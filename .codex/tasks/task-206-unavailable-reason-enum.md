# Codex Handoff Task

## Source Issue

PR #343(이슈 #341) 로컬 리뷰의 Q1 후속입니다. 리뷰 코멘트에서 개발자가 "값 미제공과 부재를
처음부터 구분하지 않은 잘못이며, 사용자나 LLM이 둘의 차이를 파악하지 못하는 문제가 있으므로
enum으로 구분하겠다"고 결정했습니다. `gh pr view 343 --comments`로 원문을 읽는다.

리뷰 피드백은 같은 브랜치에 이어 붙인다(`docs/harness/local-review-policy.md`의 Handling
Review Feedback). 새 PR을 만들지 않는다.

## Task Summary

지표가 `MetricSnapshot.values`에 담기지 않는 사유를 enum으로 구분해 스냅샷과 평가 결과에
싣는다. 지금은 사유를 잃어버려 "대상을 찾지 못함"과 "대상은 있으나 데이터가 없음"이 모두
`unavailable_metric` 하나로 뭉개진다.

## Goal

- 규칙이 발동하지 않은 이유를 사유 단위로 구분해 읽을 수 있다.
- 기존 `unavailable_metrics` 소비처가 깨지지 않는다.

## Background — 현재 코드

- `app/domains/alert_engine/types.py`
  - `MetricSnapshot`은 `values`·`previous_values`·`evidence`·`unsupported_metrics`·`asset_id`를
    가진다. 사유를 담을 자리가 없다.
  - `AlertEvaluationResult`는 `unsupported_metrics`·`unavailable_metrics`를 정렬된
    `tuple[str, ...]`로 노출한다.
- `app/domains/alert_engine/snapshot_provider.py`
  - `_read_metric`과 각 리더(`_derived_signal_metric`·`_price_change`·`_signal_change`·
    `_position_weight`·`_earnings_date`)는 실패를 전부 `None`으로만 알린다.
  - `get_snapshot`은 `None`이면 `continue`해서 해당 지표를 `values`에 넣지 않는다.
- `app/domains/alert_engine/evaluator.py`
  - `_evaluate_condition`이 `metric not in snapshot.values`를 `unavailable_metric`으로
    분류하고, `evaluate_rule`이 이를 정렬해 `unavailable_metrics`로 모은다.

## Implementation Scope

### 1. enum 신설

`app/domains/alert_engine/types.py`에 `MetricUnavailableReason`(`str`, `Enum`)을 추가한다.
멤버는 두 개다.

- `NO_TARGET` — 규칙의 대상을 확정하지 못했다. 대상 유형이 지표와 맞지 않거나, `target_id`가
  없거나 정수로 파싱되지 않거나, 대상 레코드가 없거나 소유자가 다르거나, 대상 목록이 비었다.
- `NO_DATA` — 대상은 확정했으나 지표를 계산할 데이터가 없다.

### 2. 스냅샷에 사유 싣기

`MetricSnapshot`에 `unavailable_reasons: dict[AlertMetric, MetricUnavailableReason]`을
기본값 빈 dict로 추가한다. 기존 필드는 그대로 둔다.

각 리더의 반환 타입을 `_MetricReading | MetricUnavailableReason`으로 바꾼다. 지금 `None`을
돌려주는 지점마다 아래 기준으로 사유를 돌려준다.

- `_derived_signal_metric` — `_target_asset_ids`가 `None`이면 `NO_TARGET`,
  `_aggregate_derived_metric`이 `None`이면 `NO_DATA`.
- `_price_change` — `_symbol_asset`이 `None`이면 `NO_TARGET`, 봉 수 부족이나 직전 종가 0이면
  `NO_DATA`.
- `_signal_change` — `_symbol_asset`이 `None`이면 `NO_TARGET`, `latest`가 `None`이면 `NO_DATA`.
- `_position_weight` — 대상 유형 불일치·`target_id` 없음·파싱 실패·포트폴리오 없음·소유자
  불일치는 `NO_TARGET`, 포지션이 비면 `NO_DATA`.
- `_earnings_date` — 위와 같은 대상 확정 실패는 `NO_TARGET`, 다가오는 이벤트가 없으면
  `NO_DATA`.
- `_read_metric`의 마지막 fallthrough(리더가 없는 지표) — `NO_DATA`.

`get_snapshot`은 리더가 사유를 돌려주면 `unavailable_reasons[metric]`에 담고 `values`에는
넣지 않는다. `_aggregate_derived_metric`의 반환 타입은 `_MetricReading | None`으로 유지하고,
사유 판정은 호출부인 `_derived_signal_metric`에서 한다.

### 3. 평가 결과에 사유 노출

`_ConditionEvaluation`에 `unavailable_reason: str | None`을 추가하고,
`_evaluate_condition`이 `metric not in snapshot.values`인 경우
`snapshot.unavailable_reasons`에서 사유를 읽어 채운다. 사유가 없으면 `NO_DATA`를 기본값으로
쓴다.

`AlertEvaluationResult`에 `unavailable_reasons: tuple[tuple[str, str], ...]`을 추가한다.
`(metric, reason)` 쌍을 metric 기준으로 정렬해 담는다. 기존 `unavailable_metrics`는 그대로
유지한다.

## Out of Scope

- `unavailable_metrics` 제거나 형태 변경. 기존 소비처와 테스트를 깨지 않는다.
- `AlertCycleSummary`에 사유별 카운트 추가.
- `unsupported_metrics` 관련 로직.
- 리뷰 S1(다자산 집계의 current·previous 자산 불일치, 이슈 #340). 별도 이슈이며 선행 결정이
  필요하다.
- API 응답 스키마·엔드포인트 변경. 이번 변경은 엔진 내부 표현까지다.
- 마이그레이션. 스키마를 건드리지 않는다.

## Protected Files

없음. 다만 `AlertEvaluationResult`의 기존 필드와 `MetricSnapshot`의 기존 필드는 이름·타입·
기본값을 바꾸지 않는다. 추가만 한다.

## Requirements

1. 대상을 확정하지 못한 경우와 대상은 있으나 데이터가 없는 경우가 서로 다른 enum 값으로
   구분된다.
2. `AlertEvaluationResult.unavailable_metrics`의 기존 동작과 값이 변하지 않는다.
3. 새 필드는 기본값을 가져 기존 생성부가 인자 없이도 동작한다.
4. 조건이 `all` 복합인 경우 각 지표의 사유가 개별로 수집된다.
5. mypy가 통과하도록 리더 반환 타입 변경에 따른 호출부 분기를 정리한다.

## Test Requirements

- 대상 확정 실패(존재하지 않는 워치리스트, 소유자 불일치, 잘못된 `target_id`) — `NO_TARGET`.
- 대상은 있으나 스냅샷 전무 — `NO_DATA`.
- 가격 지표에서 봉 수 부족 — `NO_DATA`.
- 복합 조건에서 두 지표가 서로 다른 사유로 미제공인 경우 둘 다 수집되는지.
- 기존 `unavailable_metrics` 단언이 그대로 통과하는지(회귀 없음).

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

`docs/designs/alert-rule-event-unified.md` §5에 사유 구분을 한 줄 추가한다. 리뷰 S1에서
제안한 "일부 자산만 스냅샷이 없을 때 집계 대상에서 제외된다"는 내용도 같은 자리에 함께
적는다. 설계 문서에는 구현 코드를 넣지 않고 동작 기준만 서술한다.

## Risk Level

Medium — 엔진 내부 계약(`MetricSnapshot`·`AlertEvaluationResult`)에 필드를 더하고 리더 5종의
반환 타입을 바꾼다. 기존 필드를 건드리지 않으므로 호환은 유지되지만, 리더마다 실패 지점이
여러 개라 사유 배정을 빠뜨리기 쉽다. 각 `return` 지점을 하나씩 확인한다.

## Expected Output

- `types.py`·`snapshot_provider.py`·`evaluator.py` 수정, 설계 문서 한 줄 보완, 테스트 추가.
- 현재 브랜치 `feat/341-alert-metric-unavailable`에 이어서 커밋. 새 브랜치 금지.
- 검증 3종 통과 보고.

## Rules

- Stay within scope. 기존 필드 변경과 #340 범위는 건드리지 않는다.
- Do not weaken verification.
- 지정된 현재 브랜치를 유지한다. 새 브랜치 금지.
- Report assumptions and verification results.
