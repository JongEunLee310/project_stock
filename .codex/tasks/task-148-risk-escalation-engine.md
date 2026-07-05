# Codex Handoff Task

## Source Issue

- BE #139 — 위험도 Escalation 엔진 — high_risk/low_confidence 시 cloud 승격·검증
- Epic BE #141
- 설계: `docs/designs/081-risk-escalation-engine.md` (Decisions MMM·NNN·OOO·PPP)

## Task Summary

`app/adapters/llm/escalation.py`에 `EscalationPolicy`를 신설하고 `LLMGateway`의
LOCAL 라우트에 pre-call(입력 `RiskLevel.HIGH` 시 CLOUD 승격)·post-call(LOCAL 결과의
스키마 검증 실패·confidence 임계 미만 시 CLOUD 1회 재호출) escalation을 추가한다.
호출부 평가기 `derive_risk_level(bundle)`을 신설해 `LLMAnalysisService`가 사용한다.
ADR-010을 Accepted로 확정 갱신한다.

## Goal

- 라우터가 LOCAL을 반환하는 작업에서 `risk_level=RiskLevel.HIGH`로 호출하면 local
  client 호출 없이 CLOUD 경로(guard → cache → budget → 호출 → store)로 실행되고
  `escalated=True`, `escalation_trigger="HIGH_RISK_INPUT"`이 표시된다.
- LOCAL 결과가 스키마 검증에 실패하거나 `confidence`가 임계 미만이면 CLOUD로 1회
  재호출하고 그 결과를 반환한다(트리거 각각 `SCHEMA_VALIDATION_FAILED` /
  `LOW_CONFIDENCE`).
- CloudSafe 비허용 payload(sensitivity가 `AGGREGATED`/`PUBLIC` 밖)는 승격하지
  않는다 — pre-call이면 LOCAL 그대로 진행, post-call이면 원 실패를 기존대로 전파.
- CLOUD 라우트와 정책 미부착 게이트웨이의 기존 동작은 변하지 않는다.
- `derive_risk_level`이 severity `"high"` signal 존재 또는 손실 임계 이하
  `unrealized_return`에서 `HIGH`를 반환하고, `LLMAnalysisService.run_analysis`가
  이를 게이트웨이에 전달한다.
- 검증 4종(ruff·mypy·pytest·alembic heads)이 전부 통과한다.

## Background

- 게이트웨이(`app/adapters/llm/gateway.py`)의 CLOUD 경로 순서:
  `privacy_gate.guard` → cache lookup(부착 시) → `call_budget.consume`(부착 시) →
  `client.complete_json` → cache store. LOCAL 경로는 guard·cache·budget 없이 바로 호출.
- 라우팅은 정적(`app/adapters/llm/router.py`의 `TaskRoute.launch`)이고 현재 모든
  작업이 `cloud`다. escalation은 LOCAL 라우트 등장 전까지 dormant — 테스트는 커스텀
  routes를 주입해 LOCAL 라우트를 만든다.
- `RiskLevel` enum은 `app/adapters/llm/types.py`에 이미 존재한다(LOW/MEDIUM/HIGH).
- `LLMAnalysisResult`(`app/domains/llm_analysis/schema.py`)에
  `confidence: float`(0.0–1.0)이 이미 있다. post-call confidence 판정은 output dict의
  `confidence` 필드가 존재할 때만 수행하고, 없으면 판정을 생략한다.
- `LLMContextBundle`·signal severity(`"high"`/`"medium"`/`"low"`)·
  `portfolio_context.unrealized_return`은 `app/domains/llm_context/schema.py`,
  `context_builder.py` 참조.
- `PrivacyGate.guard`는 위반 시 `CloudBoundaryViolationError`를 던진다
  (`app/adapters/llm/privacy.py`). 승격 판정 시 이 예외를 잡아 "승격 불가"로
  처리하되, CLOUD가 원래 라우트인 경우의 guard 예외는 기존대로 전파해야 한다.
- config의 `LLM_DAILY_CALL_LIMIT`·`LLM_CACHE_TTL_SECONDS`에 `""` → `None`
  field_validator 선례가 있다(`app/core/config.py`).
- ADR-010(`docs/decisions/ADR-010-llm-fallback-and-escalation-policy.md`)은
  Proposed — Deferred 상태다. Status를 Accepted로 올리고 Decision 절을 설계 081의
  확정 내용으로 갱신한다 — escalation은 본 구현으로 확정, 기술적 폴백은 "예외 전파
  유지" 채택, 품질 폴백(safe template)은 ADR-012 확정 시 함께. Follow-up의 "#139 /
  #140 착수 대기" 문구도 갱신한다. 본문 산문은 한국어, 헤더·코드 기호는 영어.

## Implementation Scope

1. `app/adapters/llm/escalation.py` (신규):
   - `EscalationTrigger(str, Enum)` — `HIGH_RISK_INPUT` / `LOW_CONFIDENCE` /
     `SCHEMA_VALIDATION_FAILED`.
   - `EscalationPolicy`:
     - `__init__(confidence_threshold: float)`
     - `evaluate_pre_call(risk_level: RiskLevel) -> EscalationTrigger | None` —
       `HIGH`면 `HIGH_RISK_INPUT`, 그 외 `None`.
     - `evaluate_post_call(output: dict[str, Any], schema: type[BaseModel]) ->
       EscalationTrigger | None` — `schema.model_validate(output)` 실패면
       `SCHEMA_VALIDATION_FAILED`; 통과 후 output에 `confidence` 키가 있고 값이
       임계 미만이면 `LOW_CONFIDENCE`; 그 외 `None`.
2. `app/adapters/llm/gateway.py`:
   - `__init__`에 `escalation_policy: EscalationPolicy | None = None` 추가.
   - `complete_json`에 `risk_level: RiskLevel = RiskLevel.LOW` 키워드 인자 추가
     (기존 호출부 무변경).
   - LOCAL 라우트 + 정책 부착 시:
     - pre-call: `evaluate_pre_call`이 트리거를 반환하고 payload가 CloudSafe 허용
       범위면 CLOUD 경로로 실행. guard 불가 payload면 승격 없이 LOCAL 진행.
     - post-call: LOCAL 결과에 `evaluate_post_call` 적용, 트리거 시 CLOUD 경로로
       1회 재호출(같은 CloudSafe 판정 적용, 불가 시 승격 없이 원 결과 반환 — 스키마
       실패의 경우 기존처럼 output을 그대로 반환해 호출부 검증이 실패를 처리).
     - 승격된 CLOUD 호출은 기존 CLOUD 경로와 동일하게 guard·cache·budget을 적용
       (기존 CLOUD 처리 로직을 헬퍼로 추출해 재사용 권장).
   - `LLMCompletionResult`에 `escalated: bool = False`,
     `escalation_trigger: str | None = None` 추가.
   - 승격 발생 시 `logging` warning 1줄(task_type·trigger·local→cloud). payload
     내용은 로그에 넣지 않는다.
   - CLOUD 라우트에는 정책을 적용하지 않는다.
3. `app/domains/llm_context/risk.py` (신규):
   - `derive_risk_level(bundle: LLMContextBundle) -> RiskLevel` — symbol_cards의
     signal 중 severity `"high"` 존재 시 `HIGH`; 어떤 카드의
     `portfolio_context.unrealized_return`이 손실 임계 상수
     (`HIGH_RISK_UNREALIZED_RETURN = -0.10`, 모듈 상수) 이하이면 `HIGH`; 그 외 `LOW`.
     portfolio_context가 `None`이거나 `unrealized_return`이 `None`이면 손실 축 생략.
4. `app/domains/llm_analysis/service.py` — `run_analysis`에서
   `derive_risk_level(bundle)` 결과를 `complete_json(..., risk_level=...)`로 전달.
5. `app/core/config.py` — `LLM_ESCALATION_CONFIDENCE_THRESHOLD: float | None = None`
   + `""` → `None` field_validator(기존 validator 확장 방식 허용). 값이 있으면
   0.0–1.0 범위 검증.
6. `app/adapters/factory.py` — `get_llm_gateway()` cloud 분기에서
   `LLM_ESCALATION_CONFIDENCE_THRESHOLD`가 `None`이 아닐 때만
   `EscalationPolicy(threshold)` 부착. mock·local 분기는 변경하지 않는다.
7. `.env.example` — `LLM_ESCALATION_CONFIDENCE_THRESHOLD=` 항목 추가(빈 값 =
   escalation 비활성, cloud 모드에만 적용된다는 주석 포함).
8. `docs/decisions/ADR-010-llm-fallback-and-escalation-policy.md` — Background 절
   참조. Status `Accepted` 갱신.
9. `docs/backend-v0.2.md` — 환경 변수 설명 추가(기존 `LLM_CACHE_TTL_SECONDS` 서술
   패턴 준수).

## Out of Scope

- cloud 검증 부착(verify 모드) — 채택하지 않음(설계 Decision MMM).
- safe template 폴백·저장 게이트 — ADR-012 소관.
- 기술적 폴백(재시도·대체 transport) — "예외 전파 유지"로 확정(Decision PPP).
- 로컬 provider 실 구현, 라우팅 테이블(`LLM_TASK_ROUTES`) 변경.
- `LLMAnalysisService` 외 다른 호출부(뉴스 요약·브리핑 등)의 평가기 연동.
- DB 스키마·마이그레이션 변경(이번 작업에 없음).
- `docs/designs/081-risk-escalation-engine.md` 수정(오케스트레이터 소유).

## Protected Files

- `docs/decisions/ADR-010-llm-fallback-and-escalation-policy.md` — 이 파일에 한해
  수정을 허용한다(Status Accepted 확정·Decision/Follow-up 갱신). 다른 protected
  파일은 수정 금지.

## Requirements

- 기존 호출부·기존 테스트가 무변경으로 통과해야 한다(`risk_level` 기본값·정책 opt-in).
- escalation 판단은 게이트웨이 안에서만 일어난다. 호출부가 provider를 바꾸는 코드를
  추가하지 않는다.
- 승격 호출은 budget을 소비하며, `LLMBudgetExceededError`는 기존대로 전파한다.
- post-call 재승격은 1회로 제한한다(CLOUD 결과에 대한 재평가 없음).
- 타입 힌트 완전(mypy 통과), sync 코드베이스 유지(`AsyncMock` 금지).

## Test Requirements

- `EscalationPolicy` 단위: HIGH → 트리거 / MEDIUM·LOW → None; 스키마 실패 →
  `SCHEMA_VALIDATION_FAILED`; confidence 임계 미만 → `LOW_CONFIDENCE`; confidence
  부재 → None; 임계 이상 → None.
- `derive_risk_level` 단위: high signal → HIGH; 손실 임계 이하 → HIGH; 해당 없음 →
  LOW; portfolio_context 부재 시 손실 축 생략.
- 게이트웨이 통합(커스텀 routes로 LOCAL 라우트 구성, fake client 주입):
  - pre-call 승격: local 미호출·cloud 호출·`escalated=True`·budget 소비.
  - post-call 승격: low confidence·스키마 불일치 각각에서 cloud 재호출·승격 결과 반환.
  - 정상 LOCAL 결과: 승격 없음·`escalated=False`.
  - CloudSafe 비허용 payload(RAW/SEMI) + HIGH: 승격 없이 LOCAL 진행.
  - CLOUD 라우트: 정책 미적용(기존 흐름).
  - 정책 미부착: 기존 동작 보존.
- 호출부: `run_analysis`가 `derive_risk_level` 결과를 전달하는지 검증.
- config: `""` → `None` 파싱, 범위 밖 값 거부. 팩토리: 임계값 설정 + cloud일 때만 부착.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`
- `uv run alembic heads`

## Documentation Impact

- `docs/decisions/ADR-010-llm-fallback-and-escalation-policy.md` — Accepted 확정.
- `docs/backend-v0.2.md` — 환경 변수 추가.
- 설계 `docs/designs/081-risk-escalation-engine.md`는 이미 작성됨(수정 불필요).

## ADR Need

신규 ADR 불필요 — ADR-010 확정 갱신으로 충분(설계 Decision PPP).

## Failure Record Need

불필요 — 계획된 Phase 2 항목의 트리거 충족에 따른 구현이며 결함 마감이 아니다.

## Risk Level

Medium — 게이트웨이라는 단일 choke point를 수정하므로 모든 LLM 호출 경로에 영향
가능성이 있으나, 정책 opt-in·`risk_level` 기본값으로 기존 동작이 보존되고 LOCAL
라우트가 아직 없어 프로덕션 경로 변화는 사실상 없다.

## Expected Output

- 신규: `app/adapters/llm/escalation.py`, `app/domains/llm_context/risk.py`,
  관련 테스트 파일.
- 수정: `app/adapters/llm/gateway.py`, `app/domains/llm_analysis/service.py`,
  `app/core/config.py`, `app/adapters/factory.py`, `.env.example`,
  `docs/decisions/ADR-010-llm-fallback-and-escalation-policy.md`,
  `docs/backend-v0.2.md`.
- 변경 파일 목록·검증 결과·잔여 리스크 보고(AGENTS.md Done Definition 준수).

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
