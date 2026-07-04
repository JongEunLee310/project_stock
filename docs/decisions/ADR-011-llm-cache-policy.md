# ADR-011: LLM Cache Policy

## Status

Accepted

브리핑 기능이 구현되어 동일 입력에 대한 반복 cloud LLM 호출 경로가 생겼으므로 캐시 정책을
확정한다.

## Context

클라우드 LLM 호출은 비용과 지연을 수반한다. 같은 입력에 같은 결과를 반복 생성하는 작업
(예: 동일 스냅샷에 대한 포트폴리오·대시보드 브리핑)은 캐시로 호출을 줄일 수 있다. 스펙(§6)은
세 가지 설계 요소를 든다.

1. **캐시 키.** 무엇이 같은 입력인가를 정하는 키. 스펙은 입력 데이터의 snapshot hash를
   제안한다.
2. **TTL.** 캐시 항목이 유효한 기간.
3. **무효화.** 프롬프트나 모델 버전이 바뀌면 과거 결과를 더는 신뢰할 수 없으므로 무효화해야
   한다.

과거에는 캐시할 대상 자체가 아직 없어 결정을 보류했다. 이후 포트폴리오·대시보드 브리핑과
watchlist 관찰 생성처럼 동일 스냅샷을 반복 분석할 수 있는 경로가 생겼고, 모든 호출이
`LLMGateway.complete_json(task_type, payload, schema, system_prompt)`로 수렴되었다. payload는
`CloudSafePayload` projection이므로 캐시 키도 이 projection 범위 안에서 산출한다.

## Decision

캐시는 `LLMGateway` 내부의 cloud 경로에만 둔다. 호출부는 캐시 존재를 알 필요가 없다.

캐시 키는 `llm:cache:{task_type}:{YYYYMMDD}:{digest}` 형식이다. 날짜는 UTC 기준이고,
`digest`는 `CloudSafePayload.as_payload()`의 canonical JSON, `system_prompt`,
라우팅된 client의 `model_name`, `schema.model_json_schema()` JSON을 이어붙인 문자열의
`sha256` hexdigest다. `user_id` 같은 내부 식별자는 키 재료에 넣지 않는다. 사용자별 차이는
이미 전송 projection에 반영되어야 하며, 키 재료를 CloudSafe projection과 동일한
화이트리스트로 제한하는 편이 privacy boundary와 계층 책임이 명확하다.

무효화는 별도 version 상수가 아니라 본문 해시로 처리한다. payload, 프롬프트, 모델명, schema가
바뀌면 digest가 바뀌므로 과거 항목은 자동으로 빗나간다. UTC 날짜도 키에 포함해 자정 경계에서
새 캐시 항목을 쓰게 한다.

저장 매체는 Redis다. `LLM_CACHE_TTL_SECONDS` 전역 단일 TTL을 두고, 값이 `None`이면 캐시를
부착하지 않는다. 작업별 TTL이나 수동 무효화 API는 필요 신호가 생기면 후속으로 다룬다.

cloud 경로 순서는 `privacy_gate.guard` → cache lookup → cache miss 시 `DailyCallBudget.consume`
→ client 호출 → cache store다. 캐시 hit는 cloud 호출이 아니므로 budget을 소비하지 않고,
`LLMCompletionResult.cached=True`로 복원한다. Redis `get`/`set` 예외, 역직렬화 실패, 필수 필드
결손은 모두 miss로 취급해 실제 호출로 진행한다. local 라우팅과 mock provider 팩토리 경로에는
캐시를 적용하지 않는다.

## Alternatives

지금 평가하지 않고, 확정 시 비교할 후보로만 기록한다.

- **캐시 없음.** 매 호출을 그대로 수행한다. 단순하며, 호출량이 적은 동안에는 충분하다. 캐시
  도입 전까지의 기본 상태다.
- **호출부 레벨 캐시.** 기각 방향이 유력하다. 게이트웨이 밖에 두면 프라이버시 키 산출과
  버전 무효화가 호출부마다 흩어진다.
- **TTL 없이 영구 캐시 + 수동 무효화.** 운영 부담과 stale 위험이 커서 후보로만 남긴다.

## Consequences

- 동일 입력의 반복 cloud 호출은 Redis hit 시 client 호출과 budget 소비 없이 복원된다.
- `LLM_CACHE_TTL_SECONDS`를 비워 두면 기존 동작이 유지된다.
- 캐시 장애는 LLM 호출 실패로 전파되지 않지만, 장애 동안 비용 절감 효과는 사라진다.
- DB schema 변경은 없다.

## Follow-up

- #138 — LLM Cache 구현 완료.
- hit/miss 메트릭, 작업별 TTL, 수동 무효화 API는 운영 필요가 확인되면 별도 이슈로 다룬다.

## Related Documents

- `JongEunLee310/project_stock#137`(본 ADR), Epic `#141`
- `docs/designs/080-llm-response-cache.md`
- `docs/decisions/ADR-007-llm-provider-abstraction.md`(게이트웨이 계층 분리)
- `docs/decisions/ADR-009-cloud-data-boundary-cloudsafe-projection.md`(캐시 키가 지켜야 할 경계)
