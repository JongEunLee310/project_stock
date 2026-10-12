# 01. 부트스트랩과 횡단 관심사

대상 파일: `app/main.py`, `app/core/config.py`, `app/core/logging.py`,
`app/core/middleware.py`, `app/core/exceptions.py`, `app/core/response.py`,
`app/core/error_codes.py`

기준 버전: FastAPI 0.137.1 / Starlette 1.3.1 / Pydantic 2.13.4 / SQLAlchemy 2.0.51

## app/main.py — 조립 지점

### FastAPI의 정체

`FastAPI.__bases__`는 `(starlette.applications.Starlette,)`입니다. FastAPI 앱은 Starlette 앱을
상속한 것이므로 `main.py`가 `starlette.middleware.cors.CORSMiddleware`를 직접 import해도 문제가
없습니다. 역할 분담은 Starlette이 웹 계층(라우팅·미들웨어·요청/응답·예외), Pydantic이 데이터
계층(검증·직렬화), FastAPI 본체가 접착제(의존성 주입·OpenAPI 자동 생성)입니다.

### 팩토리 함수와 ASGI 앱

`create_app(app_settings: Settings = settings)` 팩토리로 감싼 이유는 인자에 있습니다. 테스트에서
다른 `Settings`를 주입해 앱을 새로 만들 수 있습니다. 파일 마지막 줄 `app = create_app()`이 만드는
`app` 변수가 ASGI 애플리케이션이며, `Dockerfile`의 `CMD ["uvicorn", "app.main:app", ...]`이
가리키는 대상입니다.

uvicorn은 그 객체를 `await app(scope, receive, send)`로 호출합니다. `scope`는 요청 메타데이터
dict, `receive`는 요청 본문을 조각 단위로 받는 async 함수, `send`는 응답을 내보내는 async
함수입니다. ASGI 앱은 결국 함수 하나이므로 다른 앱으로 감쌀 수 있고, 그것이 미들웨어의
원리입니다.

조립 순서는 로깅 설정 → FastAPI 인스턴스 → 미들웨어 2개 → 예외 핸들러 3개 → 라우터 2개입니다.
`setup_logging`이 가장 먼저인 이유는 이후 단계의 로그가 이미 잡힌 포맷을 따라야 하기 때문입니다.

### 미들웨어 실행 순서

`add_middleware`는 추가한 순서대로 실행되지 않습니다. Starlette 구현이 `append`가 아니라
`insert(0)`이기 때문입니다.

```python
def add_middleware(self, middleware_class, *args, **kwargs) -> None:
    if self.middleware_stack is not None:
        raise RuntimeError("Cannot add middleware after an application has started")
    self.user_middleware.insert(0, Middleware(middleware_class, *args, **kwargs))
```

나중에 추가한 것이 리스트 맨 앞으로 가고, 맨 앞이 가장 바깥이 됩니다. 앱이 첫 요청을 받을 때
`build_middleware_stack()`이 앞뒤로 두 개를 더 끼웁니다.

```python
middleware = (
    [Middleware(ServerErrorMiddleware, handler=error_handler, debug=debug)]
    + self.user_middleware
    + [Middleware(ExceptionMiddleware, handlers=exception_handlers, debug=debug)]
)

app = self.router
for cls, args, kwargs in reversed(middleware):
    app = cls(app, *args, **kwargs)
return app
```

`app = cls(app, ...)`이 핵심입니다. 각 미들웨어는 "다음 앱"을 인자로 받아 품는 ASGI 앱이고,
`reversed`로 도는 이유는 리스트 앞쪽 항목이 가장 바깥이 되어야 하기 때문입니다. 최종 스택은
다음과 같습니다.

```text
ServerErrorMiddleware   ← 프레임워크가 자동 배치. Exception 핸들러 소유
  CORSMiddleware        ← main.py에서 나중에 추가 = 바깥
    RequestIdMiddleware ← main.py에서 먼저 추가 = 안쪽
      ExceptionMiddleware ← 프레임워크가 자동 배치. AppException·422 핸들러 소유
        router → endpoint
```

`RuntimeError("Cannot add middleware after an application has started")`가 알려주듯 스택은 딱 한
번 조립되고 그 뒤로는 불변입니다.

### 예외 핸들러가 두 곳으로 갈리는 이유

`add_exception_handler`를 세 번 호출했지만 등록되는 자리는 두 곳으로 나뉩니다. Starlette
`build_middleware_stack()` 앞부분에 그 분기가 있습니다.

```python
if key in (500, Exception):
    error_handler = value            # ServerErrorMiddleware (최외곽)
else:
    exception_handlers[key] = value  # ExceptionMiddleware (최내곽)
```

| 등록 대상 | 실행 위치 | 층 | CORS 헤더 |
| --- | --- | --- | --- |
| `AppException` | ExceptionMiddleware | 최내곽 | 붙음 |
| `RequestValidationError` | ExceptionMiddleware | 최내곽 | 붙음 |
| `Exception` | ServerErrorMiddleware | 최외곽 | 붙지 않음 |

`ServerErrorMiddleware`는 다른 미들웨어가 실패해도 500을 돌려줘야 하는 최후 방어선이라 가장
바깥에 있어야 하고, 그 대가로 그 응답은 어떤 미들웨어도 거치지 않습니다. 실제로 미처리 500은
CORS 헤더 없이 나가므로 브라우저에서는 원인이 드러나지 않는 `Failed to fetch`로 보이고, 실제
원인은 서버 로그에서만 확인됩니다.

FastAPI는 `HTTPException`과 `RequestValidationError`의 기본 핸들러를 이미 등록해 둡니다. 우리가
`RequestValidationError` 핸들러를 등록한 것은 기본 응답 `{"detail": [...]}`을 프로젝트 공통 봉투로
덮어쓴 것입니다. `HTTPException`을 직접 쓰면 FastAPI 기본 핸들러를 타서 봉투가 깨지므로 이
프로젝트는 `AppException`만 사용합니다.

### 라우터 등록

`include_router`는 `APIRouter` 상자에 모아둔 라우트를 앱에 접붙입니다. `prefix`는 각 라우트 경로
앞에 붙고 `tags`는 `/docs` 자동 문서의 그룹을 나눕니다. `health.py`의 라우트가 `@router.get("")`인
데도 실제 URL이 `/health`가 되는 이유입니다. `health`만 따로 붙는 것은 헬스체크가 `/api/v1` 버전
접두사 밖에 있어야 로드밸런서·Docker 설정이 단순해지기 때문입니다.

### 이 프로젝트가 쓰지 않는 것

`app/` 전체에서 `lifespan`과 `on_event` 사용이 0곳입니다. 보통 앱 시작 시 커넥션 풀이나 HTTP
클라이언트를 만들고 종료 시 정리하는 데 쓰지만, 이 프로젝트는 DB 세션을 요청 단위
의존성(`Depends(get_db)`, 02단계)으로 만들고 스케줄러·워커를 별도 프로세스(08단계)로 분리했기
때문에 필요가 없습니다. `create_app()`이 순수 조립만 하는 41줄로 끝나는 이유입니다.

## app/core/config.py — 설정의 단일 출처

`pydantic-settings`는 FastAPI 공식 문서가 권장하는 설정 관리 방식이며, 엔드포인트 요청 검증과
완전히 같은 Pydantic v2 엔진을 씁니다. 여기서 익힌 검증기 문법은 04단계의 요청 스키마에 그대로
적용됩니다.

`BaseSettings`는 필드 이름과 동일한 환경변수를 자동으로 읽습니다. 우선순위는 환경변수 > `.env`
파일 > 코드 기본값이고, `extra="ignore"`로 알 수 없는 키는 무시합니다.

`LLM_PROVIDER`, `MARKET_PROVIDER`, `NEWS_PROVIDER`, `DISCLOSURE_PROVIDER`, `PORTFOLIO_PROVIDER`
다섯 개가 06단계 어댑터 팩토리의 분기 스위치입니다. 모두 `Literal`이라 오타는 기동 시점에 걸리고,
기본값이 전부 `mock`이라 외부 API 없이도 개발 환경이 돌아갑니다.

Pydantic 검증기는 세 형태로 쓰였고 도는 시점이 다릅니다.

- **`field_validator(mode="before")` — 타입 변환 전.** `CORS_ORIGINS`는
  `Annotated[list[str], NoDecode]`로 선언했습니다. `NoDecode`가 없으면 pydantic-settings가 `list`
  필드의 환경변수 값을 JSON으로 파싱하려 들어 `["http://a"]` 형식을 강요합니다. `NoDecode`로 자동
  파싱을 끄고 검증기가 콤마 구분 문자열을 직접 쪼갭니다. 빈 문자열을 `None`으로 바꾸는 처리도
  여기서 합니다.
- **`field_validator()` (기본 `mode="after"`) — 타입 변환 후.** 이미 `int | None`으로 변환된 값이
  들어오므로 범위만 확인합니다. TTL은 양수, escalation confidence는 `(0.0, 1.0]`.
- **`model_validator(mode="after")` — 여러 필드를 함께 볼 때.** `field_validator`는 자기 필드 값
  하나만 받으므로 필드 조합 규칙을 판단할 수 없습니다. 인자가 `cls`가 아니라 완성된 `self`이고
  반환도 `self`입니다. `CORS_ALLOW_CREDENTIALS=true` + `CORS_ORIGINS=*` 금지,
  `APP_ENV=prod`에서 기본 `SECRET_KEY` 금지가 여기 해당합니다.

모듈 최하단 `settings = Settings()`는 import 시점에 실행되므로 위 검증이 모두 그때 돕니다.
잘못된 설정으로 서버가 뜨는 일이 구조적으로 불가능합니다.

## app/core/logging.py — 요청 ID 전파와 마스킹

해결하려는 문제는 "깊숙한 서비스 코드에서 남긴 로그도 어느 요청인지 식별 가능해야 한다"입니다.
함수마다 `request_id`를 인자로 넘기는 대신 `ContextVar`를 씁니다.

`threading.local()`이 아니라 `ContextVar`인 것이 ASGI 환경의 핵심입니다. ASGI 서버는 한 스레드의
이벤트 루프에서 수백 개 요청을 번갈아 처리하므로, 스레드로컬을 쓰면 요청 A가 `await`에서 양보한
사이 요청 B가 같은 스레드의 값을 덮어씁니다. `ContextVar`는 스레드가 아니라 실행 컨텍스트(코루틴
체인) 단위로 격리되므로 async 환경에서 안전합니다.

`_configure_log_record_factory()`가 `logging.setLogRecordFactory`로 레코드 생성 함수를 교체해 모든
로그 레코드에 `request_id` 속성을 자동으로 심습니다. 애플리케이션 코드는 평범하게
`logger.info(...)`만 호출하면 됩니다. 이전 팩토리를 보관했다 호출하므로 다른 라이브러리의 팩토리를
덮어쓰지 않고, `_log_record_factory_configured` 플래그가 `create_app()` 반복 호출 시 팩토리
중첩을 막습니다. 팩토리 패턴의 부작용을 여기서 방어하는 구조입니다.

핸들러 중복도 같은 문제입니다. 우리 핸들러에 `_project_stock_logging_handler` 마커를 붙여두고
다음 `setup_logging` 때 마커가 붙은 핸들러만 골라 제거합니다. 루트 로거의 핸들러를 통째로 비우면
pytest·uvicorn이 붙인 핸들러까지 사라집니다.

`SensitiveDataFilter`는 `logging.Filter`를 상속하지만 통과 여부를 판단하지 않고 항상 `True`를
반환하며, 대신 레코드의 `msg`와 `args`를 재귀 순회해 민감 키의 값을 `***`로 바꿉니다. 키 판정은
소문자화 + `-` → `_` 정규화 후 부분 일치이므로 `X-API-Key`도 잡힙니다.

포맷은 `APP_ENV`에 따라 갈립니다. prod는 `JsonFormatter`, 그 외는 사람이 읽는 텍스트.
`JsonFormatter`는 화이트리스트(`method`, `path`, `status_code`, `latency_ms`, `error_code`,
`detail`, `provider`, `operation`)에 있는 레코드 속성만 JSON 필드로 승격시킵니다. 다음 절의
`extra={...}`와 짝을 이룹니다.

## app/core/middleware.py — 요청 ID를 심는 곳

미들웨어 작성 스타일은 두 가지이고 이 프로젝트에 둘 다 있습니다.

- **순수 ASGI 미들웨어** — `CORSMiddleware`. `async def __call__(self, scope, receive, send)`를 직접
  구현합니다. 빠르지만 저수준입니다.
- **`BaseHTTPMiddleware`** — `RequestIdMiddleware`. Starlette이 저수준 ASGI를 감싸주어
  `dispatch(request, call_next)` 형태로 `Request`/`Response` 객체를 다룹니다. `call_next(request)`가
  "안쪽 앱 호출"에 해당합니다. 대가로 내부에서 anyio 태스크를 하나 더 띄우므로 스트리밍
  오버헤드가 있고 `ContextVar` 전파가 직관과 다를 수 있습니다.

`dispatch`가 `async def`인 것은 선택이 아니라 ASGI 규약상 필수입니다. 미들웨어는 이벤트 루프
위에서 직접 도는 코드라 코루틴이어야 합니다.

`dispatch`가 하는 일은 네 가지입니다.

1. `X-Request-ID` 헤더가 오면 이어받고 없으면 `uuid4().hex`로 생성합니다. 상위 서비스에서 시작된
   추적 ID를 끊지 않기 위한 처리입니다.
2. 같은 값을 `request.state.request_id`와 `ContextVar` 양쪽에 저장합니다. `request.state`는
   Starlette이 제공하는 요청 스코프 임시 저장소로, 아무 속성이나 붙일 수 있고 `Request` 객체의
   수명을 따릅니다. `ContextVar`는 실행 컨텍스트가 끝나면 사라집니다. 이 이중화가 예외
   핸들러에서 결정적으로 쓰입니다.
3. 응답 헤더에 `X-Request-ID`를 되돌려줍니다.
4. `finally`에서 지연 시간을 계산해 `extra={...}`와 함께 로그를 남기고 `ContextVar`를 되돌립니다.

`status_code = 500`을 try 진입 전에 넣어두는 이유는 `call_next`가 예외를 던지면 응답 객체가 없어
상태코드를 알 수 없기 때문입니다. 같은 값을 메시지 포맷 인자와 `extra` 양쪽에 넘기는 것은 개발
환경(텍스트)과 운영 환경(JSON) 모두에서 읽히게 하려는 것입니다. `reset_request_id(token)`은
`ContextVar.set`이 돌려준 토큰으로 이전 값을 정확히 복원하므로 컨텍스트 누수가 없습니다.

## app/core/exceptions.py — 에러의 단일 출구

`AppException`은 FastAPI의 `HTTPException` 대신 직접 만든 예외입니다. 차이는 `error_code`
필드로, HTTP 상태코드와 도메인 에러코드를 함께 들고 다닙니다. 상태코드만으로는 "무엇을 못
찾았는지" 클라이언트가 구분할 수 없기 때문입니다. `headers`는 429에 `Retry-After`를 싣는 것 같은
경우를 위한 통로입니다.

핸들러 시그니처 `(Request, Exception) -> Response`와 `async def`는 Starlette이 정해둔 계약입니다.
파라미터 타입이 `AppException`이 아닌 `Exception`인 것도 그 때문이고, 그래서 각 핸들러 앞머리에
타입을 좁히는 `isinstance` 가드를 둡니다.

`_set_request_context_from_state()`가 존재하는 이유는 미처리 예외 경로에 있습니다.

```text
endpoint에서 예외 발생
  → ExceptionMiddleware: AppException이 아니므로 통과
  → RequestIdMiddleware의 finally 실행 (로그 남기고 ContextVar reset — 이 시점에 비워짐)
  → 예외가 계속 전파
  → CORSMiddleware 통과 (CORS 헤더를 붙일 기회가 사라짐)
  → ServerErrorMiddleware가 붙잡아 unhandled_exception_handler 호출 (ContextVar는 이미 빔)
```

핸들러는 사라지지 않은 `request.state.request_id`에서 값을 꺼내 `ContextVar`에 다시 심고 로그를
남긴 뒤 되돌립니다. 이 처리가 없으면 가장 중요한 에러 로그에만 `request_id=-`가 찍힙니다. 같은
이유로 `_response_headers()`가 응답 헤더에 `X-Request-ID`를 직접 붙입니다. `getattr(..., None)`
방어가 있는 것은 `RequestIdMiddleware`보다 바깥에서 터진 예외라면 `state`에 값이 없을 수 있기
때문입니다.

### `.model_dump()`가 붙는 이유

엔드포인트에서는 Pydantic 모델을 그냥 반환하면 FastAPI가 직렬화해 줍니다. 그러나 `JSONResponse`는
Starlette의 저수준 응답 객체라 `content`에 순수 dict를 요구합니다. 예외 핸들러는 FastAPI 직렬화
파이프라인 밖(미들웨어 층)에서 도는 코드이므로 직접 dict로 만들어 넘겨야 합니다.

일반화하면 **반환 타입이 `Response` 하위 클래스면 FastAPI는 손대지 않고 그대로 내보냅니다.**
`response_model` 검증도 직렬화도 건너뜁니다. 이 규칙은 엔드포인트에도 동일하게 적용되어,
상태코드를 직접 정해야 하는 경우(`health.py`의 503 분기)에 쓰입니다.

### 422 핸들러

`RequestValidationError`는 FastAPI가 요청 파라미터·본문을 Pydantic으로 검증하다 실패했을 때 던지는
예외입니다. `exc.errors()`가 돌려주는 항목의 `loc`은 `("body", "name")`처럼 실패 지점의 경로이며,
프런트엔드가 어느 입력 필드에 에러를 표시할지 판단하는 계약이라 `list()`로 변환해 그대로
내보냅니다.

## app/core/response.py, error_codes.py — 응답 봉투

모든 API 응답이 `ApiResponse`의 네 칸(`data`, `message`, `error`, `meta`)에 담깁니다. 성공과 실패의
모양이 같으므로 클라이언트는 파싱 로직 하나만 유지하면 됩니다.

`Generic[T]`이 FastAPI와 만나는 지점이 중요합니다. 엔드포인트에서
`response_model=ApiResponse[WatchlistRead]`처럼 쓰면 FastAPI가 그 구체 타입으로 OpenAPI 스키마를
생성해 `/docs`에 `data` 칸의 실제 필드까지 펼쳐 보입니다. `data: Any`로 뒀다면 문서에 아무 정보도
나오지 않습니다. `response_model`은 반환값 검증, 모델에 없는 필드 제거(내부 필드 유출 방지),
OpenAPI 스키마 생성을 동시에 수행하며, 봉투 규칙을 강제하는 실질적인 힘이 여기서 나옵니다.

페이지네이션 메타는 두 종류입니다. `PageMeta`(page/size/total)는 일반 목록,
`CursorPageMeta`(limit/has_more/next_cursor)는 계속 쌓이는 시계열 데이터(뉴스, 알림 이벤트)용으로
새 데이터가 들어와도 페이지가 밀리지 않습니다. `meta: PageMeta | CursorPageMeta | None`은 Union
타입이라 OpenAPI에 `anyOf`로 표현됩니다.

`PaginatedApiResponse(ApiResponse[list[T]])`는 상속하면서 `meta`를 `PageMeta`로 좁힌 것입니다.
원본은 `| None`이지만 여기서는 필수가 되어, 페이지네이션 응답에 meta가 반드시 있음을 타입으로
보장합니다.

엔드포인트는 `success()` / `paginated()` / `cursor_paginated()` / `error_response()` 네 함수 중
하나만 호출하고 봉투 구조를 직접 조립하지 않습니다. `cursor_paginated`의 `*`는 뒤 인자를 키워드
전용으로 만들어 `has_more`와 `next_cursor`를 순서로 헷갈리는 사고를 막습니다.

`ErrorCode`는 45개 항목의 `str, Enum`입니다. `str` 상속 덕분에 Pydantic 직렬화 시 자동으로
문자열이 되고 `code.value` 사용도 자연스럽습니다. 명명은 `{도메인}_{사유}` 규칙을 따릅니다.
백엔드와 프런트엔드가 공유하는 계약이라 새 도메인 추가 시 함께 늘어납니다.

## 요청 흐름 요약

```text
uvicorn — await app(scope, receive, send)
  ServerErrorMiddleware        Exception 핸들러 소유. 최후 방어선
    CORSMiddleware             순수 ASGI 미들웨어
      RequestIdMiddleware      BaseHTTPMiddleware. ID 생성·ContextVar·latency 로그
        ExceptionMiddleware    AppException·422 핸들러 소유
          router → endpoint → success()/paginated()
```

- **정상** — endpoint가 `ApiResponse` 반환 → `response_model` 검증·직렬화 → RequestId가
  `X-Request-ID` 부착, `finally`에서 latency 로그 + `ContextVar` reset
- **AppException** — ExceptionMiddleware가 `app_exception_handler` 호출(RequestId 안쪽) →
  `ApiResponse{error:{code}}`, CORS 헤더 정상
- **미처리 예외** — RequestId의 `finally` 실행(ContextVar 비워짐) → 전파 → ServerErrorMiddleware가
  처리(CORS 바깥) → state에서 request_id 복구 → 500, CORS 헤더 없음

## 이 단계에서 확인한 프로젝트 규칙

1. 설정은 `Settings` 한 곳에서만 읽는다. `os.environ`을 직접 조회하지 않는다.
2. 외부 연동은 `*_PROVIDER` 환경변수로 mock과 real을 교체한다.
3. 의도된 실패는 `AppException(status_code, detail, ErrorCode.XXX)`로 던진다. FastAPI의
   `HTTPException`을 쓰면 기본 핸들러를 타서 공통 봉투가 깨진다.
4. 응답은 `success()` / `paginated()` / `cursor_paginated()`로 감싸고
   `response_model=ApiResponse[...]`로 문서화한다.
5. 로그는 `logger.xxx(..., extra={...})` 형태로 남기면 `request_id`가 자동으로 붙는다. `extra` 키는
   `JsonFormatter` 화이트리스트에 있어야 JSON 출력에 나온다.

## 다음 단계로 이어지는 질문

- `api_router`에는 어떤 엔드포인트가 어떤 접두사로 붙는가? (02단계)
- `Depends(get_db)`는 정확히 언제 실행되고 세션은 언제 닫히는가? (02단계)
- 엔드포인트를 `def`로 쓸 것인가 `async def`로 쓸 것인가, 이 프로젝트의 선택과 이유는? (02단계)
- `AppException`을 실제로 던지는 쪽은 service인가 endpoint인가? (04단계에서 확정)
