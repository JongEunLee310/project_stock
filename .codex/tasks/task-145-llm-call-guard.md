# Codex Handoff Task

## Source Issue

- BE #209 — 호출 트리거 제한 — 일일 호출 상한 가드·주기 잡 LLM 금지
- Epic BE #141
- 설계: `docs/designs/079-scheduler-cron-and-llm-call-guard.md` Part B (§2·§3.7–3.11·§5 Part B)
- **선행 태스크: task-144 완료 후 같은 브랜치에서 이어 실행한다.**

## Task Summary

`app/adapters/llm/budget.py`에 `DailyCallBudget`을 신설하고 `LLMGateway`에 주입 인터페이스를
추가한다. CLOUD 라우팅 시에만 일일 호출 상한을 소비하며, 상한 초과 시 `LLMBudgetExceededError`를
raise한다. 팩토리는 cloud 모드이고 `LLM_DAILY_CALL_LIMIT` 설정이 있을 때만 budget을 부착한다.
화이트리스트 회귀 단언을 포함해 주기 잡에 LLM 호출 잡이 혼입되지 않음을 검증한다.

## Goal

- `DailyCallBudget.consume()`이 Redis 카운터 `llm:cloud_calls:{YYYYMMDD}`를 INCR하고
  `LLM_DAILY_CALL_LIMIT` 초과 시 `LLMBudgetExceededError`를 raise한다.
- `LLMGateway.complete_json`이 CLOUD 라우팅 시에만 `call_budget.consume()`을 호출한다.
- LOCAL 라우팅 시 budget consume이 호출되지 않는다.
- `LLM_DAILY_CALL_LIMIT=None`이면 budget이 부착되지 않고 호출 상한이 없는 상태로 동작한다.
- task-144에서 추가된 화이트리스트 회귀 테스트(§15 — 주기 잡 LLM 금지)가 계속 통과한다.
- 검증 4종(ruff·mypy·pytest·alembic heads)이 전부 통과한다.

## Background

- 이 태스크는 task-144가 완료된 `feature/scheduler-cron-llm-call-guard` 브랜치에서 이어
  실행된다. task-144 산출물(`app/scheduler/cron_config.py` 등)에 직접 의존하지 않지만
  같은 PR로 묶인다.
- #206 수렴 이후 모든 LLM 호출이 `LLMGateway.complete_json`으로 집중되었다.
  `LLMGateway.complete_json`은 `router.resolve(task_type)`로 provider(CLOUD/LOCAL)를
  결정하고 CLOUD일 때만 PrivacyGate를 적용한다(`app/adapters/llm/gateway.py`·`router.py`
  참조).
- 지침 §15: LLM 호출 트리거는 초기 단계에서 "사용자 직접 분석 요청·수동 ContextBundle
  생성"만 허용하며, 주기 잡의 자동 LLM 호출은 이후 단계다. §16: Redis 도입 시점에
  API rate limit 관리가 명시된다.
- `app/adapters/llm/exceptions.py`에 `LLMCallError`(베이스)·`CloudBoundaryViolationError`·
  `LLMTimeoutError`·`LLMRoutingError`가 있다. `LLMBudgetExceededError`를 `LLMCallError`
  하위로 추가한다.
- `app/core/config.py`에 `REDIS_URL`·`LLM_TIMEOUT_SECONDS`·`LLM_PROVIDER`가 있다.
  `LLM_DAILY_CALL_LIMIT: int | None = None`을 추가한다.
- Redis 연결: `app/worker/connection.py::get_redis_connection()`.
- 팩토리: `app/adapters/factory.py::get_llm_gateway()`가 `LLM_PROVIDER`(cloud/local/mock)에
  따라 클라이언트 매핑을 조립한다.
- Decision HHH: budget.py 신설, exceptions.py 예외 추가, config.py 설정 추가,
  gateway.py budget 파라미터·CLOUD 시 consume, factory.py 부착 로직, 화이트리스트
  회귀 포함.

## Implementation Scope

1. `app/adapters/llm/budget.py` (신규) — `DailyCallBudget` 클래스:
   - `__init__(self, redis, limit: int)`: Redis 연결과 상한 값을 보관한다.
   - `consume(self) -> None`: 키 `llm:cloud_calls:{YYYYMMDD}`(UTC) INCR 후 상한 초과 시
     `LLMBudgetExceededError` raise. 첫 INCR 시 TTL 2일 설정.
2. `app/adapters/llm/exceptions.py` — `LLMBudgetExceededError(LLMCallError)` 추가.
3. `app/core/config.py` — `LLM_DAILY_CALL_LIMIT: int | None = None` 추가.
4. `app/adapters/llm/gateway.py` — `LLMGateway.__init__`에
   `call_budget: DailyCallBudget | None = None` 추가. `complete_json` 내부에서
   `router.resolve(task_type)`가 CLOUD를 반환하고 `call_budget`이 부착된 경우에만
   `call_budget.consume()` 호출.
5. `app/adapters/factory.py` — `get_llm_gateway()`: `LLM_PROVIDER == "cloud"` 이고
   `LLM_DAILY_CALL_LIMIT`이 `None`이 아닌 경우에만
   `DailyCallBudget(get_redis_connection(), settings.LLM_DAILY_CALL_LIMIT)`를 생성해
   `LLMGateway`에 부착한다. mock·local 모드에는 budget을 부착하지 않는다.
6. `.env.example` — `LLM_DAILY_CALL_LIMIT=` 항목 추가.
7. 테스트:
   - `DailyCallBudget` 단위 테스트: fake redis 스텁(INCR·EXPIRE를 흉내 내는 단순 객체)
     주입, 상한 이하 정상 통과·초과 시 `LLMBudgetExceededError` raise 검증. fakeredis
     패키지 미사용, 단순 스텁 주입. `AsyncMock` 사용 금지(sync 코드베이스).
   - 게이트웨이 상한 테스트: `MockLLMClient`로 조립한 실제 `LLMGateway` + fake budget
     스텁, CLOUD 라우팅 시 `consume` 호출, LOCAL 라우팅 시 미호출 단언.
8. `docs/backend-v0.2.md` — `LLM_DAILY_CALL_LIMIT` 환경 변수 설명 추가.

## Out of Scope

- `app/scheduler/`(task-144 산출물) 변경.
- `app/adapters/llm/router.py`·`app/adapters/llm/privacy.py`·프롬프트 지시문 변경.
- 도메인 서비스 비즈니스 로직 변경(주입만 허용).
- 기존 alembic versions 변경.
- DB 스키마 변경·migration 생성.

## Protected Files

- `app/scheduler/` — 변경 금지(task-144 산출물).
- `app/adapters/llm/router.py` — 변경 금지.
- `app/adapters/llm/privacy.py` — 변경 금지.
- `app/adapters/llm/prompts/` — 변경 금지.
- `app/domains/` — 변경 금지.
- `alembic/versions/` — 변경 금지.

## Requirements

- `LLM_DAILY_CALL_LIMIT=None`이면 budget이 부착되지 않고 무제한으로 동작한다.
- CLOUD 이외 provider(mock·local)는 budget consume을 호출하지 않는다.
- `LLMBudgetExceededError`가 `LLMCallError` 하위 타입이다.
- 키 TTL이 2일로 설정된다(자정이 지나도 어제 카운터가 바로 만료되지 않도록 여유를 둔다).
- 타입 힌트 완전성(mypy 통과 수준).
- 주석은 WHY가 명확하지 않을 때만 최소한으로.

## Test Requirements

- `DailyCallBudget.consume()` 단위 테스트: 상한 이하 통과·초과 시 예외 발생. fake 스텁
  주입(fakeredis 패키지 사용 금지).
- 게이트웨이 상한 테스트: CLOUD 시 consume 호출, LOCAL 시 미호출.
- task-144에서 추가된 화이트리스트 회귀 테스트가 계속 통과함(신규 작성 아님).
- 기존 테스트 전부 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## Documentation Impact

`docs/backend-v0.2.md` — `LLM_DAILY_CALL_LIMIT` 환경 변수 추가. `.env.example`.
설계 `docs/designs/079-scheduler-cron-and-llm-call-guard.md`는 이 PR에 동봉된다.

## ADR Need

없음 — 설계 079 §6 참조.

## Failure Record Need

없음 — 계획된 사전 예방적 가드 구현이며 결함 마감이 아니다.

## Risk Level

낮음. `LLMGateway` 생성자에 optional 파라미터를 추가하는 방식이므로 기존 경로에 영향이
없다. budget이 `None`이면 consume을 호출하지 않으므로 기본 동작은 그대로 보존된다.

## Expected Output

- 신규: `app/adapters/llm/budget.py`, 신규 테스트 파일.
- 수정: `app/adapters/llm/exceptions.py`, `app/core/config.py`,
  `app/adapters/llm/gateway.py`, `app/adapters/factory.py`, `.env.example`,
  `docs/backend-v0.2.md`.
- 검증 4종 통과.

## Decisions 요약 (설계 079 참조)

- HHH: `DailyCallBudget`(Redis 카운터, TTL 2일)으로 cloud 일일 호출 상한 가드. CLOUD
  라우팅 시에만 consume. 팩토리에서 cloud 모드·limit 설정 시에만 budget 부착.
  화이트리스트 회귀 포함(middleware 레이어 가드·게이트웨이 내부 직접 구현 기각).

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 브랜치(`feature/scheduler-cron-llm-call-guard`)를 유지한다. 커밋하지 않는다.
