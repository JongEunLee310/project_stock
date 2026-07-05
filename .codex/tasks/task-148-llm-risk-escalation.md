# Codex Handoff Task

## Source Issue

- BE #139 — [LLM] 위험도 Escalation 엔진 — high_risk/low_confidence 시 cloud 승격·검증
- Epic BE #141
- 설계: `docs/designs/081-llm-risk-escalation-engine.md` (Decisions MMM·NNN·OOO·PPP·QQQ)

## Task Summary

`app/adapters/llm/escalation.py`에 `EscalationSignal`·`EscalationPolicy`를 신설하고
`LLMGateway.complete_json`에 pre-call provider override와 post-call cloud 검증 훅을
추가한다. `LLM_ESCALATION_ENABLED` 설정이 켜져 있고 cloud 모드일 때만 팩토리가
policy를 부착한다. ADR-010을 Accepted로 확정 갱신한다.

## Goal

- pre-call: `escalation_signal`의 트리거 필드(`risk_level=HIGH`·`loss_spike`·
  `news_sentiment_swing`·`event_flag`·`trade_question`) 중 하나라도 참이고 라우팅이
  `LOCAL`이면 provider가 `CLOUD`로 override되고 결과에 `escalated=True`가 표시된다.
- post-call: 1차 결과가 confidence 임계치 미만이거나 schema 검증 실패이고 1차 provider가
  `CLOUD`가 아니면 cloud 검증 재호출이 수행되고 결과가 대체되며 `escalated=True`가
  표시된다.
- `escalation_signal=None`(기본)이거나 `escalation_policy` 미부착이면 기존 경로가
  그대로 보존된다(기존 테스트 전부 통과).
- `LLM_ESCALATION_ENABLED` 미설정(기본 `False`) 시 policy가 부착되지 않는다.
- 검증 4종(ruff·mypy·pytest·alembic heads)이 전부 통과한다.

## Background

- 모든 LLM 호출은 `LLMGateway.complete_json(task_type, payload, schema, system_prompt)`
  단일 경로다(`app/adapters/llm/gateway.py`). CLOUD 라우팅 시
  `privacy_gate.guard` → cache lookup → `call_budget.consume`(부착 시) →
  `client.complete_json` → cache store 순.
- `LLMRouter.resolve`(`app/adapters/llm/router.py`)는 정적 launch 라우팅이며 현재 전
  task가 `"cloud"`다. 따라서 pre-call escalation은 `future_primary` 로컬 전환 이후
  실질 동작하는 골격이다(설계 Decision NNN). post-call 검증은 지금도 의미가 있다 —
  단 1차가 CLOUD인 경우 재호출을 건너뛰므로, 실질 발화는 LOCAL 라우팅 이후다.
- `RiskLevel` enum(`LOW`/`MEDIUM`/`HIGH`)은 `app/adapters/llm/types.py`에 이미 있다.
- `LLMCompletionResult`(gateway.py)는 `output`·`provider`·`model_name`·`cached` frozen
  dataclass. 여기에 `escalated: bool = False`를 추가한다(설계 Decision PPP).
- config의 `LLM_DAILY_CALL_LIMIT`·`LLM_CACHE_TTL_SECONDS`에 `""` → `None`
  field_validator 선례가 있다(`app/core/config.py`).
  `LLM_ESCALATION_CONFIDENCE_THRESHOLD`도 같은 방식으로 처리한다.
- ADR-010(`docs/decisions/ADR-010-llm-fallback-and-escalation-policy.md`)은
  Proposed — Deferred 상태다. Status를 Accepted로 올리고 Decision 절을 설계 081의
  확정 내용(pre/post 트리거 분류·게이트웨이 단일 지점·프라이버시 경계·관측 필드)으로
  갱신한다. 기술적 폴백(재시도·transport 폴백)은 미결 질문으로 남긴다. 본문 산문은
  한국어, 헤더·코드 기호는 영어.

## Implementation Scope

1. `app/adapters/llm/escalation.py` (신규):
   - `EscalationSignal` frozen dataclass — `risk_level: RiskLevel = RiskLevel.LOW`,
     `loss_spike: bool = False`, `news_sentiment_swing: bool = False`,
     `event_flag: bool = False`, `trade_question: bool = False`.
   - `EscalationPolicy`:
     - `__init__(confidence_threshold: float | None = None)`
     - `should_escalate_before(signal: EscalationSignal, resolved_provider: str) -> bool`
       — `resolved_provider != LOCAL`이면 즉시 `False`. 트리거 필드 중 하나라도 참이면
       `True`(`risk_level`은 `HIGH`일 때만 트리거).
     - `should_verify_after(output: dict, schema: type[BaseModel], first_provider: str) -> bool`
       — `first_provider == CLOUD`이면 즉시 `False`. `schema.model_validate(output)`이
       `ValidationError`를 던지면 `True`. confidence 조건은 `confidence_threshold`가
       `None`이 아닐 때만 활성 — `output.get("confidence")`가 수치이고 임계치 미만이면
       `True`. confidence 키 부재·비수치 값은 confidence 조건으로는 트리거하지 않는다.
2. `app/adapters/llm/gateway.py`:
   - `__init__`에 `escalation_policy: EscalationPolicy | None = None` 추가.
   - `complete_json`에 `escalation_signal: EscalationSignal | None = None` 인자 추가.
   - pre-call: policy와 signal이 모두 있고 `should_escalate_before(signal, provider)`가
     참이면 `provider = CLOUD`로 override 후 기존 CLOUD 경로(guard·cache·budget)를
     그대로 탄다. override 시 `escalated=True`. 경고성 info/warning 로그 1건
     (설계 "관측 가능" 제약 — 로그에 payload 내용은 넣지 않는다).
   - post-call: policy가 있고 `should_verify_after(output, schema, first_provider)`가
     참이면 cloud client로 검증 재호출. 재호출 경로는 `privacy_gate.guard`와
     `call_budget.consume`을 동일하게 거치고, 캐시 lookup/store는 적용하지 않는다
     (설계 Decision OOO). 재호출 성공 시 결과 대체 + `escalated=True`. 재호출 결과도
     `schema` 검증 실패이거나 재호출이 예외를 던지면 원래 결과 반환 + 경고 로그
     (`escalated`는 재호출이 수행됐으므로 `True`로 둘지 여부는 아래 Requirements 참조).
   - cloud client 미구성(`clients.get(CLOUD) is None`) 시 post-call 재호출은 건너뛰고
     경고 로그만 남긴다.
   - `LLMCompletionResult`에 `escalated: bool = False` 추가.
3. `app/adapters/llm/__init__.py` — `EscalationPolicy`·`EscalationSignal` export 추가.
4. `app/core/config.py` — `LLM_ESCALATION_ENABLED: bool = False`,
   `LLM_ESCALATION_CONFIDENCE_THRESHOLD: float | None = None`(`""` → `None`
   field_validator, 값이 있으면 0.0 초과 1.0 이하 검증).
5. `app/adapters/factory.py` — `get_llm_gateway()` cloud 분기에서
   `LLM_ESCALATION_ENABLED=True`일 때만
   `EscalationPolicy(settings.LLM_ESCALATION_CONFIDENCE_THRESHOLD)` 부착.
   mock·local 분기는 변경하지 않는다.
6. `.env.example` — `LLM_ESCALATION_ENABLED=false`,
   `LLM_ESCALATION_CONFIDENCE_THRESHOLD=` 항목 추가(주석: cloud 모드에만 적용,
   빈 임계치 = confidence 트리거 비활성).
7. `docs/decisions/ADR-010-llm-fallback-and-escalation-policy.md` — Status `Accepted`
   갱신, Decision 절에 확정 내용 반영, Follow-up의 "#139 착수 대기" 문구를 구현 완료로
   갱신. 기술적 폴백은 미결로 유지.
8. `docs/backend-v0.2.md` — `LLM_ESCALATION_ENABLED`·
   `LLM_ESCALATION_CONFIDENCE_THRESHOLD` 환경 변수 설명 추가.

## Out of Scope

- 도메인 서비스(호출부) 변경 — `EscalationSignal` 취합·전달은 후속 이슈(#140 등)의
  호출부 작업이다.
- 기술적 폴백(타임아웃·rate limit 재시도), ADR-012 safe template 풀구현, 내용 수준
  검증, 메트릭 수집 인프라.
- `app/adapters/llm/router.py`·`privacy.py`·`budget.py`·`cache.py`·프롬프트 변경.
- DB 스키마 변경·migration 생성.

## Protected Files

- `docs/decisions/ADR-010-llm-fallback-and-escalation-policy.md` — **이번 작업에서
  변경 허용** (Status Accepted 확정 갱신, Implementation Scope 7 범위로 한정).
- 그 외 `docs/decisions/` 하위 파일 — 변경 금지.
- `AGENTS.md`, `CLAUDE.md`, `.codex/`(본 task 파일 제외), `.github/workflows/ci.yml`,
  `docs/harness/` — 변경 금지.
- `app/adapters/llm/router.py`, `app/adapters/llm/privacy.py`,
  `app/adapters/llm/budget.py`, `app/adapters/llm/cache.py`,
  `app/adapters/llm/prompts/` — 변경 금지.
- `app/domains/` — 변경 금지.
- `alembic/versions/` — 변경 금지.

## Requirements

- escalation 판단은 게이트웨이 단일 지점에서만 일어난다. 호출부에 분기를 추가하지
  않는다(ADR-010 제약·설계 Decision MMM).
- pre-call override로 CLOUD가 된 경로는 기존 CLOUD 규율(privacy_gate·cache·budget)을
  전부 거친다. post-call 재호출은 guard·budget은 거치되 캐시는 미적용(Decision OOO).
- `escalated` 의미는 "escalation 동작(override 또는 검증 재호출)이 수행됐다"로 한다 —
  재호출이 수행됐다면 최종 결과가 원래 결과로 남더라도 `escalated=True`.
- 에스컬레이션 발생·재호출 실패는 로그로 관측 가능해야 한다. 로그에 payload·output
  내용을 포함하지 않는다(키·provider·task_type 수준만).
- `should_verify_after`의 schema 검증은 pydantic `model_validate` 시도로 한다.
  검증 성공 결과를 반환값으로 쓰지 않는다(게이트웨이는 dict를 반환하는 기존 계약 유지).
- 타입 힌트 완전성(mypy 통과 수준). 주석은 WHY가 명확하지 않을 때만 최소한으로.

## Test Requirements

신규 테스트 파일 `tests/test_llm_escalation.py`(기존 `tests/test_llm_*.py` 평면 구조를
따른다), 필요 시 `tests/test_llm_gateway.py`·`tests/test_llm_factory.py`·
`tests/test_config.py` 보강. fake/stub 주입 방식(기존 게이트웨이 테스트 패턴),
`AsyncMock` 금지(sync 코드베이스).

- `EscalationSignal`: frozen 불변성, 필드 기본값.
- `EscalationPolicy.should_escalate_before`: 5개 트리거 필드 개별 참 분기, 전부 거짓이면
  `False`, `resolved_provider=CLOUD`이면 항상 `False`, `risk_level=MEDIUM`은 미트리거.
- `EscalationPolicy.should_verify_after`: confidence 경계값(임계치 미만/이상),
  schema 통과/실패 분기, `first_provider=CLOUD`이면 항상 `False`,
  `confidence_threshold=None`이면 confidence 조건 비활성, confidence 키 부재 시
  confidence 조건 미트리거.
- 게이트웨이: pre-call override 발화 시 cloud client 호출·guard 통과·`escalated=True`,
  `escalation_signal=None`이면 override 없음, post-call 발화 시 cloud 재호출·결과 대체·
  `escalated=True`·budget 소비·캐시 미저장, 재호출 실패(검증 실패·예외) 시 원래 결과
  반환 + 경고 로그, 1차 CLOUD면 재호출 없음, policy 미부착 시 기존 동작 보존.
- 팩토리: `LLM_ESCALATION_ENABLED=True` + cloud일 때만 부착, 기본값이면 미부착.
- config: `LLM_ESCALATION_CONFIDENCE_THRESHOLD` `""` → `None` 파싱, 범위 검증.
- 기존 테스트 전부 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## Documentation Impact

`docs/decisions/ADR-010-llm-fallback-and-escalation-policy.md`(Accepted 확정),
`docs/backend-v0.2.md`, `.env.example`. 설계
`docs/designs/081-llm-risk-escalation-engine.md`는 이 브랜치에 동봉된다.

## ADR Need

신규 ADR 불필요 — ADR-010 확정 갱신이 본 작업의 일부다(설계 081 Decision QQQ).

## Failure Record Need

없음 — ADR-010 Follow-up으로 계획된 구현이며 결함 마감이 아니다.

## Risk Level

낮음. `LLMGateway` 생성자·`complete_json` 모두 optional 파라미터 추가 방식이라
escalation 미설정 시 기존 경로가 그대로 보존된다. 현재 전 task가 cloud 라우팅이므로
pre-call 경로는 골격이고, post-call 재호출도 1차 CLOUD 조건에서 건너뛴다.

## Expected Output

- 신규: `app/adapters/llm/escalation.py`, `tests/test_llm_escalation.py`.
- 수정: `app/adapters/llm/gateway.py`, `app/adapters/llm/__init__.py`,
  `app/core/config.py`, `app/adapters/factory.py`, `.env.example`,
  `docs/decisions/ADR-010-llm-fallback-and-escalation-policy.md`,
  `docs/backend-v0.2.md`, 필요 시 기존 테스트 보강.
- 검증 4종 통과.

## Decisions 요약 (설계 081 참조)

- MMM: `EscalationSignal`을 `complete_json` optional 인자로 전달. 신호 취합은 호출부,
  판정은 게이트웨이 내 policy. 기본 `None` 하위호환.
- NNN: pre-call은 LOCAL 라우팅일 때만 실질 동작 — 현재는 골격, 로컬 전환 시 자동 활성.
- OOO: post-call 트리거는 confidence 임계치 미만·schema 검증 실패 두 조건. 재호출은
  guard·budget 적용, 캐시 미적용. 재호출 실패 시 원래 결과 + 경고 로그.
- PPP: `LLMCompletionResult.escalated: bool = False` 관측 필드 추가.
- QQQ: ADR-010 Status Accepted 확정 갱신.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 브랜치(`experiment/139-escalation-opus`)를 유지한다. 커밋하지 않는다.
