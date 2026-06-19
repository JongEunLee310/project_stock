# 020: 기본 Rule Engine

## 목적

AI 판단만으로 Signal/Alert를 생성하지 않도록, AI 분석 결과를 규칙 기반 검증 계층에 통과시켜 Signal로 변환한다.
1차 MVP는 투자 가설 충돌 여부와 뉴스 중요도를 중심으로 한다.

## 위치

`app/domains/signals/rules/`

- `base.py` — `Rule` 인터페이스, `RuleContext`
- `thesis_conflict_rule.py` — 가설 충돌 규칙
- `high_impact_rule.py` — 고중요도 뉴스 규칙
- `engine.py` — `RuleEngine`

Signal을 산출하므로 Signal 도메인(#17)에 의존한다.

## RuleContext

규칙 평가에 필요한 입력 묶음(dataclass).

| 필드 | 타입 | 설명 |
|---|---|---|
| asset_id | int | |
| news_item | NewsItem | 요약·sentiment·impact_level 포함 |
| thesis | InvestmentThesis \| None | |
| conflict_result | ThesisConflictResult \| None | #15 산출물 |

## Rule 인터페이스

```
class Rule(ABC):
    def evaluate(self, context: RuleContext) -> SignalCreate | None
```

- 규칙은 조건 충족 시 `SignalCreate`를 반환하고, 아니면 `None`을 반환한다.
- 규칙은 DB에 직접 쓰지 않는다(생성·중복 판단은 Engine 책임).

## 규칙

### ThesisConflictRule

- `conflict_result.status == "CONFLICTS"` 또는 `invalidation_triggered`가 참이면
  `THESIS_BROKEN`(invalidation 시) 또는 `RISK_ALERT`(충돌) Signal 생성.
- `reason`에 충돌 근거, `evidence`에 `conflict_result` 요약 저장.

### HighImpactNewsRule

- `news_item.impact_level`이 `HIGH` 또는 `CRITICAL`이면 `RISK_ALERT` Signal 생성.
- `evidence`에 `news_item_id`, `impact_level`, `sentiment` 저장.

## RuleEngine

```
class RuleEngine:
    def __init__(self, rules: list[Rule], signal_repo: SignalRepository)
    def run(self, context: RuleContext) -> list[Signal]
```

`run` 책임:

1. 각 Rule을 평가해 후보 `SignalCreate` 수집.
2. **중복 생성 방지:** `signal_repo.exists_active(asset_id, signal_type, news_item_id)`가 참이면 건너뛴다.
3. **만료 제외:** 중복 판단은 미만료 Signal만 대상으로 한다(`exists_active` 내부 처리, #17).
4. 통과한 후보를 `signal_repo.create`로 저장하고 생성된 Signal 목록 반환.

기본 규칙 구성(`default_rules()`)으로 `ThesisConflictRule`, `HighImpactNewsRule`을 제공한다.

## 완료 조건 매핑

- AI 결과가 Rule Engine을 거쳐 Signal로 변환 → `RuleEngine.run`
- 충돌 가능성 낮은 뉴스는 불필요한 알림 미생성 → 규칙 미충족 시 `None`
- 동일 원인 중복 Signal 미생성 → `exists_active` 기반 dedup + 만료 제외

## 의존성

Issue #17(Signal 도메인) 완료 후 진행.
