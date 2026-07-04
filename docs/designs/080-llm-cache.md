# 080 · LLM 캐시

Status: Draft
작성: Claude Code (orchestrator · VFF 초안)
관련: BE #138 (LLM Cache), Epic BE #141
지침 근거: ADR-011(LLM 캐시 정책), ADR-007(LLM Provider Abstraction), ADR-009(Cloud Data Boundary / CloudSafe Projection), 스펙 §6/§16

---

## 1. 배경

클라우드 LLM 호출은 비용과 지연을 수반한다. 포트폴리오·대시보드 브리핑은 동일 스냅샷에 대해
반복적으로 같은 결과를 생성하는 구조이므로, 결과를 캐시하면 호출 횟수와 비용을 줄일 수 있다.

ADR-011은 캐시 구현 시점을 "브리핑 기능 설계 착수"로 유보했으며, PR #151에서 포트폴리오·
대시보드 브리핑 기능이 완료되어 풀구현 트리거가 충족되었다. 이슈 #138은 이 시점에 맞춰
캐시 계층을 게이트웨이 내부에 추가한다(ADR-007 계층 분리 유지).

`DailyCallBudget`(`budget.py`)이 Redis 주입 선례를 제공하므로 그 패턴을 따른다.

## 2. 범위

### 포함

- `app/adapters/llm/cache.py` 신규: `LLMCache` 클래스, `RedisCache` Protocol.
- `app/adapters/llm/gateway.py` 수정: `LLMCompletionResult`에 `cache_hit` 필드 추가,
  `LLMGateway`에 `cache` 파라미터 추가, `complete_json`에 `cache_policy`·`user_id`
  파라미터 추가 및 캐시 흐름 구현.
- `app/adapters/llm/router.py` 수정: `LLM_MODEL_POLICY_VERSION` 모듈 상수 추가.
- `app/adapters/llm/__init__.py` 수정: `LLMCache` 익스포트 추가.
- `app/adapters/factory.py` 수정: `get_llm_gateway()`에 `LLMCache` 부착 로직 추가.
- `app/core/config.py` 수정: `LLM_CACHE_TTL_SECONDS: int | None = None` 추가.
- `app/domains/portfolios/briefing_service.py` 수정: `complete_json` 호출 시
  `cache_policy=READ_WRITE`, `user_id=user_id` opt-in.
- `app/domains/dashboard/briefing_service.py` 수정: `complete_json` 호출 시
  `cache_policy=READ_WRITE`, `user_id=user_id` opt-in.
- `docs/decisions/ADR-011-llm-cache-policy.md` 수정: Status를 `Accepted`로 승격,
  미결 질문 3개 확정.
- 테스트: `cache.py` 단위 테스트, 게이트웨이 캐시 hit/miss/policy 케이스 추가.
- 문서: `docs/backend-v0.2.md`·`.env.example`에 `LLM_CACHE_TTL_SECONDS` 항목 추가.

### 비포함

- 브리핑 이외 호출부(news·thesis·watchlist·llm_analysis)의 `cache_policy` 변경 —
  이번 범위에서 BYPASS 유지.
- alembic migration 신규 생성.
- `app/adapters/llm/router.py` 라우팅 테이블(`LLM_TASK_ROUTES`) 변경.
- `app/adapters/llm/privacy.py` 화이트리스트 변경.
- 관측 지표(캐시 hit/miss 메트릭 수집) — 후속 유보.

## 3. 구성 요소

### 3.1 `app/adapters/llm/cache.py` (신규)

| 심볼 | 종류 | 시그니처 | 책임 |
|---|---|---|---|
| `RedisCache` | Protocol | `get(name: str) -> str \| None` / `setex(name: str, time: int, value: str) -> object` | Redis 백엔드 인터페이스. 테스트에서 단순 스텁으로 교체 가능하게 한다. `budget.py`의 `RedisCounter`와 동형이나 독립 선언한다 |
| `LLMCache` | class | `__init__(self, redis: RedisCache, ttl: int)` | Redis 연결과 TTL 초를 보관한다 |
| | | `compute_key(self, task_type: LLMTaskType, user_id: int \| None, payload: CloudSafePayload, system_prompt: str, schema: type[BaseModel], model_policy_version: str, on_date: date \| None = None) -> str` | 키 재료를 canonical 순서로 조합해 sha256 다이제스트를 반환한다. `on_date`가 `None`이면 UTC 오늘 날짜를 사용한다(테스트에서는 인자 주입으로 날짜를 고정한다). 키 형식: `llm:cache:{digest}` |
| | | `get_cached(self, key: str) -> str \| None` | 키에 해당하는 JSON 문자열을 조회한다. 없으면 `None` 반환 |
| | | `put(self, key: str, value: str) -> None` | 키에 대해 `ttl` 초 동안 JSON 문자열을 저장한다 |

### 3.2 `app/adapters/llm/gateway.py` (수정)

| 심볼 | 변경 내용 |
|---|---|
| `LLMCompletionResult` | `cache_hit: bool = False` 필드 추가 |
| `LLMGateway.__init__` | `cache: LLMCache \| None = None` 파라미터 추가, 보관 |
| `LLMGateway.complete_json` | `cache_policy: CachePolicy = CachePolicy.BYPASS`, `user_id: int \| None = None` 파라미터 추가. 실행 순서: ① provider resolve, ② privacy guard(cloud 경로), ③ `cache_policy != BYPASS`이고 `cache`가 부착된 경우 키 산출 후 `get_cached` 조회 — hit이면 저장된 envelope을 복원해 `LLMCompletionResult(cache_hit=True, ...)` 즉시 반환(budget consume·client 호출 생략), ④ miss면 기존 흐름(budget consume(cloud 경로) → client 호출), ⑤ `cache_policy == READ_WRITE`이면 결과를 `put`으로 저장. 캐시 값은 `{"output": ..., "provider": ..., "model_name": ...}` JSON envelope 문자열로 게이트웨이가 직렬화·역직렬화한다(hit 시 원래 provider·model_name을 복원한다) |

### 3.3 `app/adapters/llm/router.py` (수정)

| 심볼 | 변경 내용 |
|---|---|
| `LLM_MODEL_POLICY_VERSION` | `str = "v1"` 모듈 상수 추가. 라우팅 테이블·모델 정책 변경 시 수동 bump한다 |

### 3.4 `app/adapters/llm/__init__.py` (수정)

`LLMCache`를 임포트·익스포트 목록에 추가한다.

### 3.5 `app/adapters/factory.py` (수정)

| 함수 | 변경 내용 |
|---|---|
| `get_llm_gateway()` | `settings.LLM_CACHE_TTL_SECONDS`가 `None`이 아니고 `LLM_PROVIDER != "mock"`인 경우에만 `LLMCache(get_redis_connection(), settings.LLM_CACHE_TTL_SECONDS)`를 생성해 `LLMGateway`에 `cache=` 파라미터로 전달한다. mock 모드에는 부착하지 않는다 |

### 3.6 `app/core/config.py` (수정)

| 설정 키 | 타입 | 기본값 | 의미 |
|---|---|---|---|
| `LLM_CACHE_TTL_SECONDS` | `int \| None` | `None` | LLM 캐시 TTL(초). `None`이면 캐시 비활성. `LLM_DAILY_CALL_LIMIT`과 동일한 empty-string-to-None 파싱 패턴을 적용한다 |

`.env.example`에 `LLM_CACHE_TTL_SECONDS=` 항목을 추가한다.

### 3.7 `app/domains/portfolios/briefing_service.py` (수정)

| 메서드 | 변경 내용 |
|---|---|
| `PortfolioBriefingService.generate` | `complete_json` 호출 시 `cache_policy=CachePolicy.READ_WRITE`, `user_id=user_id` 추가 |

### 3.8 `app/domains/dashboard/briefing_service.py` (수정)

| 메서드 | 변경 내용 |
|---|---|
| `DashboardBriefingService.generate` | `complete_json` 호출 시 `cache_policy=CachePolicy.READ_WRITE`, `user_id=user_id` 추가 |

### 3.9 `docs/decisions/ADR-011-llm-cache-policy.md` (수정)

Status를 `Accepted`로 승격하고, Decision 섹션의 미결 질문 3개에 대한 확정 답을
Decision III–MMM에 맞춰 반영한다. Alternatives·Consequences·Follow-up도 갱신한다.
상세는 §6 ADR 판단 참조.

## 4. Decisions

### Decision III — LLMCache 신규 모듈 신설, LLMGateway 생성자 주입

캐시를 `app/adapters/llm/cache.py`에 독립 모듈로 신설하고, `LLMGateway.__init__`에
`cache: LLMCache | None = None`으로 생성자 주입한다. `None`이면 캐시 없음(현행 동작 보존).

저장 매체를 Redis로 확정하는 근거는 두 가지다. 첫째, `budget.py`가 이미 Redis를 스택에
도입했으므로 추가 의존성이 없다. 둘째, 워커·API 프로세스 간 결과 공유가 필요한데 인메모리
캐시는 프로세스 로컬이라 부적합하다.

`RedisCache` Protocol(`get(name) -> str | None`, `setex(name, time, value) -> object`)을
정의해 테스트 대체성을 확보한다. `budget.py`의 `RedisCounter` Protocol과 동형이나 독립
선언한다(두 Protocol의 메서드 집합이 다르고 역할이 다르다).

기각 대안:
- **인메모리 캐시** — 프로세스 로컬이라 API·워커 간 공유 불가, 재시작 시 소실.
- **게이트웨이 내부 직접 구현** — `DailyCallBudget` 패턴과 달리 대체·테스트가 어렵다.
- **호출부 레벨 캐시** — ADR-011이 기각 방향을 명시. 프라이버시 키 산출·버전 무효화가
  호출부마다 흩어진다.

### Decision JJJ — 캐시 키 구성

캐시 키는 아래 재료를 canonical 순서로 조합한 문자열에 sha256을 적용해 구성한다.

| 재료 | 내용 |
|---|---|
| `task_type` | `LLMTaskType` 값(문자열) |
| `user_id` | `int \| None` (None이면 `"none"`) |
| `snapshot_hash` | CloudSafe payload `as_payload()` 결과를 canonical JSON으로 직렬화한 sha256 |
| `prompt_version` | `system_prompt` 문자열의 sha256 |
| `model_policy_version` | `LLM_MODEL_POLICY_VERSION` 상수 |
| `output_schema_version` | `schema.model_json_schema()` canonical JSON의 sha256 |
| `date` | UTC `YYYYMMDD` |

최종 키 형식: `llm:cache:{sha256_digest}`.

이슈가 명시한 `portfolio_snapshot_hash`·`market_snapshot_hash`를 단일 `snapshot_hash`로
수렴시키는 근거: 게이트웨이는 이미 병합된 단일 `CloudSafePayload` snapshot만 수신하므로
portfolio·market 입력을 구분할 필요 없이 payload canonical JSON의 sha256 하나로 충분하다.
projection이 이미 두 입력을 화이트리스트 범위에서 병합한다.

원본 민감정보(종목명·수량·매수가·계좌 원값)는 키에 평문으로 포함하지 않는다. `user_id`는
정수 식별자로 최종 다이제스트에만 녹아든다. 키 재료 범위는 CloudSafe payload와 같은
화이트리스트 범위로 제한한다(ADR-009·ADR-011 일관, 근거는 일관성과 단순성).

기각 대안:
- **user_id 원값을 키 접두사에 평문 노출** — 로깅·디버깅 경로 등으로 유출 가능성이 있어 기각.
- **snapshot_hash 없이 payload 내용을 키에 직접 포함** — 키 길이 폭증·민감 정보 노출 위험.

### Decision KKK — 버전 기반 무효화

세 버전 재료로 캐시를 자동 무효화한다.

| 버전 재료 | 산출 방법 | 무효화 트리거 |
|---|---|---|
| `prompt_version` | `system_prompt` 문자열의 sha256 | 프롬프트 텍스트 변경 시 자동 무효화 |
| `output_schema_version` | `schema.model_json_schema()` canonical JSON의 sha256 | 스키마 필드 변경 시 자동 무효화 |
| `model_policy_version` | `LLM_MODEL_POLICY_VERSION` 모듈 상수(`"v1"`) | 라우팅 테이블·모델 정책 변경 시 수동 bump |

버전이 바뀌면 키가 달라져 과거 항목이 자연히 miss된다. 조용한 stale 반환 없음(ADR-011 제약).

기각 대안:
- **명시적 캐시 플러시 API** — 수동 운영 부담이 크고 버전 추적이 불투명해진다.
- **TTL 기반 자연 만료만 의존** — 프롬프트 변경 후 TTL 만료 전까지 stale 결과가 반환된다.

### Decision LLL — CachePolicy 배선과 실행 순서

기존 미사용 `CachePolicy` enum(BYPASS·READ_WRITE·READ_ONLY)을 실사용한다.
`complete_json`에 `cache_policy: CachePolicy = CachePolicy.BYPASS`와
`user_id: int | None = None`을 추가한다. 기본값이 BYPASS이므로 기존 호출부는 변경 없이
동작이 보존된다.

실행 순서:
1. `router.resolve(task_type)`으로 provider 결정.
2. privacy guard(cloud 경로). 키 산출 입력이 CloudSafe 화이트리스트 범위임을 타입 레벨로
   보장하기 위해 캐시 조회보다 먼저 수행한다(ADR-011 제약). guard는 타입·sensitivity
   검사라 비용이 무시할 수준이다.
3. `cache_policy != BYPASS`이고 `self.cache`가 부착된 경우: 키 산출 후 `get_cached` 조회.
   - hit: 저장된 envelope에서 output·provider·model_name을 복원해
     `LLMCompletionResult(cache_hit=True, ...)` 즉시 반환. budget consume·client 호출 생략.
4. miss이면 기존 흐름: `call_budget.consume()`(cloud 경로) → `client.complete_json`.
5. `cache_policy == READ_WRITE`이면 결과를 `put`으로 저장. `READ_ONLY`는 저장 생략.

`LLMCompletionResult`에 `cache_hit: bool = False` 필드를 추가한다.

캐시 값은 `{"output": ..., "provider": ..., "model_name": ...}` JSON envelope 문자열로
게이트웨이가 직렬화·역직렬화한다. hit 시 최초 생성 당시의 provider·model_name이 그대로
복원되어 호출부 관점의 결과 구조가 miss 경로와 동일하다.

`call_budget.consume()`은 실제 cloud 호출 시에만 발생하므로 캐시 hit이 budget 소비를
줄인다(캐시 도입 목적과 정합).

기각 대안:
- **호출 후 선저장** — 캐시 hit 시에도 budget이 소비되어 도입 목적에 반한다.
- **캐시 조회를 privacy guard보다 앞에 배치** — hit 시 guard 연산을 아낄 수 있으나, 비
  CloudSafe payload가 키 산출 경로에 진입할 수 있어 ADR-011의 키 재료 화이트리스트 제약이
  타입 레벨에서 무너진다. guard 비용이 무시할 수준이므로 안전한 순서를 택한다.
- **output만 저장하고 provider를 `"cache"` 등 특수 값으로 표기** — 호출부가 provider 값에
  따라 분기할 여지를 만들고 결과 구조의 일관성을 해친다.

### Decision MMM — TTL과 팩토리 배선

전역 기본 TTL을 `config.LLM_CACHE_TTL_SECONDS`(기본 `None` = 비활성)로 관리한다.
`None`이면 factory가 `LLMCache`를 부착하지 않아 캐시 없는 동작이 된다.

키에 UTC `date`(YYYYMMDD) 버킷을 포함해 일 단위 자연 롤오버를 보장한다. 같은 날 생성된
캐시 항목은 TTL 내에 유효하며, 날짜가 바뀌면 키가 달라져 자동으로 miss된다.

작업별 TTL 설정은 후속으로 유보한다.

factory 배선: `LLM_CACHE_TTL_SECONDS is not None`이고 `LLM_PROVIDER != "mock"`인 경우에만
`LLMCache`를 부착한다. mock 모드에는 부착하지 않는다(`DailyCallBudget` 부착 패턴과 동형).

기각 대안:
- **`LLM_CACHE_ENABLED: bool` 별도 플래그** — TTL 값과 활성화 플래그를 따로 두면 설정 키가
  중복되고 두 값이 어긋나는 상태가 생긴다. TTL 유무 하나로 활성화를 표현한다.
- **date 버킷 없는 순수 TTL 만료** — TTL이 긴 경우 일 경계를 넘어 stale 항목이 hit될 수 있다.

## 5. 테스트

### `tests/test_llm_cache.py` (신규) — `cache.py` 단위 테스트

fake Redis 스텁(`get`·`setex`를 흉내 내는 단순 dict 기반 객체)을 직접 정의해 주입한다.
`fakeredis` 패키지 사용 금지. `AsyncMock` 사용 금지(sync 코드베이스).

- **miss** — 빈 스텁에서 `get_cached` 호출 시 `None` 반환 단언.
- **put → hit** — `put` 후 `get_cached`가 동일 값을 반환하는지 단언.
- **TTL 전달** — `put` 호출 시 스텁의 `setex`가 올바른 `ttl` 값으로 호출됨 단언.
- **결정론** — 동일 입력으로 `compute_key` 두 번 호출 시 동일 키 반환 단언.
- **prompt 민감도** — `system_prompt`를 한 글자 바꾸면 `compute_key` 결과가 달라짐 단언.
- **schema 민감도** — schema 필드가 다르면 `compute_key` 결과가 달라짐 단언.
- **날짜 버킷** — `on_date` 인자에 서로 다른 날짜를 주입하면 다른 키가 나오는지 단언.

### `tests/test_llm_gateway.py` (추가) — 게이트웨이 캐시 케이스

기존 `SpyLLMClient`·`SpyCallBudget` 패턴을 따라 fake `LLMCache` 스텁을 정의한다.

- **BYPASS policy** — `cache`가 부착되어 있어도 `BYPASS`이면 `get_cached` 미호출 단언.
- **READ_WRITE miss** — `client.complete_json` 호출됨, `cache.put` 호출됨 단언.
- **READ_WRITE hit** — `client.complete_json`·`call_budget.consume` 미호출,
  `result.cache_hit == True`이고 envelope에 저장된 provider·model_name이 복원됨 단언.
- **READ_ONLY hit** — `client.complete_json`·`call_budget.consume`·`cache.put` 미호출 단언.
- **READ_ONLY miss** — `client.complete_json` 호출됨, `cache.put` 미호출 단언.
- **budget 비소비** — cache hit 시 `SpyCallBudget.calls == 0` 단언(캐시 도입 목적 검증).
- **guard 선행** — cloud 경로에서 비 CloudSafe payload는 `cache_policy=READ_WRITE`여도
  `get_cached` 호출 전에 `CloudBoundaryViolationError`로 거부됨 단언.
- **회귀** — `cache=None`이면 기존 동작 그대로(`cache_hit=False`) 단언.

## 6. ADR 판단

ADR-011(`docs/decisions/ADR-011-llm-cache-policy.md`)을 `Proposed — Deferred`에서
`Accepted`로 승격한다.

미결 질문 3개에 대한 확정 답:

| 미결 질문 | 확정 답 |
|---|---|
| snapshot hash의 정확한 입력 범위 | CloudSafe payload `as_payload()` canonical JSON의 sha256 단일값. task_type·user_id·prompt_version·model_policy_version·output_schema_version·date를 별도 재료로 추가한다(Decision JJJ) |
| TTL 전역/작업별, 시간 기반/이벤트 기반 | 전역 기본 TTL(`LLM_CACHE_TTL_SECONDS`) + 키에 date 버킷 포함으로 일 단위 롤오버. 작업별 TTL은 후속 유보(Decision MMM) |
| 캐시 적중·미스 관측 지표 | `LLMCompletionResult.cache_hit` 필드로 호출부가 hit 여부를 확인할 수 있다. 메트릭 수집·로깅은 이번 범위 비포함, 후속 유보 |

ADR-011 Decision 섹션에 위 확정 답과 III~MMM 결정을 반영하고, Alternatives·Consequences·
Follow-up을 갱신한다. 실제 파일 편집은 Codex가 수행한다(핸드오프 Implementation Scope #9).

## 7. Failure Record 판단

불필요. 이번 작업은 결함 마감이 아닌 ADR-011 트리거 충족에 따른 계획된 기능 구현이다.
