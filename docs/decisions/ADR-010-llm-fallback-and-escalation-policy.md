# ADR-010: LLM Fallback and Escalation Policy

## Status

Accepted

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

최초 제안 시점에는 소비 기능이 충분히 구체화되지 않았고 로컬 백엔드도 stub뿐이라 결정을
보류했다. 이후 포트폴리오·대시보드 브리핑 기능 설계와 구현이 진행되었고, 선행 작업인
클라우드 경계(ADR-009)와 응답 캐시(ADR-011)가 자리 잡아 위험도 escalation 정책을
게이트웨이에 고정할 수 있게 되었다.

**현재 상태.** 게이트웨이는 `app/adapters/llm/gateway.py`의 단일 경로에서 라우팅과
클라우드 경계를 소유한다. CLOUD 경로는 `privacy_gate.guard` → cache lookup →
`call_budget.consume` → provider 호출 → cache store 순서를 따른다. LOCAL 경로는
guard·cache·budget 없이 provider를 호출한다. 모든 launch route는 아직 `cloud`이므로
escalation 엔진은 LOCAL 라우트가 등장하기 전까지 dormant하지만, LOCAL 전환 시 호출부가
provider를 직접 바꾸지 않도록 정책을 지금 게이트웨이에 둔다.

## Decision

위험도 escalation은 게이트웨이 단일 지점의 라우팅 오버라이드로 구현한다.

1. **Pre-call escalation.** 라우터가 LOCAL을 반환했고 `EscalationPolicy`가 부착되어
   있으며 입력 `risk_level`이 `RiskLevel.HIGH`이면, LOCAL provider를 호출하지 않고
   CLOUD 경로로 실행한다. 이때 결과에는 `escalated=True`,
   `escalation_trigger="HIGH_RISK_INPUT"`을 기록한다.
2. **Post-call escalation.** LOCAL 호출 결과가 스키마 검증에 실패하거나 출력 dict의
   `confidence`가 설정 임계값 미만이면 CLOUD 경로로 1회 재호출한다. 트리거는 각각
   `SCHEMA_VALIDATION_FAILED`, `LOW_CONFIDENCE`다. CLOUD 결과에 대한 재평가는 하지 않는다.
3. **CloudSafe boundary.** escalation은 ADR-009의 프라이버시 경계를 우회할 수 없다.
   승격 시도 시 `PrivacyGate.guard`가 실패하면 pre-call은 LOCAL 경로를 그대로 진행하고,
   post-call은 원 LOCAL 결과를 그대로 반환해 호출부 검증이 기존 방식으로 실패를 처리하게
   한다. 원래 라우트가 CLOUD인 경우의 guard 예외는 기존대로 전파한다.
4. **Cloud path parity.** 승격된 호출은 기존 CLOUD 경로와 동일하게 guard, cache, budget,
   provider 호출, cache store를 적용한다. 승격 호출도 `DailyCallBudget`을 소비하며 예산
   초과 예외는 전파한다.
5. **Trigger ownership.** 게이트웨이는 도메인 스키마를 해석하지 않는다. 호출부 평가기
   `derive_risk_level(bundle)`이 `LLMContextBundle`의 high severity signal 또는 손실 임계
   이하 `unrealized_return`을 `RiskLevel.HIGH`로 환산하고, 게이트웨이는 `RiskLevel`만
   소비한다.
6. **CLOUD route.** 이미 CLOUD로 라우팅된 작업에는 escalation 정책을 적용하지 않는다.
   CLOUD 결과의 품질 폴백과 safe template 저장 게이트는 ADR-012의 소관이다.
7. **Technical fallback.** provider 오류, timeout, rate limit 같은 기술적 실패에는 현재
   폴백을 두지 않고 예외 전파를 유지한다. 현재 영속화 소비처는 배경 작업 중심이라 잡 실패
   기록으로 충분하며, 사용자 대면 즉시 응답 경로가 생기면 재검토한다.

## Alternatives

- **폴백 없이 실패를 그대로 전파.** 호출부가 LLM 장애를 직접 본다. 단순하지만 브리핑류
  기능에는 사용자 경험상 부적합할 수 있다. 기술적 실패에 대해서는 현행 결정으로 채택하지만,
  품질 폴백의 최종 사용자 경험은 ADR-012에서 다룬다.
- **기술적 폴백만 두고 escalation은 영구 보류.** 로컬 전환 전까지 dormant 코드가 될 수
  있으나, LOCAL 전환 시 정책이 호출부로 흩어지는 위험이 더 크다.
- **호출부별 폴백 정책.** 기각한다. ADR-007/008과 같은 이유로 정책을 흩뜨리고 프라이버시
  경계 우회 위험을 만든다.
- **Cloud verification attachment.** 로컬 결과를 클라우드가 검증하는 별도 verify 모드는
  채택하지 않는다. 검증 프롬프트·판정 스키마가 별도로 필요하고 비용이 이중으로 들며, 현재
  요구는 LOCAL→CLOUD 승격으로 충분하다.

## Consequences

- `LLMGateway`가 LOCAL 라우트에서 pre-call·post-call escalation을 수행한다.
- `LLMAnalysisService`는 `derive_risk_level(bundle)` 결과를 게이트웨이에 전달한다.
- 정책은 설정 임계값이 있을 때만 cloud mode factory에서 부착된다. mock·local mode의 기존
  동작은 유지한다.
- DB 스키마 변경은 없다.
- 품질 폴백의 safe template 및 저장 게이트는 ADR-012와 후속 작업에 남는다.

## Follow-up

- #139 — 위험도 escalation 엔진 구현으로 본 ADR의 escalation 결정을 반영한다.
- #140 / ADR-012 — 품질 폴백의 종착지(safe template)와 저장 게이트를 확정한다.
- 사용자 대면 즉시 응답 경로가 생기면 기술적 폴백의 재시도·대체 transport 필요성을
  재검토한다.

## Related Documents

- `JongEunLee310/project_stock#137`(본 ADR), Epic `#141`
- `docs/decisions/ADR-007-llm-provider-abstraction.md`(게이트웨이 choke point)
- `docs/decisions/ADR-008-llm-task-routing-policy.md`(정적 라우팅, escalation은 런타임 오버라이드)
- `docs/decisions/ADR-009-cloud-data-boundary-cloudsafe-projection.md`(escalation이 지켜야 할 경계)
