# ADR-010: LLM Fallback and Escalation Policy (Phase 2, deferred)

## Status

Proposed — Deferred

이 ADR은 결정을 지금 확정하지 않는다. 무엇을 결정해야 하는지, 왜 지금이 아닌지, 그리고
어떤 신호가 오면 확정해야 하는지를 기록한다. 풀구현 트리거가 충족되면 본 문서를 갱신해
Status를 `Proposed`(이후 `Accepted`)로 올린다.

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

이 세 가지를 지금 풀로 설계하지 않는 이유는 소비처가 아직 없기 때문이다. 폴백과 escalation은
"어떤 결과가 충분히 좋은가", "어떤 입력이 고위험인가"라는 판단을 요구하는데, 그 판단 기준은
실제 소비 기능(포트폴리오·대시보드 브리핑)이 무엇을 보여줄지가 정해져야 구체화된다. 기능
없이 정책을 고정하면 투기적 추상화가 된다(Epic #141의 Phase 분리 근거).

또한 출시 시점에는 로컬 백엔드가 stub뿐이라(ADR-008) 로컬→클라우드 escalation을 실제로
검증할 대상 자체가 없다.

## Decision

지금은 확정하지 않는다. 대신 풀구현 시점에 지켜야 할 제약(guardrail)과 트리거만 고정한다.

1. **풀구현 트리거.** 다음 중 먼저 도래하는 것이 신호다.
   - 포트폴리오 또는 대시보드 브리핑 기능 설계가 착수되어, "이 작업이 실패하면 사용자에게
     무엇을 보여줄지"라는 폴백 요구가 구체화될 때.
   - 어떤 작업의 `future_primary`가 로컬로 전환되어(ADR-008), 고위험 입력의 클라우드
     escalation이 가상의 시나리오가 아니게 될 때.
2. **확정 시 지켜야 할 제약.**
   - escalation은 ADR-009의 프라이버시 경계를 우회할 수 없다. 로컬→클라우드 승격은 해당
     작업의 페이로드가 CloudSafe projection으로 표현 가능할 때만 허용된다. 표현 불가능한
     `RAW` 작업은 escalation 대상이 아니다.
   - 모든 폴백·escalation 판단은 게이트웨이라는 단일 choke point 안에서 일어난다. 호출부가
     자체적으로 재시도하거나 백엔드를 바꾸지 않는다.
   - 품질 폴백의 종착지는 ADR-012의 safe template과 일치시킨다. 같은 "신뢰할 수 없는 결과"를
     두 ADR이 다르게 처리하지 않도록 한다.
   - 폴백 발생은 관측 가능해야 한다(로깅·메트릭). 조용한 성능 저하를 만들지 않는다.
3. **확정해야 할 미결 질문.**
   - 기술적 폴백의 단계: 단순 재시도인지, 대체 transport인지, 즉시 safe template인지.
   - escalation 트리거를 무엇으로 측정하는가 — `Risk` enum(#133) 입력값인지, 모델이 보고한
     신뢰도인지, 둘 다인지.
   - escalation의 비용·지연 상한.

## Alternatives

지금 평가하지 않고, 확정 시 비교할 후보로만 기록한다.

- **폴백 없이 실패를 그대로 전파.** 호출부가 LLM 장애를 직접 본다. 단순하지만 브리핑류
  기능에는 사용자 경험상 부적합할 수 있다.
- **기술적 폴백만 두고 escalation은 영구 보류.** 로컬 전환이 실제로 일어날 때까지 escalation은
  죽은 코드이므로, 로컬 성숙 전까지 의도적으로 빼는 선택.
- **호출부별 폴백 정책.** 기각 방향이 유력하다. ADR-007/008과 같은 이유로 정책을 흩뜨리고
  프라이버시 경계 우회 위험을 만든다.

## Consequences

- 보류의 효과: 게이트웨이는 현재 폴백·escalation 없이 동작하며, 실패는 호출부로 전파된다.
  Phase 1 기능(뉴스 요약 등 기존 mock/cloud 경로)에는 당장 문제가 되지 않는다.
- 리스크: 브리핑 기능을 설계할 때 폴백 요구가 뒤늦게 드러나면 게이트웨이에 후행 작업이
  몰릴 수 있다. 트리거를 명시해 두는 것으로 이 리스크를 관리한다.
- 코드·DB 변경 없음. 본 문서는 결정 보류 기록이다.

## Follow-up

- 브리핑 기능 설계(Phase 2) — 폴백 요구를 확정하는 선행 의존성.
- #139 / #140 — 위험도 escalation 엔진 구현. 본 ADR이 확정된 뒤 착수한다.
- ADR-012 — 품질 폴백의 종착지(safe template)를 공유한다.

## Related Documents

- `JongEunLee310/project_stock#137`(본 ADR), Epic `#141`
- `docs/decisions/ADR-007-llm-provider-abstraction.md`(게이트웨이 choke point)
- `docs/decisions/ADR-008-llm-task-routing-policy.md`(정적 라우팅, escalation은 런타임 오버라이드)
- `docs/decisions/ADR-009-cloud-data-boundary-cloudsafe-projection.md`(escalation이 지켜야 할 경계)
