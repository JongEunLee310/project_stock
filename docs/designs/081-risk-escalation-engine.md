# 081 — Risk Escalation Engine (BE #139)

## Status

Draft

## 배경

이슈 #139는 투자 판단 영향이 큰 입력이나 신뢰하기 어려운 결과에 대해 로컬 라우팅을
클라우드로 승격하는 위험도 escalation을 요구한다. ADR-010(Proposed — Deferred)은
풀구현 트리거로 두 가지를 명시했다 — (a) 브리핑 기능 설계 착수로 폴백 요구가 구체화될 때,
(b) 어떤 작업의 `future_primary`가 로컬로 전환될 때. (a)는 포트폴리오·대시보드 브리핑
구현(PR #151)으로 충족됐고, 선행 이슈 #137(ADR)·#138(캐시)은 모두 닫혔다. 이번 작업으로
ADR-010을 확정(Accepted)하고 escalation 엔진을 구현한다.

현재 상태를 짚으면 다음과 같다.

- 모든 LLM 호출은 `LLMGateway.complete_json(task_type, payload, schema, system_prompt)`
  단일 경로로 수렴되어 있다(`app/adapters/llm/gateway.py`). CLOUD 경로는
  `privacy_gate.guard` → cache lookup → `call_budget.consume` → 호출 → cache store 순이다.
- 라우팅은 정적이다(`LLMRouter.resolve` → `TaskRoute.launch`). 현재 모든 작업의
  `launch`는 `cloud`이고, 로컬 provider는 stub이다(`LocalLLMProvider`는
  `NotImplementedError`). 따라서 escalation 엔진은 LOCAL 라우트가 실제로 등장하기
  전까지 dormant하지만, 정책·경계를 지금 게이트웨이 안에 고정해 두는 것이 이 작업의
  목적이다(로컬 전환 시 후행 작업이 게이트웨이에 몰리는 리스크를 ADR-010이 명시).
- `LLMAnalysisResult`(`app/domains/llm_analysis/schema.py`)에 `confidence: float`
  (0.0–1.0)이 이미 존재한다. `RiskLevel` enum(`app/adapters/llm/types.py`)도 존재하지만
  게이트웨이 시그니처에는 아직 위험도 입력이 없다.

## 범위

- `app/adapters/llm/escalation.py` 신설 — `EscalationPolicy` / `EscalationTrigger`
- `app/adapters/llm/gateway.py` 수정 — `risk_level` 인자, pre-call 승격, post-call
  (LOCAL 결과 한정) 재호출
- `app/domains/llm_context/risk.py` 신설 — `derive_risk_level(bundle)` 호출부 평가기
- `app/domains/llm_analysis/service.py` 수정 — 평가기 결과를 게이트웨이에 전달
- `app/core/config.py` / `app/adapters/factory.py` / `.env.example` — 임계값 설정·부착
- `docs/decisions/ADR-010-llm-fallback-and-escalation-policy.md` — Status Accepted 갱신
- 비포함: cloud 검증 부착(verify 모드), safe template 폴백(ADR-012 소관), 기술적
  폴백(재시도·대체 transport), 로컬 provider 실 구현, 브리핑 등 다른 호출부의 평가기 연동

## 구성 요소

| 파일 | 변경 | 책임 |
| --- | --- | --- |
| `app/adapters/llm/escalation.py` | 신규 | 승격 여부 판단(pre/post-call) |
| `app/adapters/llm/gateway.py` | 수정 | LOCAL 라우트에서 정책 적용·CLOUD 승격 실행 |
| `app/domains/llm_context/risk.py` | 신규 | 도메인 신호 → `RiskLevel` 환산 |
| `app/domains/llm_analysis/service.py` | 수정 | bundle 평가 결과를 `risk_level`로 전달 |
| `app/core/config.py` | 수정 | `LLM_ESCALATION_CONFIDENCE_THRESHOLD` |
| `app/adapters/factory.py` | 수정 | cloud 모드에서 정책 부착 |
| `.env.example` | 수정 | 임계값 항목 |
| `docs/decisions/ADR-010-...md` | 수정 | Accepted 확정 |

### EscalationPolicy 시그니처

- `EscalationTrigger(str, Enum)` — `HIGH_RISK_INPUT` / `LOW_CONFIDENCE` /
  `SCHEMA_VALIDATION_FAILED`
- `EscalationPolicy`:
  - `__init__(confidence_threshold: float)` — 임계값은 팩토리가 설정에서 주입
  - `evaluate_pre_call(risk_level: RiskLevel) -> EscalationTrigger | None` —
    `HIGH`면 `HIGH_RISK_INPUT`, 그 외 `None`
  - `evaluate_post_call(output: dict, schema: type[BaseModel]) -> EscalationTrigger | None`
    — 스키마 검증 실패면 `SCHEMA_VALIDATION_FAILED`, 통과했고 `confidence` 필드가
    존재하며 임계 미만이면 `LOW_CONFIDENCE`, 그 외 `None`

### derive_risk_level 시그니처

- `derive_risk_level(bundle: LLMContextBundle) -> RiskLevel` — 이슈 #139의 도메인
  트리거를 `RiskLevel`로 환산하는 호출부 평가기. 책임:
  - symbol_cards의 signal 중 severity `"high"`가 하나라도 있으면 `HIGH`
    (리스크 급등·뉴스 감성 급변·실적·공시 이벤트는 모두 signal로 유입되는 신호다)
  - portfolio_context의 `unrealized_return`이 손실 임계(모듈 상수) 이하이면 `HIGH`
    (손실률 급증)
  - 그 외 `LOW`

### LLMGateway 변경

- `complete_json(..., risk_level: RiskLevel = RiskLevel.LOW)` 인자 추가(기본값으로
  기존 호출부 무변경)
- `__init__`에 `escalation_policy: EscalationPolicy | None = None` 추가
- `LLMCompletionResult`에 `escalated: bool = False`,
  `escalation_trigger: str | None = None` 필드 추가(관측용)

## Decisions

### Decision MMM — 게이트웨이 단일 지점의 라우팅 오버라이드로 구현, cloud 검증 부착은 채택하지 않음

escalation은 게이트웨이 안에서 라우팅 결과를 CLOUD로 바꾸는 런타임 오버라이드로 구현한다.

- **pre-call.** 라우터가 LOCAL을 반환했고 정책이 부착되어 있으며 입력 `risk_level`이
  `HIGH`이면, LOCAL 호출 없이 처음부터 CLOUD 경로로 실행한다.
- **post-call.** LOCAL 호출이 성공했으나 결과가 스키마 검증에 실패하거나 `confidence`가
  임계 미만이면, CLOUD 경로로 한 번 재호출하고 그 결과를 반환한다. 재승격은 1회로
  제한한다(CLOUD 결과가 다시 나쁘면 기존과 동일하게 예외 전파·호출부 처리).
- **CLOUD 라우트에는 escalation이 없다.** 이미 최강 백엔드이므로 승격 대상이 없고,
  CLOUD 결과의 품질 문제는 ADR-012(safe template)의 소관으로 남긴다. post-call 검증도
  LOCAL 결과에만 적용한다 — 게이트웨이 레벨 검증의 전면 일반화는 ADR-012 확정 시점의
  일이며, 여기서는 escalation 트리거 판정에 필요한 최소 범위만 도입한다.

이슈 원문의 "cloud 에스컬레이션 **또는** cloud 검증 부착" 중 승격만 채택한다. 검증
부착(로컬 결과를 클라우드가 재검토)은 검증 프롬프트·판정 스키마의 별도 설계가 필요하고
비용이 이중으로 들며, 로컬이 stub인 현재 소비처가 없다. 필요 신호가 생기면 후속 이슈로
분리한다.

기각 대안: 호출부별 escalation(ADR-010 제약 2 위반 — 단일 choke point 이탈),
cloud 검증 부착(위 사유).

### Decision NNN — 트리거 측정은 입력 RiskLevel + 출력 confidence + 스키마 검증, 도메인 이벤트 환산은 호출부 책임

ADR-010 미결 질문 1(트리거를 무엇으로 측정하는가)에 대한 답은 "둘 다"다.

- **입력 축.** 게이트웨이는 도메인을 모르므로, 이슈의 도메인 트리거(리스크 급등·손실률
  급증·뉴스 감성 급변·실적·공시 이벤트)는 호출부 평가기 `derive_risk_level`이
  `LLMContextBundle`에서 판정해 `RiskLevel`로 환산한다. 게이트웨이는 `RiskLevel`이라는
  단일 어휘만 소비한다. 신호 계열 트리거는 signal severity로, 손실률은
  `unrealized_return`으로 판정한다.
- **출력 축.** 모델이 보고한 `confidence`(출력 dict의 `confidence` 필드, 없으면 판정
  생략)와 스키마 검증 결과를 post-call 트리거로 쓴다. `LLMAnalysisResult`가 이미
  `confidence`를 갖고 있어 별도 계약 추가가 없다.
- **매수·매도 질문 트리거는 후속으로 남긴다.** 현재 `user_intent`는 태스크별 고정
  문구여서(`_USER_INTENT_BY_TASK_TYPE`) 자유 입력 질문이 존재하지 않는다. AGENT
  태스크가 자유 입력을 받게 되는 시점에 평가기에 축을 추가한다(확장 지점은
  `derive_risk_level` 내부에 주석이 아닌 설계 문서로만 기록).

기각 대안: 게이트웨이가 payload 내용을 들여다보며 도메인 트리거를 직접 판정(어댑터
계층이 도메인 스키마에 역의존 — 계층 침범), 프롬프트로 위험도 자가 판정 요청(비결정적·
비용 추가).

### Decision OOO — 승격 경로는 기존 CLOUD 경로와 동일하며 CloudSafe 불가 payload는 승격하지 않음

- 승격된 호출은 기존 CLOUD 경로를 그대로 탄다 — `privacy_gate.guard` → cache lookup →
  `call_budget.consume` → 호출 → cache store. 별도의 두 번째 클라우드 경로를 만들지
  않는다(경계·비용 통제가 한 곳에 유지).
- **프라이버시 경계가 escalation보다 우선한다**(ADR-010 제약 1). 승격 시도 시
  `privacy_gate.guard`가 실패하는 payload(CloudSafe로 표현 불가·sensitivity 비허용)는
  승격 대상이 아니다 — pre-call이면 LOCAL 경로를 그대로 진행하고, post-call이면 승격
  없이 원 결과의 실패를 기존 방식대로 전파한다. guard 예외를 escalation이 삼켜서
  경계 위반으로 이어지게 하지 않는다.
- 승격 호출도 budget을 소비한다. escalation은 예산 상한(`DailyCallBudget`)의 예외가
  아니다 — 예산 초과 시 `LLMBudgetExceededError`가 기존과 동일하게 전파된다.
- **관측 가능성**(ADR-010 제약 4): 승격 발생 시 warning 로그(task_type·트리거·
  provider 전환)를 남기고, `LLMCompletionResult.escalated` / `escalation_trigger`로
  호출부가 식별할 수 있게 한다. payload 내용은 로그에 남기지 않는다.

기각 대안: 승격 호출의 budget 면제(위험도가 높다고 비용 상한을 우회하면 상한의 의미가
사라짐), 승격 전용 별도 경로(캐시·경계 로직 중복).

### Decision PPP — ADR-010을 Accepted로 확정하고 기술적 폴백은 "예외 전파 유지"로 함께 결정

풀구현 트리거(브리핑 기능 존재)가 충족됐으므로 ADR-010 Status를 `Accepted`로 올린다.
확정 내용은 세 갈래다.

- **위험도 escalation** — 본 설계(MMM·NNN·OOO)로 확정·구현.
- **기술적 폴백** — "폴백 없이 실패를 그대로 전파"를 현행 결정으로 채택한다. 현재
  영속화 소비처는 배경 워커 잡뿐이라 예외 전파로 충분하며, 사용자 대면 즉시 응답
  기능이 생기면 재검토한다(ADR-010이 이미 대안으로 기록한 방향).
- **품질 폴백** — 종착지(safe template)는 ADR-012와 공유하므로, ADR-012가 확정될 때
  함께 구체화한다. 본 작업의 post-call 검증은 escalation 트리거 판정용이며 저장
  게이트·safe template를 도입하지 않는다.

## 테스트

- `EscalationPolicy` 단위: `HIGH` → `HIGH_RISK_INPUT`, `MEDIUM`/`LOW` → `None`;
  스키마 검증 실패 → `SCHEMA_VALIDATION_FAILED`; confidence 임계 미만 →
  `LOW_CONFIDENCE`; confidence 필드 부재 → `None`; 임계 이상 → `None`.
- `derive_risk_level` 단위: severity `"high"` signal 존재 → `HIGH`; 손실 임계 이하
  `unrealized_return` → `HIGH`; 둘 다 없음 → `LOW`; portfolio_context 부재 시 손실
  축 생략.
- 게이트웨이 통합(LOCAL 라우트 커스텀 router 주입, fake client):
  - pre-call: `risk_level=HIGH` → local client 미호출·cloud client 호출·
    `escalated=True`·guard 적용·budget 소비.
  - post-call: local 결과 confidence 임계 미만/스키마 불일치 → cloud 재호출·승격
    결과 반환; local 결과 정상 → 승격 없음·`escalated=False`.
  - CloudSafe 비허용 payload + `HIGH` → 승격하지 않고 LOCAL 진행.
  - CLOUD 라우트 → 정책 미적용(기존 흐름 그대로).
  - 정책 미부착 → 기존 동작 보존(`risk_level` 전달해도 무시).
- 호출부: `LLMAnalysisService.run_analysis`가 `derive_risk_level` 결과를 게이트웨이에
  전달. config: `""` → `None` 파싱, 범위(0.0–1.0) 검증.

## ADR 판단

신규 ADR 불필요 — ADR-010 확정 갱신으로 충분하다(본 설계 Decision PPP).

## Failure Record 판단

불필요 — 계획된 Phase 2 항목의 트리거 충족에 따른 구현이며 결함 마감이 아니다.
