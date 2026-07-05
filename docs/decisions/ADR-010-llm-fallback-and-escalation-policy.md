# ADR-010: LLM Fallback and Escalation Policy

## Status

Accepted

이 ADR은 #139 구현 착수와 함께 위험도 escalation 범위를 확정한다. 기술적 폴백과 safe
template 품질 폴백의 세부 구현은 아직 별도 후속으로 남긴다.

## Context

하이브리드 LLM 게이트웨이(ADR-007)는 라우팅과 프라이버시 경계를 이미 소유하지만, 모델
호출이 실패하거나 결과가 신뢰하기 어려울 때 무엇을 할지는 아직 정해두지 않았다. 스펙(§5)은
세 가지 서로 다른 상황을 한 묶음으로 다룬다.

1. **기술적 폴백.** provider가 타임아웃·오류·rate limit으로 응답하지 못할 때. transport
   계층의 장애를 어떻게 흡수할지의 문제다.
2. **품질 폴백.** 호출은 성공했으나 결과가 검증(ADR-012)을 통과하지 못하거나 사용하기에
   부적합할 때. 잘못된 결과를 그대로 저장하지 않고 safe template로 대체하는 문제다.
3. **위험도 escalation.** 입력이 `high_risk`이거나 모델 신뢰도가 낮을 때, 정적 라우팅
   (ADR-008)이 정한 provider보다 더 강한 백엔드로 런타임에 승격하는 문제다. 예를 들어
   로컬 primary 작업을 클라우드로 올린다.

초기에는 소비처가 부족해 세 가지를 확정하지 않았다. 이후 포트폴리오·대시보드 브리핑 기능이
구현되면서 사용자 대면 결과의 신뢰도 판단 지점이 생겼고, #139에서 위험도 escalation 엔진을
게이트웨이 단일 지점에 도입한다.

**현재 상태.** `LLMGateway.complete_json`은 모든 LLM 호출의 단일 경로다. #139 이후
`EscalationPolicy`가 opt-in으로 부착되면 입력 신호 기반 pre-call override와 출력 신호 기반
post-call cloud 검증을 수행한다. 기본 설정에서는 policy가 부착되지 않아 기존 경로가 보존된다.

## Decision

1. **게이트웨이 단일 지점.** 모든 escalation 판단은 `LLMGateway.complete_json` 안에서만
   수행한다. 호출부는 `EscalationSignal | None`을 선택적으로 전달할 수 있지만 provider를 직접
   고르거나 cloud 재호출을 직접 수행하지 않는다.
2. **Pre-call escalation.** `EscalationSignal`의 `risk_level=HIGH`, `loss_spike`,
   `news_sentiment_swing`, `event_flag`, `trade_question` 중 하나가 참이고 정적 라우팅 결과가
   `LOCAL`일 때만 provider를 `CLOUD`로 override한다. 현재 launch 라우팅은 전부 `CLOUD`이므로
   이 경로는 향후 `future_primary` 로컬 전환 시 실질 동작한다.
3. **Post-call cloud 검증.** 1차 provider가 `CLOUD`가 아니고 결과의 `confidence`가 설정 임계치
   미만이거나 `schema.model_validate(output)`이 실패하면 cloud client로 검증 재호출한다.
   재호출은 `privacy_gate.guard`와 `call_budget.consume`을 동일하게 거치며 cache lookup/store는
   적용하지 않는다. 재호출 결과가 다시 검증 실패하거나 예외가 발생하면 원래 결과를 반환하고
   경고 로그를 남긴다.
4. **Privacy boundary.** 로컬→클라우드 승격과 cloud 검증은 ADR-009의 `CloudSafePayload`
   경계를 우회하지 않는다. cloud 호출 전에는 항상 `privacy_gate.guard`를 통과한다.
5. **Observability.** `LLMCompletionResult.escalated: bool = False`를 추가한다. 값의 의미는
   provider override 또는 cloud 검증 재호출이 실제 수행됐다는 것이다. escalation 발생과 재호출
   실패는 payload·output 본문 없이 `task_type`, provider, reason 수준으로 로깅한다.
6. **미결 질문.** 기술적 폴백의 단계(단순 재시도, 대체 transport, 즉시 safe template)는 아직
   확정하지 않는다. ADR-012의 safe template 품질 폴백과의 최종 정합도 후속 결정으로 남긴다.

## Alternatives

지금 평가하지 않고, 확정 시 비교할 후보로만 기록한다.

- **폴백 없이 실패를 그대로 전파.** 호출부가 LLM 장애를 직접 본다. 단순하지만 브리핑류
  기능에는 사용자 경험상 부적합할 수 있다.
- **기술적 폴백만 두고 escalation은 영구 보류.** 로컬 전환이 실제로 일어날 때까지 escalation은
  죽은 코드이므로, 로컬 성숙 전까지 의도적으로 빼는 선택.
- **호출부별 폴백 정책.** 기각 방향이 유력하다. ADR-007/008과 같은 이유로 정책을 흩뜨리고
  프라이버시 경계 우회 위험을 만든다.

## Consequences

- `LLM_ESCALATION_ENABLED` 기본값이 `False`라서 기존 호출부와 테스트 경로는 policy 미부착 상태로
  유지된다.
- cloud 모드에서 opt-in하면 위험 신호와 낮은 confidence/schema 실패 결과를 게이트웨이에서
  일관되게 cloud로 승격·검증할 수 있다.
- post-call cloud 검증은 cache를 사용하지 않으므로 검증 재호출 결과가 일반 응답 cache를 오염하지
  않는다. 대신 검증 재호출도 budget을 소비한다.
- 기술적 transport 장애를 흡수하는 재시도/대체 provider 정책은 아직 없다.

## Follow-up

- #139 — 위험도 escalation 엔진 구현 완료.
- #140 이후 — 호출부에서 `EscalationSignal` 취합·전달.
- ADR-012 — 품질 폴백의 종착지(safe template)를 공유한다.
- 기술적 폴백 — 타임아웃·rate limit·transport 오류에 대한 재시도 또는 대체 provider 정책 확정.

## Related Documents

- `JongEunLee310/project_stock#137`(본 ADR), Epic `#141`
- `docs/decisions/ADR-007-llm-provider-abstraction.md`(게이트웨이 choke point)
- `docs/decisions/ADR-008-llm-task-routing-policy.md`(정적 라우팅, escalation은 런타임 오버라이드)
- `docs/decisions/ADR-009-cloud-data-boundary-cloudsafe-projection.md`(escalation이 지켜야 할 경계)
