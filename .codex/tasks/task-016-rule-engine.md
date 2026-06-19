# Codex Handoff Task

## Source Issue

Issue #20: 기본 Rule Engine 구현

## Task Summary

AI 분석 결과(가설 충돌, 뉴스 중요도)를 규칙 기반 검증 계층에 통과시켜 Signal로 변환하는 Rule Engine을 구현한다.

## Goal

- AI 결과가 Rule Engine을 거쳐 Signal로 변환된다.
- 충돌 가능성이 낮은 뉴스는 Signal을 만들지 않는다.
- 동일 원인(asset·type·news)으로 중복 Signal이 생성되지 않으며, 만료된 Signal은 중복 판단에서 제외된다.

## Background

- **구현 전 `docs/designs/020-rule-engine.md`와 `docs/designs/017-signal-domain.md`를 읽는다.**
- Signal 도메인(Issue #17, task-015)이 먼저 머지되어 있어야 한다. `SignalRepository.exists_active`, `SignalCreate`, `SignalType`을 사용한다.
- 규칙은 DB에 직접 쓰지 않는다. 생성과 중복 판단은 `RuleEngine`이 담당한다.
- 외부 호출 없음(순수 로직). 테스트는 in-memory SQLite + 직접 구성한 `RuleContext`로 수행.
- 시작 전 최신 main에서 feature 브랜치를 생성한다.

## Implementation Scope

- `app/domains/signals/rules/__init__.py`
- `app/domains/signals/rules/base.py` — `Rule` ABC, `RuleContext`
- `app/domains/signals/rules/thesis_conflict_rule.py` — `ThesisConflictRule`
- `app/domains/signals/rules/high_impact_rule.py` — `HighImpactNewsRule`
- `app/domains/signals/rules/engine.py` — `RuleEngine`, `default_rules()`
- `tests/test_rule_engine.py`

## Out of Scope

- Signal 도메인(테이블/API) — Issue #17에서 완료
- Alert 생성 — Issue #18
- Worker job 통합 — Issue #19
- 신규 마이그레이션 (신규 테이블 없음)
- LLM/외부 어댑터 신규 추가

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

### RuleContext, Rule (base.py)

```python
@dataclass
class RuleContext:
    asset_id: int
    news_item: NewsItem
    thesis: InvestmentThesis | None = None
    conflict_result: ThesisConflictResult | None = None

class Rule(ABC):
    @abstractmethod
    def evaluate(self, context: RuleContext) -> SignalCreate | None: ...
```

### ThesisConflictRule

- `context.conflict_result`가 `None`이면 `None` 반환.
- `conflict_result.invalidation_triggered`가 `True`이면 `SignalType.THESIS_BROKEN`, `risk_level="CRITICAL"`.
- 아니고 `conflict_result.status == "CONFLICTS"`이면 `SignalType.RISK_ALERT`, `risk_level="HIGH"`.
- 그 외(SUPPORTS/NEUTRAL)는 `None`.
- 생성 시 `reason`=`conflict_result.reason`, `evidence`에 `status`, `invalidation_triggered`, `news_item_id` 포함, `thesis_id`/`news_item_id` 채움, `score`는 규칙별 고정값(예: THESIS_BROKEN=90, RISK_ALERT=70).

### HighImpactNewsRule

- `context.news_item.impact_level`이 `HIGH` 또는 `CRITICAL`이면 `SignalType.RISK_ALERT` 생성, 아니면 `None`.
- `reason`에 뉴스 요약 기반 문장, `evidence`에 `news_item_id`, `impact_level`, `sentiment` 포함.
- `score`는 impact_level에 따라(CRITICAL=80, HIGH=60).

### RuleEngine

```python
class RuleEngine:
    def __init__(self, rules: list[Rule], signal_repo: SignalRepository)
    def run(self, context: RuleContext) -> list[Signal]

def default_rules() -> list[Rule]:
    return [ThesisConflictRule(), HighImpactNewsRule()]
```

`run` 동작:

1. 각 rule의 `evaluate(context)`로 `SignalCreate` 후보 수집(`None` 제외).
2. 각 후보에 대해 `signal_repo.exists_active(asset_id, signal_type, news_item_id)`가 `True`면 건너뛴다.
3. 통과 후보를 `signal_repo.create`로 저장하고 생성된 `Signal` 리스트 반환.

## Test Requirements

`tests/test_rule_engine.py`:

- `ThesisConflictRule` — invalidation_triggered → THESIS_BROKEN, CONFLICTS → RISK_ALERT, SUPPORTS/NEUTRAL → None, conflict_result None → None
- `HighImpactNewsRule` — HIGH/CRITICAL → RISK_ALERT, LOW/None → None
- `RuleEngine.run` — 후보 Signal이 DB에 저장되고 반환됨
- `RuleEngine.run` 중복 방지 — 동일 조건 재실행 시 미만료 기존 Signal이 있으면 새로 생성하지 않음
- `RuleEngine.run` 만료 제외 — 기존 Signal이 만료된 경우 신규 Signal 생성됨

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_rule_engine.py -v
```

## Documentation Impact

`docs/designs/020-rule-engine.md` 외 없음.

## ADR Need

없음. 단순 규칙 계층이며 인터페이스는 확장 가능하게 설계됨.

## Failure Record Need

없음.

## Risk Level

Low — 신규 테이블/마이그레이션 없음, 순수 로직 계층. Signal 도메인(#17) 선행 필요.

## Expected Output

- `app/domains/signals/rules/` 신규 파일
- `tests/test_rule_engine.py` 통과
- lint/typecheck 통과

## Rules

- 구현 전 `docs/designs/020-rule-engine.md`, `017-signal-domain.md`를 읽는다.
- Issue #17(task-015) 머지 후 최신 main에서 시작한다.
- 규칙은 DB에 직접 쓰지 않는다(생성·중복 판단은 Engine).
- 스코프 외 파일 변경 금지. 테스트 약화 금지. 보호 파일 변경 금지.
