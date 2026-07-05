# 081 — LLM Risk Escalation Engine (BE #139)

## Status

Draft

## 배경

이슈 #139는 위험도 에스컬레이션 엔진을 요구한다. ADR-010(Proposed — Deferred)은
"어떤 작업의 `future_primary`가 로컬로 전환되거나, 사용자 대면 브리핑 기능이 착수될 때"를
풀구현 트리거로 명시했으며, #139를 Follow-up으로 명시했다. PR #151에서 포트폴리오·
대시보드 브리핑이 구현됨으로써 트리거가 충족됐다. 이번 작업으로 ADR-010을 확정(Accepted)하고
에스컬레이션 엔진을 구현한다.

현재 `LLMGateway.complete_json`은 `LLMRouter.resolve`가 확정한 provider를 그대로 사용한다.
`LLM_TASK_ROUTES`의 모든 `launch`가 `"cloud"`이므로 pre-call 에스컬레이션은 실질적으로
동작할 대상이 없다(ADR-010의 "죽은 코드" 인식과 일관). 그럼에도 엔진 골격을 지금 도입하는
이유는 두 가지다. 첫째, `future_primary`가 `"local"`인 작업이 실제로 전환되는 시점에
게이트웨이 재설계 없이 pre-call 경로가 자동으로 활성화된다. 둘째, post-call cloud 검증
(confidence 낮음·schema validation 실패)은 현재 cloud 라우팅에서도 즉시 작동한다.

트리거를 두 부류로 나눈다. **Pre-call 트리거**(입력 신호 기반): 리스크 급등·손실률 급증·
뉴스 감성 급변·실적/공시 이벤트·매수매도 질문 — 호출 전에 알 수 있는 신호다. **Post-call
트리거**(출력 신호 기반): confidence 낮음·schema validation 실패 — 1차 호출 결과를 본 뒤에야
판단 가능한 신호다.

## 범위

- `app/adapters/llm/escalation.py` 신설 — `EscalationSignal`, `EscalationPolicy`
- `LLMGateway.complete_json` 수정 — `escalation_signal` optional 인자·pre/post 에스컬레이션 훅
- `app/adapters/factory.py` 수정 — `escalation_policy` opt-in 부착
- `app/core/config.py` 수정 — `LLM_ESCALATION_ENABLED`, `LLM_ESCALATION_CONFIDENCE_THRESHOLD`
- `docs/decisions/ADR-010-llm-fallback-and-escalation-policy.md` — Status Accepted 갱신
- 비포함: 기술적 폴백(타임아웃·rate limit 재시도), ADR-012 safe template 풀구현, 내용 수준
  검증, 메트릭 수집 인프라, 호출부(도메인 서비스) 변경

## 구성 요소

| 파일 | 변경 | 책임 |
| --- | --- | --- |
| `app/adapters/llm/escalation.py` | 신규 | 입력 신호 보유(`EscalationSignal`)·pre/post 판정(`EscalationPolicy`) |
| `app/adapters/llm/gateway.py` | 수정 | `complete_json` pre-call provider override·post-call cloud 재검증 훅 |
| `app/adapters/factory.py` | 수정 | cloud 모드이고 `LLM_ESCALATION_ENABLED`일 때만 `EscalationPolicy` 부착 |
| `app/core/config.py` | 수정 | `LLM_ESCALATION_ENABLED: bool = False`, `LLM_ESCALATION_CONFIDENCE_THRESHOLD: float \| None = None` |
| `docs/decisions/ADR-010-llm-fallback-and-escalation-policy.md` | 수정 | Accepted 확정 — protected file¹ |

¹ `docs/decisions/` 는 핸드오프 Protected Files 목록에 포함된다. ADR-010 수정은 구현 핸드오프에서
명시적으로 허용 항목으로 선언한다.

### EscalationSignal

`EscalationSignal`은 frozen dataclass다. `complete_json`에
`escalation_signal: EscalationSignal | None = None`(기본 `None` → 하위호환)으로 전달된다.

필드(모두 기본값을 가져 부분 지정이 가능하다):

- `risk_level: RiskLevel = RiskLevel.LOW` — 입력 컨텍스트의 위험 등급(`HIGH`이면 pre-call 트리거 후보)
- `loss_spike: bool = False` — 단기 손실률이 임계치를 초과했는가
- `news_sentiment_swing: bool = False` — 뉴스 감성 점수가 급변했는가
- `event_flag: bool = False` — 실적·공시 이벤트가 존재하는가
- `trade_question: bool = False` — 페이로드가 매수·매도 의사결정 질문을 포함하는가

### EscalationPolicy 시그니처

- `__init__(confidence_threshold: float | None)` — post-call 판정에 쓸 confidence 임계치 보유.
  `None`이면 confidence 기반 post-call 트리거 비활성.
- `should_escalate_before(signal: EscalationSignal, resolved_provider: str) -> bool` —
  pre-call 트리거 판정. `resolved_provider`가 `LOCAL`일 때만 의미 있으며, 신호 필드 중
  하나라도 에스컬레이션 조건을 충족하면 `True`를 반환한다. 반환값이 참이면 게이트웨이가
  provider를 `CLOUD`로 런타임 override한다.
- `should_verify_after(output: dict, schema: type[BaseModel], first_provider: str) -> bool` —
  post-call 트리거 판정. 1차 결과의 `"confidence"` 값이 임계치 미만이거나 `schema`
  검증이 실패이고, `first_provider`가 `CLOUD`가 아닌 경우 `True`를 반환한다. 반환값이
  참이면 게이트웨이가 cloud client로 검증 재호출(cloud verification)을 수행하고 결과를
  대체한다.

### 게이트웨이 확장 흐름

`complete_json(task_type, payload, schema, system_prompt, escalation_signal=None)`:

1. `router.resolve(task_type)` → `provider`
2. *(pre-call)* `escalation_signal`이 있고
   `escalation_policy.should_escalate_before(signal, provider)`이면 `provider = CLOUD`
3. `provider == CLOUD`이면 `privacy_gate.guard(payload)` — payload가 이미 `CloudSafePayload`이므로
   항상 통과 가능(ADR-009 경계 충족)
4. cache lookup → 히트이면 반환
5. `call_budget.consume` → `client.complete_json` → cache store
6. *(post-call)* `escalation_policy.should_verify_after(output, schema, first_provider)`이면
   cloud client로 재호출 → 결과 대체. 재호출도 실패이면 원래 결과 반환 + 경고 로그.
   재호출은 cloud 호출이므로 `privacy_gate.guard`와 `call_budget.consume`을 동일하게
   거친다. 캐시는 적용하지 않는다(검증 재호출 결과의 캐시 오염 방지·복잡도 억제)
7. `LLMCompletionResult(output, provider, model_name, cached, escalated)` 반환

`escalation_policy`가 `None`이면 2번·6번 분기가 없어 기존 경로와 동일하다.

## Decisions

### Decision MMM — EscalationSignal을 게이트웨이 선택적 인자로 전달

`complete_json`에 `escalation_signal: EscalationSignal | None = None`을 추가한다.
기본값 `None`이면 에스컬레이션 없이 기존 경로를 그대로 타므로 기존 호출부는 변경 없이
하위호환된다. 신호 취합은 호출부(서비스) 책임이고, 판정은 게이트웨이 내 `EscalationPolicy`
책임으로 분리된다. 에스컬레이션 정책이 서비스 레이어로 흩어지거나(ADR-010 기각 방향),
서비스가 provider를 직접 지정하는(ADR-007/008 단일 choke point 원칙 위반) 구조를 방지한다.

`escalation_signal`이 `None`이면 `EscalationPolicy`를 주입해도 pre-call 판정이 수행되지 않는다.
opt-in 신호 없이 policy만 있어도 기존 동작이 보존된다.

기각 대안: 호출부가 provider를 인자로 직접 전달(단일 choke point 위반·ADR-008 정적 라우팅 우회),
서비스 레이어에 에스컬레이션 분기 추가(정책 흩뜨리기·프라이버시 경계 우회 위험).

### Decision NNN — pre-call 에스컬레이션: LOCAL 라우팅 시에만 실질 동작·현재는 골격 보존

`should_escalate_before`는 `resolved_provider`가 이미 `CLOUD`이면 즉시 `False`를 반환하므로
override가 발생하지 않는다. 현재 `LLM_TASK_ROUTES`는 모든 `launch`가 `"cloud"`이므로
pre-call 에스컬레이션은 실질적으로 죽은 코드다. 그럼에도 골격을 지금 포함하는 근거:
`future_primary`가 `"local"`인 작업(`NEWS_SUMMARY`, `DASHBOARD_BRIEFING`, `WATCHLIST_NOTE`,
`TAG_SENTIMENT`)이 실제로 전환되는 시점에 게이트웨이 재설계 없이 자동으로 활성화된다.

ADR-010의 "기술적 폴백만 두고 escalation은 영구 보류" 대안을 여기서 명시적으로 기각한다.
로컬 전환 시점에 게이트웨이를 재설계하는 비용이 지금 골격을 추가하는 비용보다 크다.

기각 대안: 로컬 전환 전까지 pre-call 로직 전부 생략(전환 시점 후행 재작업 비용 증가),
feature flag로 pre-call만 별도 분기(코드 복잡도 증가, opt-in 기본값으로 충분히 대체 가능).

### Decision OOO — post-call cloud 검증: confidence 임계치·schema 검증 실패 두 조건

post-call 트리거를 두 가지로 정의한다.

1. **confidence 낮음**: `output` dict의 `"confidence"` 키 값이
   `LLM_ESCALATION_CONFIDENCE_THRESHOLD` 미만. 임계치가 `None`이면 이 조건은 비활성.
   `LLMAnalysisResult.confidence: float`(schema.py)가 이미 이 필드를 정의하고 있다.
2. **schema 검증 실패**: 주어진 `schema`로 `output`을 검증했을 때 `ValidationError`가
   발생하는 경우.

두 조건 모두 `first_provider`가 `CLOUD`가 아닌 경우에만 cloud 재호출을 발화한다.
1차가 이미 CLOUD이면 재호출이 무의미하므로 건너뛴다.

cloud 재호출은 게이트웨이의 다른 cloud 호출과 같은 규율을 따른다 — `privacy_gate.guard`
통과와 `call_budget.consume` 소비를 생략하지 않는다(ADR-009 경계·비용 상한의 일관 적용).
캐시 lookup/store는 적용하지 않는다. cloud 재호출 결과도 검증에 실패하거나 재호출 자체가
예외를 던지면 원래 결과를 반환하고 경고 로그를 남긴다. ADR-012 safe template 풀구현은
본 범위 외로 후속에 표시한다.

기각 대안: 모든 후처리를 호출부 책임으로 남기기(정책 흩뜨리기·단일 choke point 원칙 위반),
cloud 재호출 없이 즉시 safe template 대체(ADR-012 풀구현 선행 필요 — 범위 외).

### Decision PPP — LLMCompletionResult에 `escalated: bool` 필드 추가

에스컬레이션 발생 여부를 관측할 수 있도록 `LLMCompletionResult`에 `escalated: bool = False`
필드를 추가한다. `cached: bool`과 동일한 최소 관측 패턴이며, 호출부와 로깅 레이어에서
에스컬레이션 발생 여부를 식별할 수 있다. ADR-010의 "폴백 발생은 관측 가능해야 한다" 제약을
만족하는 초기 대응이다. 본격 메트릭 수집 인프라는 후속으로 남긴다.

기각 대안: 별도 로그 이벤트만으로 관측(결과 객체에서 에스컬레이션 여부를 분리할 수 없어
게이트웨이 단위 테스트 작성이 어렵다), `EscalationReason` enum 필드 추가(현재 필요 신호 없음,
후속).

### Decision QQQ — ADR-010을 Accepted로 확정

#139 구현 착수로 ADR-010의 풀구현 트리거 중 "브리핑 기능 설계가 착수"된 조건이 충족됐다
(PR #151). 080이 ADR-011을 확정한 선례와 같은 방식으로 ADR-010 Status를 `Accepted`로
올리고, Decision 절에 본 설계(MMM–PPP)의 확정 내용을 반영한다.

기술적 폴백(재시도·transport 폴백)은 본 범위 외로 남기고 ADR-010의 미결 질문에 표시한다.
ADR-012 safe template과의 정합은 ADR-012 확정 시점에 맞춘다.

## 테스트

- `EscalationSignal` frozen 불변성 및 필드 기본값 확인.
- `EscalationPolicy` 단위: `should_escalate_before` — 각 트리거 필드(`risk_level HIGH`,
  `loss_spike`, `news_sentiment_swing`, `event_flag`, `trade_question`) 개별 true 분기,
  모두 false 시 false, `resolved_provider=CLOUD` 입력 시 항상 false.
- `should_verify_after` — confidence 임계치 경계값(미만·이상), schema 통과/실패 분기,
  `first_provider=CLOUD` 입력 시 항상 false, `confidence_threshold=None` 시 confidence
  조건 비활성.
- 게이트웨이 통합: pre-call override 발화 시 cloud client 호출·`escalated=True`,
  `escalation_signal=None` 시 override 없음, post-call 트리거 발화 시 cloud 재호출·
  `escalated=True`, 재호출도 실패 시 원래 결과 반환 + 경고 로그 확인, 1차가 CLOUD이면
  post-call 재호출 없음.
- 팩토리: `LLM_ESCALATION_ENABLED=True` + cloud 모드일 때만 `EscalationPolicy` 부착.
- config: `LLM_ESCALATION_CONFIDENCE_THRESHOLD` float 파싱·`""` → `None` 처리.

## ADR 판단

신규 ADR 불필요 — ADR-010 확정 갱신으로 충분하다(본 설계 Decision QQQ).

## Failure Record 판단

불필요 — ADR-010 Follow-up으로 계획된 구현이며 결함 마감이 아니다.
