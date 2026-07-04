# 080 — LLM Response Cache (BE #138)

## Status

Draft

## 배경

이슈 #138은 LLM 응답 캐시를 요구한다. ADR-011(Proposed — Deferred)은 "브리핑 기능이
등장해 반복 클라우드 호출이 생기는 시점"을 풀구현 트리거로 명시했고, PR #151에서
포트폴리오·대시보드 브리핑이 구현되어 트리거가 충족됐다. 이번 작업으로 ADR-011을
확정(Accepted)하고 캐시를 구현한다.

현재 모든 LLM 호출은 `LLMGateway.complete_json(task_type, payload, schema, system_prompt)`
단일 경로로 수렴되어 있고(#206), payload는 전부 `CloudSafePayload` projection이다.
게이트웨이는 CLOUD 라우팅 시 `PrivacyGate` 통과 후 `DailyCallBudget`(#209)을 소비한다.

## 범위

- `app/adapters/llm/cache.py` 신설 — `LLMResponseCache`
- `LLMGateway` 캐시 주입·CLOUD 경로 lookup/store
- `app/core/config.py` — `LLM_CACHE_TTL_SECONDS`
- `app/adapters/factory.py` — cloud 모드 부착 로직
- `docs/decisions/ADR-011-llm-cache-policy.md` — Status Accepted 갱신
- 비포함: 호출부(도메인 서비스) 변경, 캐시 관리 API·수동 무효화 endpoint, 작업별 TTL,
  hit/miss 메트릭 수집 인프라

## 구성 요소

| 파일 | 변경 | 책임 |
| --- | --- | --- |
| `app/adapters/llm/cache.py` | 신규 | 키 산출·Redis get/set·TTL |
| `app/adapters/llm/gateway.py` | 수정 | CLOUD 경로에서 lookup → miss 시 호출·store |
| `app/core/config.py` | 수정 | `LLM_CACHE_TTL_SECONDS: int | None = None` (`""` → `None` 파싱) |
| `app/adapters/factory.py` | 수정 | cloud 모드이고 TTL 설정 시에만 부착 |
| `.env.example` | 수정 | `LLM_CACHE_TTL_SECONDS=` 항목 |
| `docs/decisions/ADR-011-llm-cache-policy.md` | 수정 | Accepted 확정 |

### LLMResponseCache 시그니처

- `__init__(redis: RedisCacheStore, ttl_seconds: int)` — `RedisCacheStore`는
  `get(name) -> str | bytes | None` / `set(name, value, ex) -> object` Protocol
  (budget.py의 `RedisCounter` 패턴)
- `build_key(task_type, payload, system_prompt, model_name, schema) -> str`
- `lookup(key) -> CachedCompletion | None` — 역직렬화 실패는 miss로 취급
- `store(key, output, provider, model_name) -> None` — JSON 직렬화, TTL 부여
- `CachedCompletion` — `output: dict`, `provider: str`, `model_name: str` frozen dataclass

## Decisions

### Decision III — 캐시 키 스킴: 전송 페이로드와 동일 재료의 단방향 해시

키는 `llm:cache:{task_type}:{YYYYMMDD}:{digest}` 형식으로 한다. `digest`는
`sha256(canonical payload JSON + system_prompt + model_name + schema JSON)`이다.

- 이슈 #138의 키 요소 대응: portfolio/market snapshot hash → payload 해시(payload가
  스냅샷 자체), prompt_version → system_prompt 해시, model_policy_version → 라우팅
  확정 후 client의 `model_name`, output_schema_version → `schema.model_json_schema()`
  해시, date → UTC 날짜.
- **prompt version 상수 대신 프롬프트 본문 해시를 쓴다.** 버전 상수는 analysis에만
  존재하고 나머지 4개 프롬프트에는 없다. 본문 해시는 상수 갱신 누락으로 stale 결과가
  반환되는 실패 모드를 원천 제거한다(ADR-011 제약 2 — "조용히 stale 반환 금지").
- **user_id는 키에 넣지 않는다.** 이슈 원문과 다른 결정이다. ADR-011 제약 1은 키 재료를
  클라우드 전송 페이로드(CloudSafe projection)와 같은 화이트리스트로 제한하는데,
  user_id는 페이로드에 없는 내부 식별자다. 사용자 특이 데이터는 이미 payload에 반영되어
  해시가 달라지고, 서로 다른 사용자가 우연히 동일한 집계 입력을 가지면 동일 출력을
  공유해도 의미상 올바르다(같은 입력 → 같은 결과).
- 원본 민감정보는 키에 직접 포함되지 않는다 — digest는 단방향이며 재료 자체가 이미
  CloudSafe 범위다.

기각 대안: 프롬프트 모듈별 버전 상수 신설(5개 모듈 수기 관리 부담·갱신 누락 위험),
user_id 키 포함(화이트리스트 이탈·게이트웨이 시그니처 변경 필요).

### Decision JJJ — 저장 매체 Redis·전역 단일 TTL·미설정 시 비활성

- 저장은 Redis로 한다. 지침 §16이 Redis 필요 시점으로 "짧은 TTL 캐시·중복 LLM 요청
  방지"를 명시하고, #209에서 이미 게이트웨이 계층이 Redis를 쓰고 있다.
- TTL은 `LLM_CACHE_TTL_SECONDS` 전역 단일 값. `None`(기본)이면 캐시를 부착하지 않아
  기존 동작이 그대로 보존된다 — `LLM_DAILY_CALL_LIMIT`과 동일한 opt-in 패턴. 작업별
  TTL은 필요 신호가 생기면 후속으로 미룬다.
- 키의 UTC 날짜 요소가 자정 경계 무효화를 보장하므로, TTL이 날짜를 넘겨도 어제 항목이
  재사용되지 않는다.

기각 대안: PostgreSQL JSONB 저장(읽기 경로에 DB 세션 필요 — 게이트웨이는 현재 DB
비의존, 계층 침범), 인메모리(프로세스 간 비공유 — API·worker 다중 프로세스 구조).

### Decision KKK — CLOUD 전용·budget보다 먼저 조회·결과 projection 저장

게이트웨이 CLOUD 경로 순서: `privacy_gate.guard` → **cache lookup** → (miss 시)
`call_budget.consume` → `client.complete_json` → **cache store**.

- 캐시 히트는 클라우드 호출이 발생하지 않으므로 budget을 소비하지 않는다. 캐시의
  목적(비용 절감)과 budget의 목적(비용 상한)이 일관된다.
- LOCAL 라우팅·mock 모드에는 캐시를 적용하지 않는다(비용·지연 문제가 없는 경로).
- 저장 값은 `output`(dict)·`provider`·`model_name`으로, 히트 시 `LLMCompletionResult`를
  클라이언트 없이 복원한다. `LLMCompletionResult`에 `cached: bool = False` 필드를
  추가해 최소 관측 지표로 삼는다(ADR-011 미결 질문 3의 초기 대응 — 호출부·로깅에서
  히트 여부 식별 가능).
- Redis get/set 실패나 역직렬화 실패는 miss로 처리하고 실 호출로 진행한다 — 캐시는
  최적화 계층이므로 장애가 호출 실패로 전파되면 안 된다.

기각 대안: budget 소비 후 캐시 조회(히트에도 예산 차감 — 목적 모순), 호출부 레벨
캐시(ADR-011이 이미 기각 방향으로 기록).

### Decision LLL — ADR-011을 Accepted로 확정

풀구현 트리거(브리핑 기능 존재·반복 호출 경로 등장)가 충족됐으므로 ADR-011 Status를
`Accepted`로 올리고, Decision 절에 III·JJJ·KKK의 확정 내용을 반영한다. 미결 질문 3
(관측 지표)은 `cached` 필드 수준의 초기 대응만 기록하고 본격 메트릭은 후속으로 남긴다.

## 리뷰 반영

블라인드 코드 리뷰(실험 라운드3, `docs/experiments/fable-codex-high-vs-opus-vff-codex-medium.md`)
적발 사항을 task-147로 반영한다.

- 빈 output(`{}`)은 store하지 않는다 — provider 이상 신호가 TTL 동안 고착되는 것을 방지.
- `CACHE_SCHEMA_VERSION` 상수를 키 네임스페이스에 포함한다 — 키 재료 밖 코드(메시지
  조립·provider schema instruction·envelope 형식) 변경 시 수동 bump로 일괄 무효화.
- digest 재료는 경계가 보존되는 직렬화로 결합한다(연결 경계 이동으로 인한 키 충돌 제거).
- `LLM_CACHE_TTL_SECONDS`는 양수만 허용한다(0 이하는 기동 시 설정 오류).
- `lookup`·`store`의 예외 삼킴 지점에 warning 로그를 남긴다(캐시 값은 로그 제외).

## 테스트

- `LLMResponseCache` 단위: 키 결정성(동일 입력 → 동일 키), 재료 민감도(payload·
  prompt·model·schema 각각 변경 시 키 변화), miss → store → hit 왕복, 손상 값 miss
  처리. fake Redis 스텁 주입(fakeredis 미사용, `AsyncMock` 금지 — sync 코드베이스).
- 게이트웨이 통합: CLOUD 히트 시 클라이언트 미호출·budget 미소비·`cached=True`,
  miss 시 호출·store, LOCAL 라우팅 시 캐시 미조회.
- 팩토리: TTL 설정+cloud일 때만 부착. config: `""` → `None` 파싱.

## ADR 판단

신규 ADR 불필요 — ADR-011 확정 갱신으로 충분하다(본 설계 Decision LLL).

## Failure Record 판단

불필요 — 계획된 Phase 2 항목의 트리거 충족에 따른 구현이며 결함 마감이 아니다.
