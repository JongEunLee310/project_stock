# ADR-011: LLM Cache Policy

## Status

Accepted

## Context

클라우드 LLM 호출은 비용과 지연을 수반한다. 포트폴리오·대시보드 브리핑은 동일 사용자와
동일 CloudSafe 스냅샷에 대해 반복 호출될 수 있으므로, 게이트웨이 내부 캐시를 두면 호출 횟수와
응답 지연을 줄일 수 있다.

이 ADR은 이전에 브리핑 입력 스냅샷과 갱신 주기가 확정될 때까지 결정을 보류했다. 브리핑 기능이
구현되어 BE #138의 풀구현 트리거가 충족되었으므로, 캐시 키·TTL·무효화·관측 표면을 확정한다.

## Decision

LLM 캐시는 `app/adapters/llm/cache.py`의 `LLMCache`로 구현하고, `LLMGateway`에
`cache: LLMCache | None = None`으로 생성자 주입한다. 저장 매체는 Redis로 정한다. 이미
`DailyCallBudget`가 Redis를 사용하므로 새 의존성이 필요 없고, API/worker 프로세스 간 결과를
공유할 수 있다.

캐시 키는 다음 재료를 canonical 순서로 조합한 뒤 sha256으로 해시한다.

| Material | Value |
| --- | --- |
| `task_type` | `LLMTaskType` 문자열 값 |
| `user_id` | 사용자 id, 없으면 `"none"` |
| `snapshot_hash` | `CloudSafePayload.as_payload()` canonical JSON의 sha256 |
| `prompt_version` | `system_prompt` 문자열의 sha256 |
| `model_policy_version` | `LLM_MODEL_POLICY_VERSION` 상수 |
| `output_schema_version` | `schema.model_json_schema()` canonical JSON의 sha256 |
| `date` | UTC `YYYYMMDD` 버킷 |

최종 Redis key 형식은 `llm:cache:{digest}`이다. 원본 entity와 raw 민감 정보는 키 재료로 쓰지
않고, projection된 CloudSafe payload 범위만 사용한다.

무효화는 버전 기반으로 처리한다. 프롬프트 문자열 또는 출력 스키마가 바뀌면 자동으로 다른 키가
나오고, 라우팅 테이블이나 모델 정책이 바뀌면 `LLM_MODEL_POLICY_VERSION`을 수동 bump한다.
따라서 조용히 stale 결과를 반환하지 않는다.

`CachePolicy`는 `LLMGateway.complete_json` 파라미터로 실사용한다. 기본값은
`CachePolicy.BYPASS`라 기존 호출부 동작은 유지된다. 캐시를 사용하는 경로의 실행 순서는
provider resolve, cloud privacy guard, cache lookup, budget consume, client call, cache store이다.
cache hit이면 budget consume과 client 호출 없이 저장된 envelope의 `output`, `provider`,
`model_name`을 복원해 반환한다.

TTL은 전역 설정 `LLM_CACHE_TTL_SECONDS`로 둔다. 기본값 `None`은 캐시 비활성이고, 값이 있으면
`LLM_PROVIDER != "mock"`인 factory 경로에서 Redis 캐시를 부착한다. 작업별 TTL과 메트릭/로깅은
이번 범위에서 제외하고 후속으로 유보한다. 호출부가 확인할 수 있는 최소 관측 표면으로
`LLMCompletionResult.cache_hit`을 제공한다.

## Alternatives

- **No cache.** 구현은 단순하지만 동일 브리핑 반복 호출 비용과 지연을 줄이지 못한다.
- **In-memory cache.** 프로세스 로컬이라 API/worker 간 공유가 안 되고 재시작 시 소실된다.
- **Call-site cache.** 프라이버시 키 산출과 버전 무효화가 호출부마다 흩어져 ADR-007의
  게이트웨이 경계와 맞지 않는다.
- **Permanent cache with manual invalidation.** 운영자가 stale 위험을 직접 관리해야 하므로
  프롬프트·스키마·모델 정책 버전 기반 무효화보다 취약하다.

## Consequences

- 브리핑 호출부는 `CachePolicy.READ_WRITE`로 opt-in하고, 그 외 LLM 호출은 기본 BYPASS를 유지한다.
- cache hit은 일일 cloud call budget을 소비하지 않는다.
- Redis 장애나 TTL 설정 오류는 LLM 캐시 경로에 영향을 줄 수 있으므로, 운영 환경에서는
  `LLM_CACHE_TTL_SECONDS`를 명시적으로 선택해야 한다.
- 모델 라우팅 또는 모델 정책 변경 시 `LLM_MODEL_POLICY_VERSION` bump를 잊으면 기존 캐시가
  재사용될 수 있다.

## Follow-up

- 캐시 hit/miss 메트릭과 로그를 별도 작업으로 추가한다.
- 작업별 TTL이 필요해지는 시점에 전역 TTL 정책을 재검토한다.
- 모델 정책 변경 체크리스트에 `LLM_MODEL_POLICY_VERSION` bump를 포함한다.

## Related Documents

- `docs/designs/080-llm-cache.md`
- `docs/decisions/ADR-007-llm-provider-abstraction.md`
- `docs/decisions/ADR-009-cloud-data-boundary-cloudsafe-projection.md`
- BE #138, Epic BE #141
