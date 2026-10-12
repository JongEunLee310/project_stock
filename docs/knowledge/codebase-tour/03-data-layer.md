# 03. 데이터 층

대상 파일: `app/db/session.py`, `app/db/base.py`, `app/db/models.py`, `alembic/env.py`,
`alembic.ini`, `alembic/versions/*.py`

## app/db/session.py — 엔진과 세션 팩토리

```python
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

**엔진은 모듈 수준에 하나만 존재합니다.** 엔진은 커넥션 풀을 소유하는 무거운 객체라 앱당 하나가
정석입니다. import 시점에 만들어지지만 이때 DB에 접속하지는 않습니다. SQLAlchemy 엔진은
**lazy connect**라서 첫 쿼리가 나갈 때 비로소 커넥션을 엽니다. DB가 아직 안 떠 있어도 앱은
기동되고, 첫 요청에서 실패하는 동작이 여기서 나옵니다.

`pool_pre_ping=True`가 실무에서 중요합니다. 커넥션 풀에 오래 놀고 있던 커넥션은 DB나 중간
네트워크 장비가 먼저 끊어버렸을 수 있습니다. 이 옵션은 **풀에서 커넥션을 꺼낼 때마다 가벼운
`SELECT 1`을 먼저 던져** 살아 있는지 확인하고, 죽었으면 조용히 새 커넥션으로 교체합니다. 없으면
유휴 시간 뒤 첫 요청이 `OperationalError: server closed the connection`으로 실패합니다.

`sessionmaker` 옵션 두 개도 의도적입니다.

- **`autocommit=False`** — 명시적으로 `commit()`할 때까지 확정하지 않습니다. SQLAlchemy 2.0에서는
  사실상 강제되는 값입니다.
- **`autoflush=False`** — 기본값 `True`면 쿼리를 실행하기 직전에 세션의 보류 변경분을 자동으로
  DB에 밀어 넣습니다(flush). 편하지만 **예상치 못한 시점에 INSERT/UPDATE가 나가** 디버깅을
  어렵게 만듭니다. `False`로 두면 `db.flush()` 또는 `db.commit()`을 부를 때만 SQL이 나가므로
  흐름을 읽기 쉽습니다. 대신 "add한 객체를 커밋 전에 조회하면 안 보인다"는 점을 개발자가
  알고 있어야 합니다.

### 세션 수명과 의존성

`get_db`는 02단계에서 본 `yield` 의존성입니다. 여기에 없는 것이 있습니다 — **`commit`도 `rollback`도
없습니다.**

```python
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

일반적인 FastAPI 예제는 `except: db.rollback()`을 넣습니다. 여기 없는 이유는 이 프로젝트가
**트랜잭션 경계를 repository에 두었기** 때문입니다. repository 메서드가 각자 `commit()`하고, 실패
시에는 `db.close()`가 커밋되지 않은 트랜잭션을 자동으로 롤백합니다(SQLAlchemy `Session.close()`는
진행 중 트랜잭션을 롤백합니다). 결과적으로 데이터가 어중간하게 남지는 않지만, **한 요청에서 여러
repository를 호출하면 각각 별도 트랜잭션이 됩니다.** 중간에 실패하면 앞선 것은 이미 커밋된
상태로 남습니다. 04단계와 09단계에서 이 제약이 실제로 어떻게 다뤄지는지 봅니다.

## app/db/base.py — 선언적 기반과 공통 컬럼

```python
class Base(DeclarativeBase):
    pass
```

SQLAlchemy 2.0의 선언적 기반 클래스입니다. 1.x의 `declarative_base()` 함수 호출 방식이 클래스
상속으로 바뀌었고, 이 덕분에 `Mapped[int]` 같은 타입 어노테이션을 mypy가 이해합니다.

`Base`가 중요한 진짜 이유는 **`Base.metadata`** 입니다. `Base`를 상속한 모델 클래스가 정의되는
순간(즉 모듈 import 시점) 그 테이블 정보가 `Base.metadata`에 자동 등록됩니다. Alembic이
autogenerate로 마이그레이션을 만들 때 보는 것이 바로 이 레지스트리입니다.

```python
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

**믹스인 패턴**입니다. `Base`를 상속하지 않은 순수 클래스이므로 자체 테이블이 없고, 모델이
`class User(Base, TimestampMixin)`처럼 함께 상속하면 두 컬럼이 그 테이블에 추가됩니다. 상속
순서(`Base`가 먼저)는 관례입니다.

세 옵션의 차이를 구분해야 합니다.

| 옵션 | 실행 주체 | 시점 |
| --- | --- | --- |
| `DateTime(timezone=True)` | DB 타입 | PostgreSQL `TIMESTAMPTZ` |
| `server_default=func.now()` | **DB** | INSERT 시 DB가 채움 |
| `onupdate=func.now()` | **SQLAlchemy** | UPDATE 문 생성 시 파이썬이 값을 넣음 |

`server_default`는 DDL에 `DEFAULT now()`로 새겨지므로 **ORM을 거치지 않는 직접 SQL INSERT에도
적용**됩니다. 반면 `onupdate`는 SQLAlchemy가 UPDATE 문을 만들 때 끼워 넣는 것이라 **직접 SQL로
UPDATE하면 `updated_at`이 갱신되지 않습니다.** 워커나 배치에서 bulk update를 쓸 때 주의해야 하는
지점입니다.

`timezone=True`는 이 프로젝트 전반의 규칙입니다. 02단계의 `UtcDatetime` 직렬화, `security.py`의
`datetime.now(UTC)`와 같은 방향입니다 — **시간은 어디서든 aware UTC로 다룬다.**

### 상태값은 Enum 컬럼이 아니라 String

```python
class JobRun(Base, TimestampMixin):
    status: Mapped[str] = mapped_column(String(20))
```

`app/domains/*/types.py`에는 파이썬 enum이 정의되어 있습니다.

```python
class AlertStatus(str, Enum):
    UNREAD = "UNREAD"
    READ = "READ"
    DISMISSED = "DISMISSED"
```

그런데 **DB 컬럼은 `sa.Enum`이 아니라 `String`입니다.** 마이그레이션 43개를 전수 조사해도
`sa.Enum`/`postgresql.ENUM` 사용이 0건입니다. 의도적인 선택입니다.

PostgreSQL의 네이티브 ENUM 타입은 값을 추가할 때 `ALTER TYPE ... ADD VALUE`가 필요하고, 값 제거나
순서 변경은 사실상 타입 재생성을 요구합니다. 상태값이 자주 늘어나는 도메인(알림, 잡, 시그널)에서는
마이그레이션 부담이 큽니다. `String` + 파이썬 enum 조합이면 **DB 스키마 변경 없이 값을 추가**할
수 있고, 검증 책임은 Pydantic 스키마(`Literal` 또는 enum 타입)가 집니다.

대가는 DB 자체가 잘못된 값을 막아주지 않는다는 점입니다. 애플리케이션 밖에서 데이터를 넣으면
오염될 수 있으므로, 스키마 계층의 검증이 그만큼 중요해집니다.

### 예약어 컬럼 회피

```python
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
```

`metadata`는 SQLAlchemy `Base`가 이미 쓰는 이름이라 속성명으로 쓸 수 없습니다. 그래서 **파이썬
속성은 `metadata_`, 실제 DB 컬럼명은 `"metadata"`** 로 분리했습니다. `mapped_column`의 첫 위치
인자가 컬럼명을 지정하는 자리입니다.

`JSON` 타입은 정형화하기 이른 부가 정보를 담는 용도로 이 프로젝트 여러 곳에 등장합니다. 스키마
유연성을 얻는 대신 인덱싱과 타입 안전성을 포기하는 거래입니다.

## app/db/models.py — 27줄짜리 import 목록

```python
# Register all models in metadata regardless of each process import graph.
import app.domains.alert_candidates.model  # noqa: F401 — registers alert candidate model
import app.domains.assets.model  # noqa: F401 — registers Asset model for autogenerate
...
```

**이 파일에는 코드가 없습니다. import만 26줄 있습니다.** 그런데 이 파일이 없으면 마이그레이션이
깨집니다.

이유는 `Base.metadata`가 **import된 모델만** 알고 있기 때문입니다. Alembic이 autogenerate를 돌릴
때 `Base.metadata`에 없는 테이블은 "DB에는 있는데 코드에는 없는 테이블"로 보고 **`DROP TABLE`
마이그레이션을 생성합니다.** 웹 앱 프로세스는 라우터를 타고 대부분의 모델을 자연스럽게 import하지만,
워커 프로세스나 alembic CLI는 import 경로가 전혀 다릅니다. 그래서 **모든 모델을 강제로 한 번씩
import하는 파일**을 두고, `alembic/env.py`가 이것만 import하면 되게 만들었습니다.

주석의 "regardless of each process import graph"가 정확히 그 뜻입니다.

`# noqa: F401`은 "import했지만 쓰지 않음" 린트 경고를 끄는 지시자입니다. 각 줄에 왜 필요한지
설명까지 붙여둔 것은, 이 파일을 정리하려는 사람에게 보내는 경고입니다.

**새 모델을 추가하면 이 파일에 import를 한 줄 추가해야 합니다.** 빠뜨리면 마이그레이션
autogenerate가 그 테이블을 무시하거나, 더 나쁘게는 기존 테이블에 DROP을 생성합니다.

## alembic/env.py — 마이그레이션 실행 진입점

```python
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
```

`alembic.ini`에는 `sqlalchemy.url = driver://user:pass@localhost/dbname`이라는 **가짜 값**이
들어 있습니다. 실제 접속 문자열은 여기서 `Settings`로부터 덮어씁니다. `alembic.ini`는 git에
커밋되는 파일이므로 **자격증명을 넣지 않기 위한 처리**이며, 1단계의 "설정은 `Settings` 한 곳에서만
읽는다" 규칙이 마이그레이션에도 적용된 형태입니다.

```python
from app.db.base import Base
import app.db.models  # noqa: F401

target_metadata = Base.metadata
```

이 세 줄이 앞 절의 설명과 이어집니다. `app.db.models`를 import하는 순간 모든 모델이
`Base.metadata`에 등록되고, `target_metadata`가 autogenerate의 비교 기준(코드 쪽 정답)이 됩니다.
Alembic은 이것과 실제 DB 스키마를 비교해 차이를 마이그레이션으로 만듭니다.

### offline / online 두 가지 모드

```python
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- **offline** (`alembic upgrade head --sql`) — DB에 접속하지 않고 **SQL 스크립트만 출력**합니다.
  DBA가 검토 후 직접 실행하는 운영 환경에서 씁니다. `literal_binds=True`는 파라미터 바인딩 대신
  값을 SQL에 직접 박아 실행 가능한 스크립트를 만들라는 뜻입니다.
- **online** (평소) — 실제로 접속해 마이그레이션을 실행합니다.

```python
    connectable = engine_from_config(..., poolclass=pool.NullPool)
```

`NullPool`은 **커넥션 풀링을 하지 않는 풀**입니다. 마이그레이션은 한 번 실행되고 끝나는
프로세스라 풀이 필요 없고, 풀을 쓰면 프로세스 종료 시 커넥션이 남아 있을 수 있습니다.
`app/db/session.py`의 엔진이 기본 풀(QueuePool)을 쓰는 것과 대비됩니다 — **용도가 다르면 풀 전략도
다르다.**

```python
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
```

**모든 마이그레이션이 하나의 트랜잭션 안에서 실행됩니다.** PostgreSQL은 DDL도 트랜잭션에
포함되므로, 3개 리비전을 한 번에 올리다 마지막이 실패하면 앞의 2개도 함께 롤백됩니다. MySQL에서는
DDL이 암묵적 커밋을 일으켜 이 보장이 없습니다 — PostgreSQL을 쓰기에 가능한 안전장치입니다.

## alembic/versions/*.py — 리비전 체인

현재 43개 리비전이 있고, 체인의 시작점(`down_revision = None`)은
`6d7da5356815_create_users_table.py`, **head는 `c3d4e5f6006e_open_fund_flow_quantitative_ranges.py`
하나**입니다.

```python
revision: str = "2b8a4e9c1f03"
down_revision = "9f7c2e4d1a8b"
```

각 파일이 자기 ID와 **부모 ID**를 들고 있어서, 전체가 연결 리스트를 이룹니다. `alembic upgrade head`는
현재 DB에 기록된 리비전(`alembic_version` 테이블)에서 시작해 head까지 순서대로 `upgrade()`를
실행합니다.

### merge 리비전이 생기는 이유

```python
revision: str = "4d5e6f708192"
down_revision = ("2b3c4d5e6f70", "3c4d5e6f7081")   # 부모가 둘

def upgrade() -> None:
    pass
```

**두 개발자가 각자 브랜치에서 마이그레이션을 만들면 부모가 같은 리비전이 두 개 생깁니다**(head가
둘). 이 상태로는 `upgrade head`가 어디로 갈지 결정할 수 없어 실패합니다. `alembic merge`는 두 head를
부모로 갖는 빈 리비전을 만들어 체인을 다시 하나로 합칩니다. `upgrade()`가 `pass`인 것은 스키마
변경이 없고 **순서만 확정**하는 역할이기 때문입니다.

이 저장소에는 merge 리비전이 두 개 있습니다 — `4d5e6f708192`(news + jobs),
`8c3f0d2b7a91`(watchlists + theses). 병렬 개발의 흔적입니다.

**작업 전에 `alembic heads`로 head가 하나인지 확인**하고, 둘이면 merge가 필요합니다.

### 마이그레이션 파일의 구조

```python
def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        ...
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

def downgrade() -> None:
    op.drop_table("watchlist_items")
    op.drop_table("watchlists")
```

`downgrade()`는 `upgrade()`의 **정확한 역순**이어야 합니다. 위 예에서 생성은
`watchlists` → `watchlist_items` 순인데 삭제는 반대인 이유는 **외래키 때문**입니다.
`watchlist_items`가 `watchlists`를 참조하므로 자식을 먼저 지워야 합니다.

`sa.UniqueConstraint("watchlist_id", "asset_id", name="uq_watchlist_items_asset")`는 **복합 유니크
제약**으로, "같은 관심목록에 같은 종목을 두 번 담을 수 없다"는 도메인 규칙을 DB 수준에서
강제합니다. 04단계에서 service가 같은 규칙을 애플리케이션 수준에서도 확인하는 것을 보게 되는데,
이중 방어입니다 — service는 친절한 에러 메시지를, DB는 동시 요청 경합에서의 최종 보장을 담당합니다.

제약 이름을 명시(`name="uq_..."`)한 것도 의도입니다. 이름을 주지 않으면 DB가 자동 생성한 이름이
붙어 나중에 `downgrade`나 수정 마이그레이션에서 그 제약을 지목하기 어려워집니다. 참고로 이
프로젝트는 `Base.metadata`에 `naming_convention`을 설정하지 않았으므로, **제약 이름은 마이그레이션
작성자가 직접 붙여야 합니다.**

### 마이그레이션 파일명 규칙

```text
2b8a4e9c1f03_create_watchlists_tables.py
c3d4e5f60064_add_news_item_category.py
```

`{revision_id}_{설명}.py` 형식입니다. 초기 파일들은 alembic이 생성한 랜덤 hex ID를 쓰지만, 후기
파일들은 `c3d4e5f60050`, `c3d4e5f60051`처럼 **손으로 순번을 매긴 ID**를 씁니다. 파일 목록을
정렬했을 때 시간 순서가 보이게 하려는 실용적 선택입니다.

## 실제 운영에서의 함정

컨테이너로 백엔드를 띄울 때 **마이그레이션은 자동으로 적용되지 않습니다.** `create_app()`에는
`Base.metadata.create_all()`도 없고 `lifespan` 훅도 없습니다(01단계). 따라서 `alembic upgrade head`를
직접 실행해야 합니다.

빠뜨리면 테이블이 없어 쿼리가 `ProgrammingError`를 내고, 이는 미처리 예외이므로 01단계에서 본
경로를 탑니다 — **`ServerErrorMiddleware`가 CORS 헤더 없는 500을 반환**하고, 프런트엔드에는
`Failed to fetch`로만 보입니다. 원인이 데이터 층인데 증상은 네트워크 층으로 나타나는 대표적인
사례입니다.

## 이 단계에서 확인한 프로젝트 규칙

1. 모델은 `Base` + 필요 시 `TimestampMixin`을 상속하고, SQLAlchemy 2.0의 `Mapped[T]` +
   `mapped_column()` 문법을 쓴다.
2. 시각 컬럼은 `DateTime(timezone=True)`, 기본값은 `server_default=func.now()`.
3. 상태값 컬럼은 `String`으로 두고 파이썬 enum(`types.py`)으로 값을 관리한다. DB ENUM은 쓰지 않는다.
4. **새 모델을 만들면 `app/db/models.py`에 import를 추가한다.** 빠뜨리면 마이그레이션이 잘못
   생성된다.
5. 마이그레이션 작성 시 `downgrade()`는 `upgrade()`의 역순으로 쓰고, 제약에는 이름을 명시한다.
6. 작업 전 `alembic heads`로 head가 하나인지 확인한다. 둘이면 `alembic merge`.
7. 배포·컨테이너 기동 후 `alembic upgrade head`를 반드시 실행한다.

## 다음 단계로 이어지는 질문

- `watchlist_items`의 복합 유니크 제약을 service는 어떻게 중복 확인하는가? (04단계)
- 소유권 검사(`WATCHLIST_FORBIDDEN`)는 repository와 service 중 어디서 하는가? (04단계)
- N+1 쿼리를 막는 eager loading은 어디에 있는가? (04단계)
