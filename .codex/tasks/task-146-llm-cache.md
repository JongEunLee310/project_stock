# Codex Handoff Task

## Source Issue

- BE #138 — LLM Cache — snapshot hash 키·TTL·prompt/model version 무효화
- Epic BE #141
- 설계: `docs/designs/080-llm-response-cache.md` (Decisions III·JJJ·KKK·LLL)

## Task Summary

`app/adapters/llm/cache.py`에 `LLMResponseCache`를 신설하고 `LLMGateway`의 CLOUD
경로에 lookup/store를 추가한다. 키는 payload·system_prompt·model_name·schema의
단방향 해시 + task_type + UTC 날짜로 구성한다. `LLM_CACHE_TTL_SECONDS` 설정이 있고
cloud 모드일 때만 팩토리가 캐시를 부착한다. ADR-011을 Accepted로 확정 갱신한다.

## Goal

- 동일 (task_type, payload, system_prompt, model, schema, UTC 날짜) 입력의 두 번째
  CLOUD 호출이 클라이언트 호출 없이 캐시에서 복원되고 `cached=True`로 표시된다.
- 캐시 히트 시 `DailyCallBudget.consume()`이 호출되지 않는다.
- payload·system_prompt·model_name·schema 중 하나라도 바뀌면 키가 달라진다(무효화).
- `LLM_CACHE_TTL_SECONDS` 미설정 시 캐시가 부착되지 않고 기존 동작이 보존된다.
- LOCAL 라우팅에는 캐시가 적용되지 않는다.
- 검증 4종(ruff·mypy·pytest·alembic heads)이 전부 통과한다.

## Background

- 모든 LLM 호출은 `LLMGateway.complete_json(task_type, payload, schema, system_prompt)`
  단일 경로다(`app/adapters/llm/gateway.py`). CLOUD 라우팅 시
  `privacy_gate.guard` → `call_budget.consume`(부착 시) → `client.complete_json` 순.
- payload는 전부 `CloudSafePayload`(frozen pydantic, `as_payload()` → dict,
  `app/adapters/llm/privacy.py`). 캐시 키 재료는 이 projection 범위로 제한한다
  (ADR-011 제약 — 키 재료 = 클라우드 전송 페이로드 화이트리스트).
- Redis 연결: `app/worker/connection.py::get_redis_connection()`. budget이 이미
  같은 패턴을 쓴다(`app/adapters/llm/budget.py`의 `RedisCounter` Protocol 참조).
- `LLMCompletionResult`는 `output: dict`, `provider: str`, `model_name: str` frozen
  dataclass. 여기에 `cached: bool = False`를 추가한다.
- config의 `LLM_DAILY_CALL_LIMIT`에 `""` → `None` field_validator 선례가 있다
  (`app/core/config.py`). `LLM_CACHE_TTL_SECONDS`도 같은 방식으로 처리한다.
- ADR-011(`docs/decisions/ADR-011-llm-cache-policy.md`)은 Proposed — Deferred
  상태다. Status를 Accepted로 올리고 Decision 절을 설계 080의 확정 내용(키 스킴·
  Redis·전역 TTL·CLOUD 전용·budget 선후 관계)으로 갱신한다. 본문 산문은 한국어,
  헤더·코드 기호는 영어.

## Implementation Scope

1. `app/adapters/llm/cache.py` (신규):
   - `RedisCacheStore` Protocol — `get(name) -> str | bytes | None`,
     `set(name, value, ex) -> object`.
   - `CachedCompletion` frozen dataclass — `output: dict`, `provider: str`,
     `model_name: str`.
   - `LLMResponseCache`:
     - `__init__(redis: RedisCacheStore, ttl_seconds: int)`
     - `build_key(task_type, payload, system_prompt, model_name, schema) -> str` —
       `llm:cache:{task_type.value}:{YYYYMMDD(UTC)}:{digest}`. digest는
       payload canonical JSON(`json.dumps(payload.as_payload(), sort_keys=True,
       ensure_ascii=False)`)·system_prompt·model_name·`json.dumps(schema.model_json_schema(),
       sort_keys=True)`를 이어붙인 문자열의 sha256 hexdigest.
     - `lookup(key) -> CachedCompletion | None` — 값 없음·JSON 역직렬화 실패·필수
       필드 결손은 모두 `None`(miss).
     - `store(key, output, provider, model_name) -> None` — JSON 직렬화 후
       `set(..., ex=ttl_seconds)`.
2. `app/adapters/llm/gateway.py`:
   - `__init__`에 `response_cache: LLMResponseCache | None = None` 추가.
   - CLOUD 경로: guard 통과 후 캐시가 부착되어 있으면 `build_key`·`lookup`. 히트 시
     budget 소비·클라이언트 호출 없이 `LLMCompletionResult(..., cached=True)` 반환.
     miss 시 기존 흐름 수행 후 `store`.
   - `LLMCompletionResult`에 `cached: bool = False` 추가.
   - LOCAL 경로는 캐시를 조회하지 않는다.
3. `app/core/config.py` — `LLM_CACHE_TTL_SECONDS: int | None = None` +
   `""` → `None` field_validator (기존 validator에 필드 추가 방식 허용).
4. `app/adapters/factory.py` — `get_llm_gateway()` cloud 분기에서
   `LLM_CACHE_TTL_SECONDS`가 `None`이 아닐 때만
   `LLMResponseCache(get_redis_connection(), settings.LLM_CACHE_TTL_SECONDS)` 부착.
   mock·local 분기는 변경하지 않는다.
5. `.env.example` — `LLM_CACHE_TTL_SECONDS=` 항목 추가(빈 값 = 캐시 비활성, cloud
   모드에만 적용된다는 주석 포함).
6. `docs/decisions/ADR-011-llm-cache-policy.md` — Status `Accepted` 갱신, Decision
   절에 확정 내용 반영, Follow-up의 "#138 착수 대기" 문구를 구현 완료로 갱신.
7. `docs/backend-v0.2.md` — `LLM_CACHE_TTL_SECONDS` 환경 변수 설명 추가.

## Out of Scope

- 도메인 서비스(호출부) 변경 — 캐시는 게이트웨이 내부 관심사.
- 캐시 관리·수동 무효화 API, 작업별 TTL, hit/miss 메트릭 수집 인프라.
- `app/adapters/llm/router.py`·`privacy.py`·`budget.py`·프롬프트 지시문 변경.
- DB 스키마 변경·migration 생성.

## Protected Files

- `app/adapters/llm/router.py` — 변경 금지.
- `app/adapters/llm/privacy.py` — 변경 금지.
- `app/adapters/llm/budget.py` — 변경 금지.
- `app/adapters/llm/prompts/` — 변경 금지.
- `app/domains/` — 변경 금지.
- `app/scheduler/` — 변경 금지.
- `alembic/versions/` — 변경 금지.

## Requirements

- Redis `get`/`set` 예외·역직렬화 실패는 miss로 처리하고 실 호출로 진행한다 — 캐시
  장애가 LLM 호출 실패로 전파되면 안 된다.
- 키 digest 재료는 CloudSafe payload·프롬프트·모델명·스키마로 한정한다. user_id 등
  내부 식별자를 키에 넣지 않는다(설계 Decision III).
- 캐시 히트 경로에서 `call_budget.consume()`이 호출되지 않는다(설계 Decision KKK).
- 타입 힌트 완전성(mypy 통과 수준). 주석은 WHY가 명확하지 않을 때만 최소한으로.

## Test Requirements

- `LLMResponseCache` 단위(fake Redis 스텁 주입, fakeredis 미사용, `AsyncMock` 금지):
  키 결정성, payload·prompt·model·schema 각각 변경 시 키 변화, store → lookup 왕복,
  손상 값·빈 값 miss 처리, `set`에 TTL 전달 검증.
- 게이트웨이: CLOUD 히트 시 클라이언트 미호출·budget 미소비·`cached=True` 반환,
  miss 시 클라이언트 호출·store 수행, LOCAL 라우팅 시 캐시 미조회, Redis 예외 시
  실 호출 폴백.
- 팩토리: TTL 설정+cloud일 때만 부착, 미설정 시 미부착. config: `""` → `None` 파싱.
- 기존 테스트 전부 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## Documentation Impact

`docs/decisions/ADR-011-llm-cache-policy.md`(Accepted 확정), `docs/backend-v0.2.md`,
`.env.example`. 설계 `docs/designs/080-llm-response-cache.md`는 이 PR에 동봉된다.

## ADR Need

신규 ADR 불필요 — ADR-011 확정 갱신이 본 작업의 일부다(설계 080 Decision LLL).

## Failure Record Need

없음 — 계획된 Phase 2 구현이며 결함 마감이 아니다.

## Risk Level

낮음. `LLMGateway` 생성자 optional 파라미터 추가 방식이므로 캐시 미설정 시 기존
경로가 그대로 보존된다. 캐시 장애는 miss 폴백으로 흡수된다.

## Expected Output

- 신규: `app/adapters/llm/cache.py`, 신규 테스트 파일.
- 수정: `app/adapters/llm/gateway.py`, `app/core/config.py`,
  `app/adapters/factory.py`, `.env.example`,
  `docs/decisions/ADR-011-llm-cache-policy.md`, `docs/backend-v0.2.md`.
- 검증 4종 통과.

## Decisions 요약 (설계 080 참조)

- III: 키 = task_type + UTC 날짜 + sha256(payload·prompt·model·schema). 버전 상수
  대신 본문 해시로 자동 무효화. user_id 미포함.
- JJJ: Redis 저장, 전역 단일 TTL(`LLM_CACHE_TTL_SECONDS`), 미설정 시 비활성.
- KKK: CLOUD 전용, lookup은 budget consume보다 먼저, 히트 시 `cached=True` 복원,
  캐시 장애는 miss 폴백.
- LLL: ADR-011 Status Accepted 확정 갱신.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 브랜치(`experiment/138-llm-cache-fable`)를 유지한다. 커밋하지 않는다.
