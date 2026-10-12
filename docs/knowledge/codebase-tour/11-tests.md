# 11. 테스트 지형

대상 파일: `tests/conftest.py`, `tests/test_*.py`(100개), `pyproject.toml`

## 구성

```text
tests/
  conftest.py            공용 픽스처·헬퍼 (113줄)
  test_*.py              100개, 평면 구조 (하위 디렉터리 없음)
```

**디렉터리를 나누지 않았습니다.** `tests/unit/`, `tests/integration/` 같은 구분 없이 파일명으로만
구분합니다. 파일명이 대체로 `app/` 구조를 반영합니다.

| 테스트 파일 | 대상 |
| --- | --- |
| `test_watchlists.py` | `domains/watchlists` + 엔드포인트 |
| `test_llm_gateway.py`, `test_llm_privacy.py`, ... | `adapters/llm/` 파일별 |
| `test_error_handlers.py`, `test_response.py`, `test_logging.py` | `core/` |
| `test_alembic_metadata.py`, `test_worker_model_registry.py` | **구조 자체** |
| `test_api_contract.py`, `test_integration_flow.py` | 계약·전체 흐름 |

## pyproject.toml — 실행 설정

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=app --cov-report=xml --cov-report=term-missing"

[tool.coverage.run]
source = ["app"]
omit = ["*/migrations/*", "alembic/*"]
```

`addopts`에 커버리지가 들어 있어 **`uv run pytest`만 쳐도 항상 커버리지가 측정**됩니다.
`term-missing`은 커버되지 않은 줄 번호를 터미널에 표시하고, `xml`은 SonarQube 연동용입니다
(`sonar-project.properties`가 저장소에 있습니다).

```toml
[tool.mypy]
python_version = "3.12"
strict = true
exclude = "^scripts/"
```

**mypy `strict = true`** 입니다. 지금까지 코드에서 본 `cast(...)`, `TypeGuard`, `# type: ignore`
주석들이 왜 있는지가 여기서 설명됩니다. strict 모드는 타입 어노테이션이 없는 함수를 허용하지
않으므로, 모든 함수에 반환 타입이 붙어 있습니다.

CI는 **ruff + mypy + pytest 세 가지**를 모두 돌립니다. 로컬 검증에서 mypy를 빠뜨리면 CI에서
막힙니다.

## conftest.py — 이 파일이 테스트 전략의 전부

### import보다 먼저 실행되는 환경변수 설정

```python
import os
...
# OS environment variables must win over local .env values during Settings import.
_PROVIDER_SETTINGS = ("MARKET_PROVIDER", "NEWS_PROVIDER", "DISCLOSURE_PROVIDER",
                      "PORTFOLIO_PROVIDER", "LLM_PROVIDER")
for _provider_setting in _PROVIDER_SETTINGS:
    os.environ[_provider_setting] = "mock"

from app.core.config import settings  # noqa: E402
```

**파일 최상단에서 환경변수를 먼저 설정하고 그 다음에 앱을 import합니다.** `# noqa: E402`(import가
파일 맨 위에 있지 않음)는 이 순서가 의도적임을 표시합니다.

1단계에서 본 `settings = Settings()`가 **import 시점에 실행**되기 때문입니다. `app.core.config`를
import하는 순간 환경변수를 읽으므로, 그전에 값을 심어두어야 합니다. 순서가 바뀌면 개발자의
`.env`에 있는 실제 API 키로 테스트가 돌아 외부 호출과 비용이 발생합니다.

```python
# Also reset the cached object in case another pytest plugin imported it first.
for _provider_setting in _PROVIDER_SETTINGS:
    setattr(settings, _provider_setting, "mock")
```

**같은 일을 두 번 합니다.** 다른 pytest 플러그인이 `conftest.py`보다 먼저 `app.core.config`를
import했다면 `settings` 객체가 이미 만들어진 뒤이므로, 이미 만들어진 객체의 속성을 직접
덮어씁니다. 두 겹 방어이고, 주석이 그 이유를 설명합니다.

이 열 줄이 **"테스트는 절대 외부에 나가지 않는다"** 를 보장합니다. 06·07단계의 mock 어댑터가
여기서 활성화됩니다.

### 인메모리 SQLite

```python
engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

운영은 PostgreSQL인데 테스트는 **인메모리 SQLite**입니다. 빠르고 격리가 쉽지만 대가가 있습니다.

옵션 두 개가 필수입니다.

- **`check_same_thread=False`** — SQLite는 기본적으로 커넥션을 만든 스레드에서만 쓸 수 있습니다.
  02단계에서 본 대로 FastAPI가 동기 엔드포인트를 **스레드풀에서 실행**하므로, 이 옵션이 없으면
  `TestClient` 요청이 전부 실패합니다.
- **`StaticPool`** — 기본 풀은 커넥션마다 **새 인메모리 DB**를 만듭니다. `sqlite://`는 커넥션에
  귀속된 메모리 공간이라 커넥션이 다르면 테이블이 없습니다. `StaticPool`은 커넥션 하나를 계속
  재사용해 모두가 같은 DB를 보게 합니다.

**SQLite로 검증할 수 없는 것들**을 알아두어야 합니다.

- PostgreSQL 전용 타입·함수
- 03단계에서 본 트랜잭션 안 DDL 롤백
- 09단계 `begin_nested()`의 SAVEPOINT 동작(SQLite도 지원하지만 세부가 다름)
- 동시성 관련 제약 경합

04·09단계에서 본 "동시 요청 경합에서 `IntegrityError`가 최종 방어" 같은 경로는 **단위 테스트로
검증하기 어렵습니다.**

### client 픽스처 — 매 테스트마다 새 스키마

```python
@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
```

**`app.dependency_overrides`가 FastAPI 테스트의 핵심 기능입니다.** 02단계에서 본 `Depends(get_db)`가
있는 모든 곳에서 이 대체 함수가 대신 실행됩니다. 애플리케이션 코드를 전혀 건드리지 않고 DB를
바꿔치기합니다. 이것이 의존성 주입을 쓰는 실질적 이득입니다.

`create_all` → 테스트 → `drop_all`로 **매 테스트가 빈 DB에서 시작**합니다. 03단계의 alembic
마이그레이션을 쓰지 않고 `Base.metadata`에서 직접 만드는데, 빠르지만 **마이그레이션 자체는
검증되지 않습니다.** 마이그레이션에 버그가 있어도 테스트는 통과합니다.

`with TestClient(app)`으로 컨텍스트 매니저를 쓰는 것은 lifespan 이벤트를 발생시키기 위한
것입니다. 01단계에서 확인한 대로 이 앱에는 lifespan이 없지만, 관례를 따랐습니다.

`Base.metadata.create_all`이 **모든 테이블을 만들려면 모든 모델이 import되어 있어야** 합니다.
03단계의 `app/db/models.py`가 여기서도 역할을 합니다.

### 인증 우회

```python
def set_current_user(user_id: int, email: str = "owner@example.com") -> None:
    def override_get_current_user() -> User:
        return User(id=user_id, email=email, hashed_password="test-hash")

    app.dependency_overrides[get_current_user] = override_get_current_user
```

`get_current_user`를 통째로 대체해 **JWT 발급·검증을 건너뜁니다.** 관심목록 테스트에서 매번
회원가입 → 로그인 → 토큰 헤더를 붙이는 것은 낭비이고, 그 경로는 `test_auth.py`가 따로 검증합니다.

`User(id=..., ...)`가 **DB에 저장되지 않은 객체**라는 점이 흥미롭습니다. service는 `user_id`만
쓰므로(02·04단계에서 확인한 계약) 실제 행이 없어도 동작합니다. 계층 분리가 잘 되어 있어 가능한
단순화입니다.

이 함수는 픽스처가 아니라 **일반 함수**라 테스트 안에서 명시적으로 호출합니다. 소유권 검증
테스트에서 사용자를 바꿔가며 여러 번 호출할 수 있습니다.

### 응답 봉투 헬퍼

```python
def api_data(response: Any) -> Any:
    body = response.json()
    assert body["message"] is None
    assert body["error"] is None
    return body["data"]

def api_error(response: Any) -> dict[str, Any]:
    body = response.json()
    assert body["data"] is None
    assert body["meta"] is None
    error = body["error"]
    return {"message": body["message"], **error}
```

1단계의 `ApiResponse` 봉투를 벗기는 헬퍼입니다. **꺼내면서 검증도 합니다** — `api_data`는
`error`가 없음을, `api_error`는 `data`가 없음을 확인합니다.

덕분에 모든 테스트가 `data = api_data(response)`로 시작하고, **봉투 규칙 위반이 자동으로
잡힙니다.** 봉투 구조를 바꾸면 이 세 함수만 고치면 됩니다.

### 느린 해시 우회

```python
@pytest.fixture
def stable_password_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    def hash_password(password: str) -> str:
        return f"hashed:{password}"

    monkeypatch.setattr("app.domains.users.service.hash_password", hash_password)
    monkeypatch.setattr("app.domains.users.service.verify_password", verify_password)
```

bcrypt는 **의도적으로 느리게** 설계된 알고리즘입니다(무차별 대입 방어). 테스트에서 매번 돌리면
전체 시간이 크게 늘어나므로 단순 문자열 접두사로 대체합니다.

`monkeypatch.setattr`의 대상이 `app.core.security.hash_password`가 아니라
**`app.domains.users.service.hash_password`** 인 점이 중요합니다. `service.py`가
`from app.core.security import hash_password`로 가져왔으므로 **service 모듈의 이름공간에 있는
참조**를 바꿔야 합니다. 원본 모듈을 패치하면 이미 import된 참조는 그대로여서 효과가 없습니다.
파이썬 monkeypatch에서 가장 흔한 실수 지점입니다.

## 테스트 스타일 — API 레벨 통합 테스트가 기본

```python
def create_asset(client: TestClient, symbol: str = "AAPL") -> dict[str, Any]:
    response = client.post("/api/v1/assets",
                           json={"symbol": symbol, "name": f"{symbol} Inc.", "market": "NASDAQ"})
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))
```

**service를 직접 부르지 않고 HTTP 엔드포인트로 데이터를 만듭니다.** 테스트 파일마다 이런 팩토리
헬퍼가 위쪽에 모여 있습니다.

장점은 라우팅·검증·직렬화까지 한 번에 검증된다는 것입니다. 단점은 테스트가 느리고, 실패했을 때
어느 계층이 문제인지 바로 알기 어렵다는 것입니다.

**이 프로젝트의 기본 단위는 "엔드포인트 하나"** 이고, 순수 로직(`evaluator`, `privacy`, `dedup`)만
직접 호출하는 단위 테스트를 씁니다. 06·07·09단계에서 본 `Protocol`과 순수 함수 분리가 여기서
값을 합니다.

```python
from app.domains.portfolios.service import CASH_FLOOR_HIGH, CASH_FLOOR_MEDIUM
from app.domains.watchlists.types import BuyReadinessLevel
```

**임계값과 enum을 테스트가 import해서 씁니다.** `0.25` 같은 숫자를 테스트에 다시 적으면 상수를
바꿨을 때 테스트가 조용히 무의미해집니다. 04단계의 "임계값은 정의한 도메인에서 import" 규칙이
테스트에도 적용된 형태입니다.

## 구조를 검증하는 테스트

이 프로젝트에서 가장 특이하고 배울 점이 많은 부분입니다.

### test_alembic_metadata.py — 소스 코드를 AST로 파싱

```python
import ast

def _domain_model_modules() -> set[str]:
    return {
        ".".join(model_path.relative_to(REPO_ROOT).with_suffix("").parts)
        for model_path in DOMAIN_ROOT.glob("**/*model.py")
    }

def _model_registry_imports() -> set[str]:
    parsed = ast.parse(MODEL_REGISTRY.read_text())
    return {alias.name for node in ast.walk(parsed)
            if isinstance(node, ast.Import) for alias in node.names}

def test_model_registry_imports_all_domain_models() -> None:
    ...
```

**`app/domains/**/*model.py` 파일을 전부 찾아, `app/db/models.py`가 그것들을 모두 import하는지
확인합니다.** 03단계에서 "새 모델을 만들면 `app/db/models.py`에 import를 추가해야 하고, 빠뜨리면
마이그레이션이 잘못 생성된다"고 한 규칙이 **테스트로 자동 강제**되는 것입니다.

`ast.parse`로 소스를 파싱하는 이유는, 모듈을 import해서 확인하면 이미 다른 경로로 import된
것까지 잡혀 검증이 무의미해지기 때문입니다. **텍스트로 존재해야만** 통과합니다.

이것이 이 코드베이스에서 가장 인상적인 테스트입니다. 사람이 기억해야 하는 규칙을 기계가
검사하게 만든 사례입니다.

### test_worker_model_registry.py — 별도 프로세스에서 검증

```python
def test_worker_job_import_registers_all_foreign_key_targets() -> None:
    script = textwrap.dedent("""
        import app.worker.jobs.llm_analysis
        from app.db.base import Base

        missing = []
        for table_name, table in sorted(Base.metadata.tables.items()):
            for foreign_key in table.foreign_keys:
                target_table_name = foreign_key.target_fullname.rsplit(".", 1)[0]
                if target_table_name not in Base.metadata.tables:
                    missing.append(...)
        raise SystemExit(1 if missing else 0)
    """)
    result = subprocess.run([sys.executable, "-c", script], capture_output=True)
```

**`subprocess`로 새 파이썬 프로세스를 띄웁니다.** 이유가 중요합니다 — 같은 프로세스에서 실행하면
pytest가 이미 모든 모델을 import한 상태라 검증이 성립하지 않습니다.

검증 내용은 08단계와 연결됩니다. **워커 프로세스는 웹 앱과 import 경로가 다릅니다.** 워커 잡
하나만 import했을 때 그 잡이 다루는 테이블의 모든 FK 대상 테이블이 `Base.metadata`에 등록되는지
확인합니다. 누락되면 워커에서만 `NoReferencedTableError`가 납니다.

**"운영에서만 터지는 버그"를 테스트로 잡는 방법**의 좋은 예입니다.

### test_api_contract.py — 응답 계약 전수 검증

```python
Contract = Mapping[str, type[Any] | tuple[type[Any], ...]]

def assert_envelope(body: Mapping[str, Any], *, has_meta: bool) -> None:
    assert set(body) == {"data", "message", "error", "meta"}
    assert body["message"] is None
    assert body["error"] is None
    if has_meta:
        assert_contract(body["meta"], {"page": int, "size": int, "total": int})
    else:
        assert body["meta"] is None
```

**응답의 필드 이름과 타입을 명시적으로 검증**합니다. `set(body) == {...}`는 필드가 추가되거나
빠져도 잡습니다.

프런트엔드가 소비하는 계약이 조용히 깨지는 것을 막는 장치입니다. `response_model`이 서버 쪽
보장이라면, 이 테스트는 **실제 나가는 JSON**을 검증합니다.

### 마이그레이션 전용 테스트

```text
test_news_category_migration.py
test_raw_processing_status_migration.py
test_signal_key_points_migration.py
```

특정 마이그레이션의 동작을 검증하는 테스트가 따로 있습니다. `client` 픽스처가 `create_all`을
쓰므로 일반 테스트로는 마이그레이션이 검증되지 않는데, 데이터 백필처럼 위험한 마이그레이션만
골라 개별 테스트를 붙인 형태입니다.

## 외부 의존 대체 정리

| 대상 | 방법 | 위치 |
| --- | --- | --- |
| 시장·뉴스·공시·포트폴리오 | `*_PROVIDER=mock` 환경변수 | `conftest.py` 최상단 |
| LLM | `LLM_PROVIDER=mock` + 테스트별 `monkeypatch.setattr(settings, ...)` | conftest + 각 테스트 |
| DB | `dependency_overrides[get_db]` → SQLite | `client` 픽스처 |
| 인증 | `dependency_overrides[get_current_user]` | `set_current_user()` |
| bcrypt | `monkeypatch.setattr` | `stable_password_hashing` |
| Redis | 테스트별 가짜 객체 (`Protocol` 덕분) | 각 테스트 |

**계층마다 대체 방법이 다릅니다.** FastAPI 의존성은 `dependency_overrides`, 팩토리 함수는 설정
변경, 모듈 함수는 `monkeypatch`, `Protocol` 기반은 가짜 객체 주입입니다. 06단계에서 "어댑터
팩토리를 `Depends`로 만들지 않은 대가는 monkeypatch"라고 한 것이 실제로 이렇게 나타납니다.

## 이 단계에서 확인한 프로젝트 규칙

1. `conftest.py`는 앱 import보다 먼저 `*_PROVIDER=mock`을 설정한다. 테스트가 외부에 나가지 않는
   것은 이 순서에 달려 있다.
2. 테스트 DB는 인메모리 SQLite + `StaticPool` + `check_same_thread=False`. 매 테스트마다
   `create_all`/`drop_all`.
3. DB와 인증은 `app.dependency_overrides`로 대체한다. 애플리케이션 코드를 수정하지 않는다.
4. 응답 검증은 `api_data`/`api_meta`/`api_error` 헬퍼로 하고, 봉투 규칙은 헬퍼가 강제한다.
5. 기본 단위는 API 레벨 통합 테스트다. 순수 로직만 직접 호출한다.
6. 임계값·enum은 테스트에서도 도메인에서 import한다. 값을 다시 적지 않는다.
7. `monkeypatch.setattr`는 **사용하는 모듈**의 이름을 패치한다(`app.domains.x.service.f`).
8. 사람이 지켜야 하는 구조 규칙(모델 등록, 워커 import 경로)은 AST 파싱·서브프로세스 테스트로
   자동 검증한다.
9. 검증은 ruff + mypy(strict) + pytest 세 가지를 모두 돌린다.

## 알아둘 만한 한계

- 마이그레이션이 대부분 검증되지 않는다(`create_all` 사용). 개별 마이그레이션 테스트 3개가
  예외다.
- SQLite라 PostgreSQL 전용 동작(트랜잭션 DDL, SAVEPOINT 세부, 동시성 경합)은 검증되지 않는다.
- 04·09단계의 `IntegrityError` 최종 방어 경로는 단위 테스트로 재현하기 어렵다.
- 디렉터리 구분이 없어 100개 파일에서 "빠른 단위 테스트만" 골라 돌리기 어렵다. 마커나 디렉터리
  분리가 있으면 개발 루프가 빨라진다.

## 다음 단계로 이어지는 질문

- 사용자 요청 하나가 계층 전체를 어떻게 통과하는가? (12단계)
- 스케줄 잡 하나가 프로세스를 넘나들며 무엇을 남기는가? (12단계)
