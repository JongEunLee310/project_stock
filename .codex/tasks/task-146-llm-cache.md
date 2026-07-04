# Codex Handoff Task

## Source Issue

- BE #138 — LLM Cache
- Epic BE #141
- 설계: `docs/designs/080-llm-cache.md` (§2·§3·§4·§5 전체)

## Task Summary

`app/adapters/llm/cache.py`에 `LLMCache`를 신설하고 `LLMGateway`에 생성자 주입 인터페이스를
추가한다. `complete_json`에 `cache_policy`·`user_id` 파라미터를 추가해 브리핑 호출을
`READ_WRITE` 캐시로 opt-in한다. ADR-011을 `Accepted`로 승격한다.

## Goal

- `LLMCache`가 Redis를 백엔드로 삼아 `get_cached`/`put`을 수행한다.
- `compute_key`가 task_type·user_id·snapshot_hash·prompt_version·model_policy_version·
  output_schema_version·date 재료로 sha256 키를 결정론적으로 산출한다.
- `LLMGateway.complete_json`이 `cache_policy != BYPASS`이고 cache가 부착된 경우 privacy
  guard(cloud 경로) 통과 후 키를 산출해 조회하며, hit이면 budget consume·client 호출 없이
  저장된 envelope을 복원해 즉시 반환한다.
- `cache_policy=READ_WRITE`일 때 miss 후 결과를 저장하고, `READ_ONLY`는 저장을 생략한다.
- `LLMCompletionResult.cache_hit`이 hit 여부를 반환한다.
- `PortfolioBriefingService`·`DashboardBriefingService`가 `cache_policy=READ_WRITE`로 opt-in한다.
- ADR-011이 `Accepted` 상태로 갱신된다.
- 검증 4종(ruff·mypy·pytest·alembic heads)이 전부 통과한다.

## Background

- #206 수렴 이후 모든 LLM 호출이 `LLMGateway.complete_json`으로 집중된다
  (`app/adapters/llm/gateway.py`).
- `DailyCallBudget`(`app/adapters/llm/budget.py`)이 Redis 주입 패턴 선례를 제공한다.
  `RedisCounter` Protocol(incr·expire)와 동형이나 `RedisCache` Protocol(get·setex)은
  독립 선언한다.
- `CachePolicy` enum(BYPASS·READ_WRITE·READ_ONLY)이 `app/adapters/llm/types.py`에 이미
  정의되어 있으나 `complete_json` 파라미터로 연결되지 않았다.
- `LLMCompletionResult`는 `app/adapters/llm/gateway.py`에 frozen dataclass로 정의되어 있다.
  `cache_hit: bool = False`를 추가한다. 기본값이 있으므로 기존 생성 코드는 무변경이다.
- `LLM_MODEL_POLICY_VERSION` 상수를 `app/adapters/llm/router.py`에 추가한다.
  라우팅 테이블(`LLM_TASK_ROUTES`)은 변경하지 않는다.
- `.env.example`에 `LLM_CACHE_TTL_SECONDS=` 항목을 추가하고, `app/core/config.py`에
  해당 설정 필드를 추가한다(`LLM_DAILY_CALL_LIMIT`과 동일한 empty-string-to-None 파싱 패턴).
- factory.py: `LLM_CACHE_TTL_SECONDS is not None`이고 `LLM_PROVIDER != "mock"`인 경우에만
  `LLMCache`를 부착한다.
- 브리핑 서비스 opt-in: `PortfolioBriefingService.generate`와 `DashboardBriefingService.generate`의
  `complete_json` 호출에 `cache_policy=CachePolicy.READ_WRITE`, `user_id=user_id`를 전달한다.
  두 파일 이외 도메인 파일은 변경하지 않는다.
- ADR-011 확정 처리: 설계 §6 참조. Status를 `Proposed — Deferred` → `Accepted`로 승격하고
  미결 질문 3개에 확정 답을 반영한다.

## Implementation Scope

1. `app/adapters/llm/cache.py` (신규)
   - `RedisCache` Protocol: `get(name: str) -> str | None`, `setex(name: str, time: int, value: str) -> object`
   - `LLMCache.__init__(self, redis: RedisCache, ttl: int)`
   - `LLMCache.compute_key(self, task_type: LLMTaskType, user_id: int | None, payload: CloudSafePayload, system_prompt: str, schema: type[BaseModel], model_policy_version: str, on_date: date | None = None) -> str`: sha256 다이제스트 반환, 키 형식 `llm:cache:{digest}`. `on_date`가 `None`이면 UTC 오늘 날짜를 사용한다(테스트는 인자 주입으로 날짜를 고정한다)
   - `LLMCache.get_cached(self, key: str) -> str | None`
   - `LLMCache.put(self, key: str, value: str) -> None`
2. `app/adapters/llm/gateway.py` (수정)
   - `LLMCompletionResult`: `cache_hit: bool = False` 필드 추가
   - `LLMGateway.__init__`: `cache: LLMCache | None = None` 파라미터 추가
   - `LLMGateway.complete_json`: `cache_policy: CachePolicy = CachePolicy.BYPASS`, `user_id: int | None = None` 추가 및 캐시 흐름 구현. 실행 순서(설계 §4 Decision LLL): ① provider resolve → ② privacy guard(cloud 경로) → ③ 캐시 조회(hit이면 즉시 반환) → ④ miss 시 budget consume(cloud 경로)·client 호출 → ⑤ `READ_WRITE`면 저장. 캐시 값은 `{"output": ..., "provider": ..., "model_name": ...}` JSON envelope 문자열로 게이트웨이가 직렬화·역직렬화하며, hit 시 envelope의 provider·model_name을 복원해 `LLMCompletionResult(cache_hit=True, ...)`를 반환한다
3. `app/adapters/llm/router.py` (수정)
   - `LLM_MODEL_POLICY_VERSION: str = "v1"` 모듈 상수 추가
4. `app/adapters/llm/__init__.py` (수정)
   - `LLMCache` 임포트·익스포트 추가
5. `app/adapters/factory.py` (수정)
   - `get_llm_gateway()`: `settings.LLM_CACHE_TTL_SECONDS is not None`이고 mock 모드가
     아닌 경우 `LLMCache(get_redis_connection(), settings.LLM_CACHE_TTL_SECONDS)` 생성 후
     `LLMGateway`에 `cache=` 전달
6. `app/core/config.py` (수정)
   - `LLM_CACHE_TTL_SECONDS: int | None = None` 추가. `LLM_DAILY_CALL_LIMIT`과 동일한
     empty-string-to-None validator 적용
7. `app/domains/portfolios/briefing_service.py` (수정)
   - `complete_json` 호출에 `cache_policy=CachePolicy.READ_WRITE`, `user_id=user_id` 전달
8. `app/domains/dashboard/briefing_service.py` (수정)
   - `complete_json` 호출에 `cache_policy=CachePolicy.READ_WRITE`, `user_id=user_id` 전달
9. `docs/decisions/ADR-011-llm-cache-policy.md` (수정)
   - Status: `Proposed — Deferred` → `Accepted`
   - Decision 섹션 미결 질문 3개에 확정 답 반영(설계 §6)
   - Alternatives·Consequences·Follow-up 갱신
10. 테스트: `tests/test_llm_cache.py` (신규) 및 `tests/test_llm_gateway.py` (캐시 케이스 추가)
11. `docs/backend-v0.2.md` — `LLM_CACHE_TTL_SECONDS` 환경 변수 설명 추가

## Out of Scope

- 브리핑 이외 호출부(news·thesis·watchlist·llm_analysis)의 `cache_policy` 변경 — BYPASS 유지.
- `app/adapters/llm/router.py` 라우팅 테이블(`LLM_TASK_ROUTES`) 변경.
- `app/adapters/llm/privacy.py` 화이트리스트 변경.
- alembic migration 신규 생성.
- 관측 지표(메트릭·로깅 추가).
- `LLMResponse`(types.py) 구조 변경 또는 `LLMCompletionResult`와 통합.

## Protected Files

- `app/adapters/llm/privacy.py` — 변경 금지.
- `app/adapters/llm/router.py`의 `LLM_TASK_ROUTES` — 라우팅 테이블 내용 변경 금지
  (`LLM_MODEL_POLICY_VERSION` 상수 추가만 허용).
- `app/adapters/llm/prompts/` — 변경 금지.
- `alembic/versions/` — 변경 금지.
- 브리핑 서비스 이외 `app/domains/` 파일 — 변경 금지.

## Requirements

- `LLM_CACHE_TTL_SECONDS=None`이면 `LLMCache`가 부착되지 않고 캐시 없는 동작이 보존된다.
- mock 모드에는 `LLMCache`를 부착하지 않는다.
- cache hit 시 `call_budget.consume()`과 `client.complete_json`이 호출되지 않는다.
- privacy guard(cloud 경로)는 캐시 조회보다 먼저 수행된다 — 비 CloudSafe payload는
  `cache_policy=READ_WRITE`여도 키 산출 전에 `CloudBoundaryViolationError`로 거부된다.
- cache hit 시 envelope에 저장된 provider·model_name이 `LLMCompletionResult`로 복원된다.
- `BYPASS` policy에서는 `cache`가 부착되어 있어도 `get_cached`를 호출하지 않는다.
- `LLMCompletionResult.cache_hit`이 hit 시 `True`, miss·BYPASS 시 `False`이다.
- `compute_key`가 동일 입력에 대해 결정론적으로 동일 키를 반환한다.
- `system_prompt`·`schema`·`model_policy_version` 변경 시 키가 달라진다.
- 브리핑 서비스에서 `CachePolicy`를 `app.adapters.llm` 패키지에서 임포트한다.
- 타입 힌트 완전성(mypy 통과 수준).
- 주석은 WHY가 명확하지 않을 때만 최소한으로.

## Test Requirements

`AsyncMock` 사용 금지(sync 코드베이스). `fakeredis` 패키지 사용 금지, 단순 스텁 주입.

### `tests/test_llm_cache.py` (신규)

- fake Redis 스텁 — `get`·`setex`를 흉내 내는 단순 dict 기반 객체를 직접 정의한다.
- miss — 빈 스텁에서 `get_cached` 호출 시 `None` 반환.
- put → hit — `put` 후 `get_cached`가 동일 값 반환.
- TTL 전달 — `put` 시 스텁의 `setex`가 올바른 ttl 값으로 호출됨.
- 결정론 — 동일 입력으로 `compute_key` 두 번 호출 시 동일 키.
- prompt 민감도 — `system_prompt` 변경 시 다른 키.
- schema 민감도 — schema 필드 변경 시 다른 키.
- 날짜 버킷 — `on_date` 인자에 다른 날짜를 주입하면 다른 키.

### `tests/test_llm_gateway.py` (추가)

기존 `SpyLLMClient`·`SpyCallBudget` 패턴에 준하는 fake `LLMCache` 스텁을 정의한다.

- BYPASS policy — cache 부착 상태에서 `BYPASS`이면 `get_cached` 미호출.
- READ_WRITE miss — `client.complete_json` 호출됨, `cache.put` 호출됨.
- READ_WRITE hit — `client.complete_json`·`call_budget.consume` 미호출, `result.cache_hit == True`,
  envelope의 provider·model_name 복원됨.
- READ_ONLY hit — `client.complete_json`·`call_budget.consume`·`cache.put` 미호출.
- READ_ONLY miss — `client.complete_json` 호출됨, `cache.put` 미호출.
- budget 비소비 — cache hit 시 `SpyCallBudget.calls == 0`.
- guard 선행 — cloud 경로에서 비 CloudSafe payload는 `cache_policy=READ_WRITE`여도
  `get_cached` 호출 전에 `CloudBoundaryViolationError`로 거부됨.
- 회귀 — `cache=None`이면 기존 동작 그대로(`cache_hit=False`).

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## Documentation Impact

- `docs/decisions/ADR-011-llm-cache-policy.md` — Status 승격 및 내용 갱신(Implementation Scope #9).
- `docs/designs/080-llm-cache.md` — 이 태스크의 설계 문서. 수정 불필요.
- `docs/backend-v0.2.md` — `LLM_CACHE_TTL_SECONDS` 환경 변수 설명 추가.
- `.env.example` — `LLM_CACHE_TTL_SECONDS=` 항목 추가.

## ADR Need

없음. ADR-011 승격으로 충족. 신규 아키텍처 방향을 추가로 결정하지 않는다.

## Failure Record Need

없음. 계획된 기능 구현이다.

## Risk Level

낮음. `LLMGateway` 생성자와 `complete_json`에 기본값이 있는 optional 파라미터를 추가하는
방식이므로 기존 호출부에 영향이 없다. `cache=None`이면 현행 동작이 그대로 보존된다.
브리핑 서비스 opt-in 두 파일만 도메인 영역 수정이며, 변경 범위가 명확하게 제한된다.

## Expected Output

- 신규: `app/adapters/llm/cache.py`, `tests/test_llm_cache.py`.
- 수정: `app/adapters/llm/gateway.py`, `app/adapters/llm/router.py`,
  `app/adapters/llm/__init__.py`, `app/adapters/factory.py`, `app/core/config.py`,
  `app/domains/portfolios/briefing_service.py`,
  `app/domains/dashboard/briefing_service.py`,
  `docs/decisions/ADR-011-llm-cache-policy.md`,
  `docs/backend-v0.2.md`.
- 검증 4종 통과.

## Decisions 요약 (설계 080 참조)

- **III**: `LLMCache`를 `cache.py`에 신설, `LLMGateway`에 `cache: LLMCache | None = None` 생성자 주입. Redis 백엔드, `RedisCache` Protocol 독립 선언.
- **JJJ**: sha256(task_type + user_id + snapshot_hash + prompt_version + model_policy_version + output_schema_version + date), 키 형식 `llm:cache:{digest}`.
- **KKK**: prompt_version·output_schema_version 자동 무효화, model_policy_version 수동 bump. 조용한 stale 없음.
- **LLL**: `CachePolicy` 실사용, `complete_json`에 `cache_policy`·`user_id` 추가(기본 BYPASS). guard → 캐시 조회 → budget 순서, hit 시 budget consume·client 호출 생략, JSON envelope로 provider·model_name 복원.
- **MMM**: `LLM_CACHE_TTL_SECONDS`(None=비활성), date 버킷 일 단위 롤오버, mock 모드 미부착.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 브랜치(`experiment/138-llm-cache-opus`) 유지. 커밋하지 않는다. 새 의존성 추가 금지.
