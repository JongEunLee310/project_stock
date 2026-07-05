# 081 — LLM Risk Escalation Engine (BE #139)

## Status

Draft

## 배경

이슈 #139는 위험도 escalation 엔진을 요구한다. ADR-010은 "어떤 작업의
`future_primary`가 로컬로 전환되거나, 사용자 대면 브리핑 기능이 착수될 때"를 풀구현
트리거로 명시했다. 포트폴리오·대시보드 브리핑이 구현되면서 사용자 대면 결과의 신뢰도
판단 지점이 생겼고, 이번 작업으로 ADR-010을 `Accepted`로 올리며 escalation 골격을
게이트웨이에 도입한다.

현재 `LLMGateway.complete_json`은 `LLMRouter.resolve`가 확정한 provider를 그대로 사용한다.
`LLM_TASK_ROUTES`의 모든 `launch`가 `"cloud"`이므로 pre-call escalation은 실질적으로
동작할 대상이 없다. post-call cloud 검증도 `first_provider`가 `CLOUD`가 아닌 경우에만
의미가 있으므로, 현행 launch 라우팅에서는 발화하지 않는다. 따라서 `LLM_ESCALATION_*`
설정과 policy 부착은 현재 구성에서 즉시 사용자 영향이 있는 기능이 아니라, 향후
`future_primary`가 `"local"`인 작업이 실제 로컬 라우팅으로 전환될 때 활성화되는 선행
골격이다.

트리거는 두 부류다.

- **Pre-call 트리거**: 리스크 급등·손실률 급증·뉴스 감성 급변·실적/공시 이벤트·매수매도 질문.
- **Post-call 트리거**: confidence 낮음·schema validation 실패.

## 범위

- `app/adapters/llm/escalation.py` 신설 — `EscalationSignal`, `EscalationPolicy`
- `LLMGateway.complete_json` 수정 — `escalation_signal` optional 인자, pre/post escalation 훅
- `app/adapters/factory.py` 수정 — `escalation_policy` opt-in 부착
- `app/core/config.py` 수정 — `LLM_ESCALATION_ENABLED`, `LLM_ESCALATION_CONFIDENCE_THRESHOLD`
- `docs/decisions/ADR-010-llm-fallback-and-escalation-policy.md` — Status Accepted 갱신
- 비포함: 기술적 폴백, ADR-012 safe template 풀구현, 내용 수준 검증, 메트릭 수집 인프라,
  호출부(도메인 서비스) 변경

## 구성 요소

| 파일 | 변경 | 책임 |
| --- | --- | --- |
| `app/adapters/llm/escalation.py` | 신규 | 입력 신호 보유(`EscalationSignal`)·pre/post 판정(`EscalationPolicy`) |
| `app/adapters/llm/gateway.py` | 수정 | provider override·post-call cloud 검증 훅·privacy/budget guard |
| `app/adapters/factory.py` | 수정 | cloud 모드이고 `LLM_ESCALATION_ENABLED`일 때만 `EscalationPolicy` 부착 |
| `app/core/config.py` | 수정 | escalation 설정 파싱·검증 |
| `docs/decisions/ADR-010-llm-fallback-and-escalation-policy.md` | 수정 | Accepted 확정 |

## Decisions

### Decision MMM — `EscalationSignal`을 게이트웨이 선택적 인자로 전달

`complete_json`에 `escalation_signal: EscalationSignal | None = None`을 추가한다. 기본값
`None`이면 기존 호출부는 escalation 없이 동일하게 동작한다. 신호 취합은 호출부 책임이고,
판정과 provider override는 게이트웨이의 `EscalationPolicy` 책임이다.

### Decision NNN — Pre-call escalation은 LOCAL 라우팅에서만 동작

`should_escalate_before`는 정적 라우팅 결과가 `LOCAL`이 아니면 즉시 `False`를 반환한다.
트리거가 참이어도 payload가 `PrivacyGate.guard()`를 통과하지 못하면 승격을 생략하고 로컬
경로를 유지한다. 이 guardrail은 하드 실패가 아니라 "cloud로 표현할 수 없는 payload는
승격하지 않는다"는 의미다.

### Decision OOO — Post-call cloud 검증은 confidence 임계치·schema 실패에 반응

`first_provider`가 `CLOUD`가 아니고 결과의 `confidence`가 설정 임계치 미만이거나
`schema.model_validate(output)`이 실패하면 cloud client로 검증 재호출한다. 검증 재호출도
`PrivacyGate.guard()`와 `call_budget.consume()`을 거친다. guard 또는 budget 단계에서 실패하면
cloud 재호출이 실제 수행되지 않았으므로 원본 결과를 반환하고 `escalated=False`를 유지한다.
cloud transport 호출 뒤 schema 실패나 예외가 발생하면 원본 결과를 반환하되 재호출은 시도된
것이므로 `escalated=True`로 관측한다.

### Decision PPP — `LLMCompletionResult.escalated` 추가

`LLMCompletionResult`에 `escalated: bool = False`를 추가한다. 값의 의미는 provider override
또는 cloud 검증 재호출이 실제 수행됐다는 것이다. cloud client 부재, privacy boundary 위반,
budget 선행 실패처럼 재호출이 수행되지 않은 경로는 `False`다.

### Decision QQQ — ADR-010을 Accepted로 확정

#139 구현 착수로 ADR-010의 풀구현 트리거가 충족됐다. 기술적 폴백과 ADR-012 safe template
품질 폴백은 후속으로 남긴다.

## 테스트

- `EscalationSignal` frozen 불변성 및 필드 기본값.
- `EscalationPolicy.should_escalate_before`의 각 trigger, no-trigger, cloud provider 분기.
- `EscalationPolicy.should_verify_after`의 confidence 임계치, schema 실패, cloud provider 분기.
- 게이트웨이 pre-call override, CloudSafe 불가 payload의 승격 생략, signal 없음.
- 게이트웨이 post-call 검증 성공, cloud client 부재, schema 실패, transport 예외, budget 실패,
  boundary 위반.
- 팩토리의 `LLM_ESCALATION_ENABLED=True` + cloud 모드 policy 부착.
- config의 threshold 파싱과 범위 검증.

## ADR 판단

신규 ADR 불필요 — ADR-010 확정 갱신으로 충분하다.

## Failure Record 판단

불필요 — ADR-010 Follow-up으로 계획된 구현이며 결함 마감이 아니다.
