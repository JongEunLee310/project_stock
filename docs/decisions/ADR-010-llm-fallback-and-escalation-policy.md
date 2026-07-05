# ADR-010: LLM Fallback and Escalation Policy

## Status

Accepted

#139 구현으로 위험도 escalation 엔진을 확정한다. 기술적 폴백(타임아웃·rate limit 재시도,
대체 transport, 즉시 safe template 전환)은 아직 소비처별 요구가 충분히 구체화되지 않았으므로
미결 질문으로 남긴다.

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

초기에는 소비처가 아직 없어 결정을 보류했다. 이후 포트폴리오·대시보드 브리핑 기능이 착수되어
사용자 대면 LLM 결과의 신뢰도 요구가 구체화됐고, `future_primary=local` 작업이 실제 전환될 때
게이트웨이 재설계 없이 cloud 승격을 적용할 필요가 생겼다.

**현재 상태.** 모든 LLM 호출은 `LLMGateway.complete_json` 단일 경로를 통과한다. 정적 라우팅은
`LLMRouter`가 결정하고, cloud 호출은 `PrivacyGate`와 비용 상한, 응답 캐시 규율을 따른다. 이번
결정은 이 단일 지점 안에 위험도 escalation 판단을 추가하되, 호출부가 provider를 직접 바꾸지
않도록 한다.

## Decision

위험도 escalation은 `LLMGateway.complete_json` 안에서만 판단한다. 호출부는 선택적으로
`EscalationSignal`을 전달할 수 있지만, provider를 직접 지정하거나 재호출 분기를 갖지 않는다.
`escalation_signal=None`이거나 `EscalationPolicy`가 주입되지 않으면 기존 경로를 그대로 보존한다.

1. **Pre-call escalation.** `EscalationSignal`의 입력 신호 중 `risk_level=HIGH`,
   `loss_spike`, `news_sentiment_swing`, `event_flag`, `trade_question` 중 하나라도 참이고,
   정적 라우팅 결과가 `LOCAL`이면 게이트웨이가 provider를 `CLOUD`로 런타임 override한다. 이미
   `CLOUD`로 라우팅된 호출은 다시 승격하지 않는다. cloud로 승격된 호출은 일반 cloud 호출과
   동일하게 `PrivacyGate`, cache lookup/store, `DailyCallBudget` 규율을 모두 따른다.
2. **Post-call cloud verification.** 1차 provider가 `CLOUD`가 아니고, 결과 dict의
   `confidence`가 설정된 `LLM_ESCALATION_CONFIDENCE_THRESHOLD` 미만이거나 `schema.model_validate`
   검증에 실패하면 cloud client로 검증 재호출을 수행한다. 재호출은 `PrivacyGate`와
   `DailyCallBudget`을 동일하게 적용하지만 cache lookup/store는 적용하지 않는다. 재호출 결과가
   schema 검증을 통과하면 최종 결과를 대체한다. 재호출 자체가 실패하거나 재호출 결과도 schema
   검증에 실패하면 원래 결과를 반환하고 경고 로그를 남긴다.
3. **Privacy boundary.** escalation은 ADR-009의 CloudSafe projection 경계를 우회할 수 없다.
   로컬→클라우드 승격과 cloud 검증 재호출 모두 `PrivacyGate.guard`를 통과해야 한다.
4. **Observability.** `LLMCompletionResult`에 `escalated: bool = False`를 추가한다. 값의 의미는
   "provider override 또는 cloud 검증 재호출이 실제 수행됐다"이다. cloud client가 없어 재호출을
   건너뛴 경우에는 `False`로 남긴다. escalation 발생과 재호출 실패는 payload·output 내용을
   포함하지 않는 로그로 남긴다.
5. **Remaining open questions.** 기술적 폴백의 단계(단순 재시도, 대체 transport, 즉시 safe
   template), ADR-012 safe template과의 최종 결합 방식, 별도 메트릭 수집 인프라는 후속 결정으로
   남긴다.

## Alternatives

지금 평가하지 않고, 확정 시 비교할 후보로만 기록한다.

- **폴백 없이 실패를 그대로 전파.** 호출부가 LLM 장애를 직접 본다. 단순하지만 브리핑류
  기능에는 사용자 경험상 부적합할 수 있다.
- **기술적 폴백만 두고 escalation은 영구 보류.** 로컬 전환이 실제로 일어날 때까지 escalation은
  죽은 코드이므로, 로컬 성숙 전까지 의도적으로 빼는 선택.
- **호출부별 폴백 정책.** 기각 방향이 유력하다. ADR-007/008과 같은 이유로 정책을 흩뜨리고
  프라이버시 경계 우회 위험을 만든다.

## Consequences

- `LLM_ESCALATION_ENABLED` 기본값은 `False`이므로 명시적으로 켠 cloud 모드에서만 policy가
  부착된다.
- 현재 launch 라우팅은 모두 `cloud`이므로 pre-call escalation은 `future_primary=local` 작업이
  실제 local launch로 전환될 때 실질 동작한다.
- post-call 검증도 1차 provider가 `CLOUD`이면 재호출하지 않는다. 따라서 현재 cloud launch에서는
  비용 중복 호출을 만들지 않는다.
- DB 스키마 변경은 없다.

## Follow-up

- #139 — 위험도 escalation 엔진 구현 완료.
- #140 이후 — 호출부에서 `EscalationSignal` 취합·전달.
- ADR-012 — 품질 폴백의 종착지(safe template)를 공유한다.
- 기술적 폴백(타임아웃·rate limit 재시도, 대체 transport) 별도 결정.

## Related Documents

- `JongEunLee310/project_stock#137`(본 ADR), Epic `#141`
- `docs/decisions/ADR-007-llm-provider-abstraction.md`(게이트웨이 choke point)
- `docs/decisions/ADR-008-llm-task-routing-policy.md`(정적 라우팅, escalation은 런타임 오버라이드)
- `docs/decisions/ADR-009-cloud-data-boundary-cloudsafe-projection.md`(escalation이 지켜야 할 경계)
