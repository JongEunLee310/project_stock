# Codebase Tour

`app/main.py`를 시작점으로 백엔드 전체 코드를 단계별로 읽어 나간 기록입니다. 한 단계당 3~6개
파일을 다루고, 핵심 파일은 라인 단위로, 반복 패턴 파일은 역할과 호출 흐름 중심으로 정리했습니다.
프레임워크(FastAPI·Starlette·Pydantic·SQLAlchemy) 설명은 별도 문서로 빼지 않고, 해당 코드가
나오는 자리에 함께 담았습니다.

기준 버전: FastAPI 0.137.1 / Starlette 1.3.1 / Pydantic 2.13.4 / SQLAlchemy 2.0.51

## 코드베이스 지형

`app/` 기준 321개 파일, 약 28,000줄, 38개 도메인, 43개 마이그레이션, 100개 테스트 파일.

| 층 | 위치 | 역할 |
| --- | --- | --- |
| Bootstrap | `app/main.py`, `app/core/` | 앱 조립, 미들웨어, 예외 핸들러, 설정·로깅 |
| Routing | `app/api/v1/` | 라우터, 의존성 주입, 엔드포인트 |
| Domain | `app/domains/<name>/` | `endpoint → service → repository → model` 수직 슬라이스 |
| Data | `app/db/`, `alembic/` | 세션, ORM base, 마이그레이션 |
| External | `app/adapters/` | 시장·뉴스·공시·LLM 연동 |
| Async | `app/scheduler/`, `app/worker/` | 크론, 큐 잡 |

프로세스는 셋입니다 — `backend`(uvicorn), `worker`(rq worker), `scheduler`(rq cron). 코드베이스는
하나이고 Redis와 PostgreSQL을 공유합니다.

## 단계 목록

### Part 1 — 뼈대

- [01. 부트스트랩과 횡단 관심사](01-bootstrap.md) — `main.py`, `core/`
  ASGI, 미들웨어 스택 조립 순서, 예외 핸들러 두 갈래, 응답 봉투, ContextVar 요청 ID
- [02. 라우팅과 의존성](02-routing-and-dependencies.md) — `api/v1/`, `core/security.py`, `domains/users/`
  APIRouter 중첩, `Depends` 그래프, `yield` 의존성, JWT, `def` vs `async def`, 도메인 4파일 구조
- [03. 데이터 층](03-data-layer.md) — `db/`, `alembic/`
  엔진·세션 옵션, `Base.metadata`, `TimestampMixin`, 모델 레지스트리, 리비전 체인과 merge

### Part 2 — 도메인 패턴

- [04. 수직 슬라이스 표준형](04-domain-slice-watchlists.md) — `domains/watchlists/`
  소유권 검사, 중복 2겹 방어, 스키마 명명 규칙, `Annotated[X, Depends()]`, N+1의 실재
- [05. 조회와 수집 슬라이스](05-assets-and-prices.md) — `domains/assets/`, `prices/`, `raw_prices/`
  원본·가공 테이블 분리, 수집 파이프라인 4단계, 해시 중복 제거, 품질 검증
- [06. 어댑터 층](06-adapters.md) — `adapters/market/`, `news/`, `disclosure/`
  `base`/`mock`/`real` 삼각 구조, 인터페이스 분리, 캐시 데코레이터, 결정적 mock

### Part 3 — 확장 층

- [07. LLM 층](07-llm-layer.md) — `adapters/llm/`
  게이트웨이 6단계 정책, `CloudSafePayload` 개인정보 경계, 구간화, 캐시 키, 프롬프트 관리
- [08. 백그라운드 실행](08-background-execution.md) — `worker/`, `scheduler/`, `domains/jobs/`
  프로세스 3개, RQ 잡 골격, `JobRun` 기록, cron 시간표(UTC), Redis 레이트 리밋
- [09. 파생과 판정 도메인](09-signals-and-alerts.md) — `domains/signals/`, `alert_engine/`
  우선순위 튜플, 스냅샷 테이블, 조건 JSON 인터프리터, 중복 억제 4겹, `begin_nested()`
- [10. 대형 도메인](10-large-domains.md) — `news_insights/`, `decision_logs/`, `research_*`
  3층 파이프라인, 단계별 실행 기록, Record dataclass, 상태 머신, `superseded_by_id`

### Part 4 — 종합

- [11. 테스트 지형](11-tests.md) — `tests/`
  conftest 순서의 중요성, `dependency_overrides`, SQLite 한계, AST로 구조 검증
- [12. 엔드투엔드 추적](12-end-to-end.md)
  사용자 요청 1건과 스케줄 잡 1건 전체 추적, 관통 원칙 10가지, 성숙도 편차 표

## 자주 참조할 지점

| 알고 싶은 것 | 문서 |
| --- | --- |
| 500인데 CORS 에러로 보이는 이유 | [01](01-bootstrap.md) |
| 엔드포인트를 `async def`로 쓰면 안 되는 이유 | [02](02-routing-and-dependencies.md) |
| 새 모델 추가 시 빠뜨리면 안 되는 것 | [03](03-data-layer.md) |
| 새 도메인의 표준 골격 | [04](04-domain-slice-watchlists.md) |
| 새 외부 연동 붙이는 법 | [06](06-adapters.md) |
| 새 LLM 기능 추가 절차 | [07](07-llm-layer.md) |
| 새 배치 잡 추가 절차 | [08](08-background-execution.md) |
| 테스트가 외부에 나가지 않는 이유 | [11](11-tests.md) |
| 전체 원칙과 개선 대상 | [12](12-end-to-end.md) |
