# 02. 라우팅과 의존성

대상 파일: `app/api/v1/router.py`, `app/api/v1/deps.py`, `app/core/security.py`,
`app/api/v1/endpoints/auth.py`, `app/domains/users/*`, `app/core/pagination.py`,
`app/core/schema.py`, `app/db/session.py`(의존성 관점)

## app/api/v1/router.py — 라우터 트리

```python
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
```

`APIRouter`는 **중첩할 수 있습니다.** 여기서는 3단 구조입니다.

```text
FastAPI 앱
  └─ api_router (prefix="/api/v1")
      └─ auth.router (prefix="/auth")
          └─ @router.post("/login")
                최종 경로: /api/v1/auth/login
```

`prefix`는 단계마다 누적되고, `tags`는 `/docs` 문서의 그룹을 나눕니다. 이 구조 덕분에 API 버전을
올릴 때 `api_router` 한 줄만 바꾸면 되고, 엔드포인트 파일은 자기 도메인 안의 상대 경로만
신경 쓰면 됩니다.

### 경로 규칙과 도메인 이름의 불일치

URL 접두사는 **케밥 케이스**(`/alert-candidates`), 모듈 이름은 **스네이크 케이스**
(`alert_candidates`)입니다. 그리고 둘이 일치하지 않는 경우가 두 곳 있습니다.

- `prices.router` → `prefix="/stocks"` (모듈명 prices, 경로 stocks)
- `research_queue.router` → `prefix="/research-queue"`

`prices` → `/stocks`는 프런트엔드 계약이 먼저 정해진 흔적입니다. 코드에서 엔드포인트를 찾을 때
URL만으로 파일을 유추하면 이 두 곳에서 헤맬 수 있습니다.

### health가 두 번 등록되어 있다

`main.py`가 `/health`로 한 번, `api_router`가 `/api/v1/health`로 또 한 번 등록합니다. 같은 라우터
객체를 두 경로에 붙인 것이며 둘 다 동작합니다. 인프라 헬스체크(`/health`)와 API 클라이언트용
(`/api/v1/health`) 양쪽을 지원하려는 의도입니다.

### 라우트 매칭 순서

Starlette은 등록된 순서대로 위에서 아래로 경로를 매칭하고 **첫 번째로 맞는 것을 씁니다.** 그래서
`/assets/search` 같은 고정 경로는 `/assets/{asset_id}` 같은 변수 경로보다 **먼저** 등록해야
합니다. 반대로 두면 `search`가 `asset_id`로 해석됩니다. 엔드포인트 파일 안에서 데코레이터 순서를
함부로 바꾸면 안 되는 이유입니다.

## FastAPI 의존성 주입 — `Depends`의 동작 원리

`Depends(f)`는 "이 요청을 처리하기 전에 `f`를 실행하고 그 반환값을 이 파라미터에 넣어라"는
뜻입니다. FastAPI는 라우트 등록 시점(모듈 import 시점)에 함수 시그니처를 훑어 **의존성 그래프**를
미리 만들어 둡니다.

```python
def get_current_user(
    token: str | None = Depends(oauth2_scheme),   # 의존성이 또 의존성을 가짐
    db: Session = Depends(get_db),
) -> User:
```

**의존성은 중첩됩니다.** `/auth/me`를 호출하면 다음 순서로 해석됩니다.

```text
get_me(current_user = Depends(get_current_user))
  └─ get_current_user
      ├─ oauth2_scheme  → Authorization 헤더에서 Bearer 토큰 추출
      └─ get_db         → DB 세션 생성
```

같은 요청 안에서 **동일한 의존성 함수는 한 번만 실행되고 결과가 재사용됩니다**(요청 스코프 캐싱).
엔드포인트가 `get_db`와 `get_current_user`를 모두 요구해도 세션은 하나만 만들어지고, 둘이 같은
트랜잭션을 공유합니다. 이 프로젝트의 서비스 계층이 안심하고 `db`를 받아 쓰는 근거입니다.

### `yield` 의존성 — 정리 코드가 있는 의존성

```python
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

`return`이 아니라 `yield`를 쓰면 FastAPI가 **`yield` 앞을 요청 전에, 뒤를 응답 후에** 실행합니다.
`finally: db.close()`가 커넥션을 풀에 반납하는 지점입니다. 예외가 나도 `finally`는 돌므로 커넥션이
새지 않습니다.

주목할 점은 **여기에 `commit`도 `rollback`도 없다**는 것입니다. 이 프로젝트는 트랜잭션 경계를
의존성이 아니라 **repository 계층**에 두었습니다(`UserRepository.create`가 직접 `db.commit()`
호출). 04단계에서 이 선택의 파장을 다시 봅니다.

실행 순서를 정확히 말하면 이렇습니다.

```text
요청 → get_db의 yield 앞 실행 → 엔드포인트 실행 → 응답 생성
     → get_db의 finally 실행 → 응답 전송
```

즉 **세션은 응답이 직렬화된 뒤에 닫힙니다.** 그래서 엔드포인트가 ORM 객체를 그대로 반환해도
lazy loading이 터지지 않습니다.

### `oauth2_scheme` — OAuth2PasswordBearer

```python
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
```

이 객체는 두 가지 일을 합니다.

1. **런타임** — `Authorization: Bearer <token>` 헤더에서 토큰 문자열만 뽑아 돌려줍니다.
2. **문서** — OpenAPI에 security scheme을 등록해 `/docs`에 "Authorize" 버튼이 생기게 합니다.

`tokenUrl`은 **문서용 정보일 뿐** 실제로 그 주소를 호출하지 않습니다. `/docs`에서 로그인 폼을
어디로 보낼지 알려주는 값입니다.

`auto_error=False`가 중요합니다. 기본값 `True`면 헤더가 없을 때 FastAPI가 곧바로 `HTTPException`
401을 던지는데, 그러면 1단계에서 본 대로 **FastAPI 기본 형식** `{"detail": ...}`이 나가서 공통
봉투가 깨집니다. `False`로 두어 `token`을 `None`으로 받고, 우리가 직접 `AppException`을 던집니다.

```python
def get_current_user(token: str | None = Depends(oauth2_scheme), ...) -> User:
    if token is None:
        raise _INVALID_TOKEN_EXC
```

**의존성 안에서 던진 예외도 1단계의 예외 핸들러가 그대로 처리합니다.** 엔드포인트 본문이 아직
실행되지 않았더라도 미들웨어 스택 안쪽에서 벌어진 일이기 때문입니다.

### 인증 실패를 모두 401 + 같은 메시지로 처리하는 이유

```python
_INVALID_TOKEN_EXC = AppException(
    status_code=401,
    detail="유효하지 않은 토큰입니다.",
    error_code=ErrorCode.AUTH_INVALID_TOKEN,
    headers=AUTHENTICATE_HEADERS,   # {"WWW-Authenticate": "Bearer"}
)
```

토큰 없음 / 서명 불일치 / 만료 / `type`이 access가 아님 / `sub`가 문자열이 아님 — 전부 같은 예외로
수렴합니다. **공격자에게 실패 원인을 알려주지 않기 위한 의도적 설계**입니다. `WWW-Authenticate:
Bearer` 헤더는 401 응답에 붙이도록 HTTP 표준이 정한 것으로, 1단계에서 `AppException`에 `headers`
필드를 둔 이유가 여기서 쓰입니다.

예외 객체를 모듈 상수로 한 번만 만들어 재사용하는 것도 눈여겨볼 만합니다. 예외에 요청별 상태가
없으므로 가능한 최적화입니다.

## app/core/security.py — JWT와 비밀번호

```python
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
```

`passlib`의 `CryptContext`는 해시 알고리즘을 감싸는 계층입니다. `schemes` 리스트의 **첫 번째가
새 해시를 만들 때 쓰는 알고리즘**이고, 나머지는 검증만 가능한 레거시입니다. `deprecated="auto"`는
"첫 번째가 아닌 알고리즘으로 만들어진 해시는 낡은 것으로 표시"하라는 뜻으로, 나중에
`bcrypt` → `argon2` 전환 시 재해싱 판단에 쓸 수 있게 열어둔 것입니다.

bcrypt는 **해시마다 다른 salt를 자동 생성해 결과 문자열에 포함**하므로, 같은 비밀번호라도 매번
다른 해시가 나옵니다. 그래서 검증은 문자열 비교가 아니라 `pwd_context.verify(plain, hashed)`로
해야 합니다.

```python
def decode_token(token: str) -> dict[str, Any]:
    """JWT의 서명과 만료를 검증하고 payload를 반환한다.

    토큰의 `type`은 검증하지 않으므로 호출자가 용도에 맞는 `type`인지 확인해야 한다.
    """
```

**이 프로젝트에서 보기 드문 docstring이고, 그만한 이유가 있습니다.** `jwt.decode`는 서명과 `exp`
(만료)를 검증하지만 `type` 클레임은 모릅니다. access 토큰과 refresh 토큰이 같은 `SECRET_KEY`로
서명되므로, **`type`을 확인하지 않으면 refresh 토큰으로 API에 접근할 수 있습니다.** 그래서 두
호출자가 각각 확인합니다.

- `deps.get_current_user` → `payload.get("type") != "access"`면 거부
- `UserService.refresh` → `payload.get("type") != "refresh"`면 거부

```python
to_encode = {"sub": str(subject), "exp": expire, "type": "access"}
```

`sub`(subject)와 `exp`(expiration)는 **JWT 표준 클레임**이고 `type`은 이 프로젝트가 추가한
커스텀 클레임입니다. `sub`를 `str(subject)`로 변환하는 이유는 표준이 문자열을 요구하기 때문이며,
그래서 읽는 쪽에서 `int(sub)`로 되돌립니다.

`datetime.now(UTC)`를 쓰는 것도 의도적입니다. `datetime.now()`(naive)를 쓰면 서버 타임존에 따라
만료 시각이 어긋납니다. 시간은 항상 UTC aware로 다루는 것이 이 프로젝트의 규칙입니다.

## app/api/v1/endpoints/auth.py — 엔드포인트 4개의 표준형

```python
@router.post(
    "/register",
    response_model=ApiResponse[UserResponse],
    status_code=201,
    summary="Register user",
    description="Create a user account with email and password.",
)
def register(data: UserCreate, db: Session = Depends(get_db)) -> ApiResponse[UserResponse]:
    return success(UserResponse.model_validate(UserService(db).register(data)))
```

이 4줄에 이 프로젝트 엔드포인트의 규칙이 전부 들어 있습니다.

**① 파라미터 출처 결정** — `data: UserCreate`는 Pydantic 모델이므로 FastAPI가 **요청 본문(JSON)**
으로 해석해 검증합니다. 검증 실패 시 `RequestValidationError` → 1단계의 422 핸들러로 갑니다.
`db`는 기본값이 `Depends(...)`이므로 의존성 주입입니다.

**② `status_code=201`** — 생성 계열은 명시적으로 201을 지정합니다. 지정하지 않으면 200입니다.

**③ `response_model=ApiResponse[UserResponse]`** — 1단계에서 본 제네릭 봉투가 여기서 구체화됩니다.
`/docs`에 `data` 칸의 실제 필드까지 펼쳐집니다.

**④ 엔드포인트는 얇다** — 로직이 없습니다. `UserService(db)`를 만들고 호출하고 `success()`로 감싸는
것이 전부입니다. **비즈니스 로직은 service, HTTP 관심사는 endpoint**라는 경계가 여기서 강제됩니다.

**⑤ `def`이지 `async def`가 아니다** — 실측하면 `app/api/v1/endpoints/` 안에 `async def`가 0개,
`def`가 122개, `AsyncSession` 사용이 0곳입니다. FastAPI는 두 경우를 다르게 실행합니다.

| 선언 | 실행 위치 | 블로킹 호출 시 |
| --- | --- | --- |
| `async def` | 이벤트 루프에서 직접 | 서버 전체가 멈춤 |
| `def` | anyio 스레드풀로 위임 | 다른 요청은 계속 처리됨 |

이 프로젝트는 동기 SQLAlchemy `Session`을 쓰므로 `db.execute(...)`가 블로킹 호출입니다. 엔드포인트를
`async def`로 선언했다면 DB 쿼리마다 서버 전체가 멈췄을 것입니다. 122개가 모두 `def`인 것은 우연이
아니라 일관된 설계이며, 이 코드베이스에서 `async def`를 만나면 이유를 확인해야 합니다(미들웨어와
예외 핸들러는 ASGI 규약상 필수, 외부 HTTP 호출 어댑터는 정당한 사유).

```python
def get_me(current_user: User = Depends(get_current_user)) -> ApiResponse[UserResponse]:
    return success(UserResponse.model_validate(current_user))
```

`/me`에는 `db` 파라미터가 없습니다. `get_current_user`가 내부적으로 `get_db`를 쓰기 때문에 세션은
이미 만들어졌고, 엔드포인트가 직접 쓸 일이 없으니 받지 않는 것입니다. **의존성 그래프가 필요한
것만 정확히 요구하게 해줍니다.**

## app/domains/users/* — 도메인 4파일 구조

38개 도메인이 전부 이 모양입니다. `users`가 가장 작아서 골격을 보기 좋습니다.

| 파일 | 책임 | 아는 것 / 모르는 것 |
| --- | --- | --- |
| `model.py` | SQLAlchemy ORM 테이블 정의 | DB만 안다 |
| `schema.py` | Pydantic 요청·응답 스키마 | HTTP 계약만 안다 |
| `repository.py` | DB 쿼리 | SQLAlchemy를 안다. 비즈니스 규칙은 모른다 |
| `service.py` | 비즈니스 규칙 | repository를 안다. HTTP는 모른다 |

### model.py — SQLAlchemy 2.0 스타일

```python
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
```

SQLAlchemy 2.0의 `Mapped[T]` + `mapped_column()` 문법입니다. 1.x의 `Column(Integer)` 방식과 달리
**타입 어노테이션이 실제 컬럼 타입을 결정**하므로 mypy가 `user.email`이 `str`임을 압니다.
`Mapped[str]`은 `NOT NULL`, `Mapped[str | None]`은 nullable로 자동 변환됩니다.

`hashed_password`라는 이름이 중요합니다. 평문 비밀번호가 DB에 닿지 않는다는 것을 **컬럼 이름으로
선언**한 것입니다. `TimestampMixin`은 03단계에서 봅니다.

### schema.py — Pydantic 스키마 3종

```python
class UserCreate(BaseModel):
    email: EmailStr
    password: str
```

`EmailStr`은 Pydantic이 제공하는 이메일 검증 타입입니다(`email-validator` 패키지 필요). 형식이
틀리면 422가 나갑니다.

**요청 스키마와 응답 스키마가 분리되어 있는 것이 핵심입니다.** `UserCreate`에는 `password`가 있고
`UserResponse`에는 없습니다. 한 클래스로 합쳤다면 응답에 비밀번호가 새어 나갈 위험이 생깁니다.

```python
class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    email: str
    is_active: bool
    created_at: UtcDatetime
```

`from_attributes = True`(Pydantic v1의 `orm_mode`)가 있어야 `UserResponse.model_validate(user_orm_object)`
가 동작합니다. dict가 아니라 **속성 접근으로 값을 읽으라**는 설정입니다. 이것이 ORM 객체를 응답
스키마로 바꾸는 표준 경로입니다.

`hashed_password`가 필드에 없다는 점을 확인하세요. `model_validate`는 스키마에 선언된 필드만
가져오므로, **응답에 내부 필드가 새지 않는 것이 구조적으로 보장**됩니다.

```python
    @computed_field  # type: ignore[prop-decorator]
    @property
    def username(self) -> str:
        return self.email.split("@", maxsplit=1)[0]
```

`computed_field`는 **DB에 없지만 응답에는 포함되는 파생 필드**를 만듭니다. 직렬화 결과와 OpenAPI
스키마 양쪽에 나타납니다. DB 컬럼을 추가하지 않고 표현 계층에서 파생값을 만드는 방법입니다.

### core/schema.py — UTC 직렬화 규칙

```python
UtcDatetime = Annotated[
    datetime, PlainSerializer(serialize_utc, return_type=str, when_used="json")
]
```

`Annotated[타입, 메타데이터]`로 만든 **재사용 가능한 커스텀 타입**입니다. `PlainSerializer`는
"이 필드를 JSON으로 직렬화할 때 이 함수를 써라"는 Pydantic v2 지시자이고, `when_used="json"`은
`model_dump()`(파이썬 객체)에는 적용하지 않고 `model_dump_json()`에만 적용하라는 뜻입니다.

`serialize_utc`는 naive datetime을 UTC로 간주해 붙이고, 최종적으로 `2026-07-31T09:00:00Z` 형식으로
내보냅니다. **`+00:00`을 `Z`로 바꾸는 이유는 JavaScript `new Date()` 호환** 때문입니다.
`created_at: UtcDatetime`처럼 쓰기만 하면 모든 응답의 시각 형식이 통일됩니다.

### repository.py — 쿼리만

```python
class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self.db.scalars(stmt).first()

    def create(self, email: str, hashed_password: str) -> User:
        user = User(email=email, hashed_password=hashed_password)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
```

세션을 생성자로 받습니다(**생성자 주입**). 세션의 수명은 `get_db`가 관리하고 repository는 빌려
쓰기만 합니다.

`select(User)`는 SQLAlchemy 2.0 스타일이고, `db.scalars(stmt)`는 결과의 첫 컬럼(즉 `User` 객체)만
꺼냅니다. 1.x의 `db.query(User).filter(...)`는 레거시입니다.

`create`의 3연타를 정확히 이해해야 합니다.

- `db.add(user)` — 세션에 등록만. 아직 SQL 없음
- `db.commit()` — INSERT 실행 + 트랜잭션 확정
- `db.refresh(user)` — DB가 채운 값(`id`, `created_at`)을 객체에 다시 읽어옴

`refresh`가 없으면 `user.id`가 `None`이라 응답에 넣을 수 없습니다.

**이 프로젝트는 repository가 직접 커밋합니다.** 장점은 단순함, 단점은 "여러 repository 호출을
하나의 트랜잭션으로 묶기"가 어렵다는 것입니다. 04단계와 09단계에서 이 제약이 어떻게 드러나는지
봅니다.

### service.py — 비즈니스 규칙

```python
class UserService:
    def __init__(self, db: Session) -> None:
        self.repo = UserRepository(db)

    def register(self, data: UserCreate) -> User:
        if self.repo.get_by_email(data.email):
            raise AppException(400, "이미 등록된 이메일입니다.", ErrorCode.USER_EMAIL_DUPLICATE)
        return self.repo.create(email=data.email, hashed_password=hash_password(data.password))
```

**`AppException`을 던지는 주체가 service라는 점이 이 프로젝트의 규칙입니다.** 엔드포인트는
try/except를 쓰지 않고, service가 던진 예외가 미들웨어까지 올라가 공통 봉투로 변환됩니다.
전역 지침의 "에러 처리는 시스템 경계에서만"이 구현된 형태입니다.

`register`가 `Token`이 아니라 `User`를 돌려주는 것도 의도입니다. 가입과 로그인은 별개 행위이므로
가입 직후 자동 로그인시키지 않습니다.

```python
    def login(self, data: UserLogin) -> Token:
        user = self.repo.get_by_email(data.email)
        if not user or not verify_password(data.password, user.hashed_password):
            raise AppException(401, "이메일 또는 비밀번호가 올바르지 않습니다.",
                               ErrorCode.AUTH_INVALID_CREDENTIALS)
```

"이메일 없음"과 "비밀번호 틀림"을 **하나의 조건으로 합쳐 같은 메시지**를 냅니다. 분리하면
공격자가 가입된 이메일 목록을 알아낼 수 있습니다(user enumeration).

`refresh`는 새 access 토큰만 발급하고 refresh 토큰은 재발급하지 않습니다(`Token`의 `refresh_token`
기본값이 `""`). refresh 토큰의 수명을 고정해 무한 갱신을 막는 선택입니다.

`refresh` 안의 `from jwt import PyJWTError`는 함수 지역 import인데, 이 파일에서 유일한 사례입니다.
특별한 이유가 보이지 않으므로 모듈 상단으로 올려도 무방한 지점입니다.

## app/core/pagination.py — 의존성으로 만든 재사용 파라미터

### 클래스를 의존성으로 쓰기

```python
class PaginationParams:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> None:
        self.page = page
        self.size = size
```

**FastAPI는 클래스도 의존성으로 받습니다.** 이때 `__init__`의 시그니처를 함수 시그니처처럼 읽습니다.
엔드포인트에서 `pagination: PaginationParams = Depends()`로 쓰면(콜러블 생략 시 타입 어노테이션을
그대로 사용) `?page=2&size=50`이 검증되어 객체로 들어옵니다.

`Annotated[int, Query(ge=1, le=100)]`이 세 가지를 동시에 합니다. **쿼리 파라미터임을 선언**하고,
**범위를 검증**하고(`size=1000`이면 422), **OpenAPI 문서에 제약을 기록**합니다. `le=100`은 클라이언트가
한 번에 과도한 양을 요청하지 못하게 막는 방어선입니다.

`offset`/`limit` 프로퍼티가 페이지 번호를 SQL 오프셋으로 변환합니다. 이 변환을 한 곳에 둔 덕분에
모든 목록 엔드포인트가 같은 규칙을 씁니다.

### 의존성 팩토리 — 파라미터를 받는 의존성 만들기

```python
def sort_param(*, allowed_fields: Collection[str], default: str) -> Callable[[str | None], SortParams]:
    parse_sort(default, allowed_fields=allowed_fields, default=default)   # 기동 시 자기검증

    def dependency(sort: Annotated[str | None, Query()] = default) -> SortParams:
        return parse_sort(sort, allowed_fields=allowed_fields, default=default)

    return dependency
```

`Depends`는 **인자를 받는 함수를 직접 받을 수 없습니다.** 정렬 허용 필드는 엔드포인트마다 다른데,
`Depends(parse_sort)`처럼 쓸 방법이 없습니다. 그래서 **의존성 함수를 만들어 돌려주는 팩토리**를
씁니다. 엔드포인트에서는 이렇게 쓰입니다.

```python
sort: SortParams = Depends(sort_param(allowed_fields={"created_at", "symbol"}, default="-created_at"))
```

함수 첫 줄의 `parse_sort(default, ...)` 호출이 영리한 부분입니다. 반환값을 버리는데, 목적은
**`default`가 `allowed_fields`에 실제로 있는지 앱 기동 시점에 검사**하는 것입니다. 개발자가
오타를 내면 첫 요청이 아니라 서버 기동 때 터집니다.

정렬 표기는 `-created_at`처럼 **접두사 `-`가 내림차순**입니다. 화이트리스트 밖의 필드가 오면
`RequestValidationError`를 직접 던지는데, 이러면 1단계의 422 핸들러를 그대로 타서 다른 검증 실패와
같은 응답 형식이 나옵니다. **프레임워크 예외를 직접 던져 형식을 통일하는 기법**입니다. 임의 컬럼
정렬을 막는 것은 SQL injection 방어이기도 합니다.

### 커서 페이지네이션

```python
def encode_datetime_cursor(timestamp: datetime, row_id: int) -> str:
    payload = json.dumps({"timestamp": ..., "row_id": row_id}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")
```

커서는 `(timestamp, row_id)` 쌍을 JSON → base64로 인코딩한 **불투명 문자열**입니다. 클라이언트는
내용을 해석하지 말고 그대로 돌려보내면 됩니다.

`row_id`가 함께 들어가는 이유는 **같은 timestamp를 가진 행이 여럿일 때 순서를 확정**하기
위해서입니다. timestamp만으로 커서를 만들면 동시각 행이 누락되거나 중복됩니다.

`urlsafe_b64encode`는 `+/`를 `-_`로 바꿔 URL에 안전하게 만들고, `rstrip("=")`으로 패딩을 떼어
URL을 깔끔하게 합니다. 디코딩 시 `"=" * (-len(cursor) % 4)`로 패딩을 복원합니다.

디코딩 실패 시에도 `RequestValidationError`를 던져 422로 통일합니다. `validate=True`는 base64가
아닌 문자가 섞이면 예외를 내게 하는 옵션이며, `raise ... from None`은 내부 예외 체인을 숨겨
클라이언트에게 스택 정보를 흘리지 않습니다.

## 요청 흐름 — `POST /api/v1/auth/login`

```text
1. 라우팅        api_router(/api/v1) → auth.router(/auth) → post("/login")
2. 의존성 해석   Depends(get_db) → SessionLocal() 생성 (yield 앞)
3. 본문 검증     UserLogin(email: EmailStr, password: str) — 실패 시 422
4. 엔드포인트    def login(...)  ← 동기 함수이므로 anyio 스레드풀에서 실행
5. 서비스        UserService(db).login(data)
6. 리포지토리    UserRepository.get_by_email → SELECT
7. 검증          verify_password(bcrypt) — 실패 시 AppException(401)
8. 토큰 생성     create_access_token / create_refresh_token
9. 응답 조립     success(Token) → ApiResponse[Token]
10. 직렬화       response_model이 검증 + JSON 변환
11. 정리         get_db의 finally → db.close()
12. 미들웨어     RequestId가 X-Request-ID 부착, latency 로그
```

인증이 필요한 요청(`GET /api/v1/auth/me`)은 2번과 3번 사이에 이 과정이 추가됩니다.

```text
oauth2_scheme → Authorization 헤더에서 토큰 추출 (없으면 None)
get_current_user → decode_token(서명·만료 검증) → type == "access" 확인
                 → SELECT user → 없으면 AppException(401)
```

## 이 단계에서 확인한 프로젝트 규칙

1. 엔드포인트는 얇게 유지한다. `Service(db)` 호출과 `success()` 포장이 전부이고 try/except를 쓰지
   않는다.
2. 엔드포인트는 항상 `def`로 선언한다. 동기 SQLAlchemy를 쓰므로 `async def`는 서버를 멈춘다.
3. 요청 스키마와 응답 스키마를 분리한다. ORM → 응답은 `model_validate` + `from_attributes`.
4. 응답의 시각 필드는 `UtcDatetime`을 쓴다.
5. `AppException`은 service가 던진다. 인증 실패는 원인을 구분하지 않고 같은 메시지로 응답한다.
6. 목록 파라미터는 `PaginationParams`, `sort_param(...)`, 커서 헬퍼를 재사용한다. 정렬 필드는
   반드시 화이트리스트로 제한한다.
7. FastAPI 기본 401(`auto_error=True`)처럼 공통 봉투를 깨는 프레임워크 기본 동작은 꺼두고 직접
   처리한다.

## 다음 단계로 이어지는 질문

- `Base`와 `TimestampMixin`은 무엇을 제공하는가? (03단계)
- `create_engine`의 `pool_pre_ping=True`는 무엇을 막는가? (03단계)
- 마이그레이션 파일 44개는 어떤 순서로 적용되며 `merge` 리비전은 왜 생겼는가? (03단계)
- repository가 직접 커밋하는 구조에서 여러 테이블을 한 트랜잭션으로 묶으려면? (04·09단계)
