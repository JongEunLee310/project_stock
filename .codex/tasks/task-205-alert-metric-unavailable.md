# Codex Handoff Task

## Source Issue

이슈 #341 — 알림 엔진에서 지표 데이터 부재와 안정 상태를 구분해 `unavailable`로 표현한다.
`gh issue view 341`로 맥락을 읽는다. 문제의 상세는 `docs/reviews/pr-338.md`의 S2이고, 설계
정본은 `docs/designs/alert-rule-event-unified.md` §5다. 선행 PR #338(이슈 #336)은 `dev`에
머지 완료.

## Task Summary

파생 지표(`NEWS_RISK`·`THEME_HEAT`·`AI_JUDGMENT_CHANGED`)를 읽을 때, 시그널 스냅샷이 없어서
값을 알 수 없는 경우와 실제로 안정 상태인 경우를 구분한다. 전자는 기본값을 채우지 않고 값
미제공으로 처리해 evaluator의 `unavailable_metrics` 경로로 흘려보낸다.

## Goal

- 스냅샷이 하나도 없는 대상의 규칙 평가에서 해당 지표가 `unavailable_metrics`로 구분된다.
- 실제로 안정 상태인 대상은 기존과 동일하게 값이 채워진 채 미발동으로 남는다.
- 두 경우가 테스트에서 명시적으로 구분되어 단언된다.

## Background — 현재 코드

- `app/domains/alert_engine/snapshot_provider.py`
  - `_derive_signal_metrics(signal_type)`는 `signal_type`이 `None`일 때도
    `LOW`·`NEUTRAL`·`STABLE`을 돌려준다. 스냅샷이 없는 자산과 안정 상태인 자산이 여기서
    같아진다.
  - `_aggregate_derived_metric(metric, pairs)`는 `pairs`의 모든 자산을 집계에 넣는다.
    `latest`가 `None`인 자산도 기본값으로 참여한다.
  - `_derived_signal_metric`은 `_target_asset_ids`가 비면 `None`을 돌려준다.
- `MetricSnapshotProvider.get_snapshot`은 `_read_metric`이 `None`을 돌려주면 `continue`해서
  해당 지표를 `values`에 넣지 않는다.
- `app/domains/alert_engine/evaluator.py`의 `_evaluate_condition`은 `metric not in
  snapshot.values`인 경우를 `unavailable_metric`으로 분류한다(현재 파일 기준 117-124행).

즉 값 미제공을 표현하는 경로는 이미 있다. 이번 작업은 새 표현 수단을 만드는 것이 아니라,
파생 지표가 그 경로를 타도록 연결하는 것이다.

## Implementation Scope

`app/domains/alert_engine/snapshot_provider.py`만 고친다.

- `_aggregate_derived_metric`이 `latest`가 `None`인 자산을 집계 대상에서 제외한다. 스냅샷이
  없는 자산은 값을 모르는 것이지 안정 상태인 것이 아니므로 집계에 기여하지 않는다.
- 제외 후 남는 자산이 하나도 없으면 값 미제공으로 처리한다. `_aggregate_derived_metric`이
  `None`을 돌려줄 수 있게 반환 타입을 `_MetricReading | None`으로 바꾸고,
  `_derived_signal_metric`이 그대로 전달한다. `get_snapshot`의 기존 `continue` 분기가 나머지를
  처리하므로 호출부 로직은 바꾸지 않는다.
- `previous` 집계도 같은 기준을 따른다. 제외되지 않은 자산만으로 계산한다.

## Out of Scope

- 파생 매핑 표 자체의 변경. `_derive_signal_metrics`의 `signal_type` 대 값 대응은 #336에서
  확정됐으므로 건드리지 않는다.
- 알 수 없는 `signal_type`의 기본값 정책. 매핑 범위 밖의 값이지 데이터 부재가 아니므로
  현행 유지한다. `_derive_signal_metrics`가 `None`이 아닌 미지의 문자열을 받으면 지금처럼
  `LOW`·`NEUTRAL`·`STABLE`을 돌려준다.
- PR #338 리뷰 S1(다자산 집계의 current·previous 자산 불일치, 이슈 #340). 별도 이슈이며
  선행 결정이 필요하다. 이번 작업에서 함께 고치지 않는다.
- `evaluator.py` 변경. `unavailable_metric` 분류 로직은 그대로 쓴다.
- 운영자용 진단 화면이나 알림 미발동 리포트 신설.
- `AlertMetric.SIGNAL_CHANGED` 경로(`_signal_change`). 이미 `latest is None`이면 `None`을
  돌려주므로 변경 불필요하다.

## Protected Files

없음. 다만 `evaluator.py`·`types.py`의 기존 계약과 `MetricSnapshot` 구조는 바꾸지 않는다.

## Requirements

1. 대상 자산 전체에 시그널 스냅샷이 없으면 파생 지표가 `MetricSnapshot.values`에 담기지
   않는다.
2. 그 결과 evaluator가 해당 조건을 `unavailable_metric`으로 분류하고 규칙은 발동하지 않는다.
3. 일부 자산에만 스냅샷이 있으면 스냅샷이 있는 자산만으로 집계한다. 스냅샷이 없는 자산이
   기본값으로 집계를 끌어내리지 않는다.
4. 모든 대상에 스냅샷이 있고 값이 안정 상태이면 기존과 동일하게 값이 채워지고 미발동으로
   남는다.
5. `AI_JUDGMENT_CHANGED`의 전이 선택과 tie-break, `NEWS_RISK`·`THEME_HEAT`의 최고 심각도
   선택 규칙은 제외 후 남은 자산 집합 안에서 기존과 동일하게 동작한다.

## Test Requirements

- 대상 전원 스냅샷 없음 — 지표가 `values`에 없고 evaluator 결과가 `unavailable`로 분류되는지.
- 대상 전원 스냅샷 있음, 안정 상태 — 값이 채워지고 미발동인지. 위 경우와 결과가 구분되는지.
- 일부만 스냅샷 있음 — 스냅샷 있는 자산의 값으로 집계되는지, 없는 자산이 기본값으로
  참여하지 않는지.
- 기존 파생 지표 테스트 회귀 없음.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

없음. 계약 변경이 아니라 값 미제공 판정 기준을 바로잡는 작업이다. 구현 중 계약과 어긋나는
지점을 발견하면 멈추고 가정을 보고한다.

## Risk Level

Low — 단일 파일의 집계 필터와 반환 타입 변경이다. 주의할 점은 반환 타입을 Optional로 바꾸며
mypy가 요구하는 호출부 정리와, 제외 후 빈 집합에서 `max()`가 호출되지 않도록 순서를 잡는
것이다.

## Expected Output

- `snapshot_provider.py` 수정과 테스트 추가.
- 지정된 현재 브랜치에 커밋. 자체 브랜치 생성 금지.
- 검증 3종 통과 보고.

## Rules

- Stay within scope. 매핑 표와 #340 범위는 건드리지 않는다.
- Do not weaken verification.
- 지정된 현재 브랜치를 유지한다. 새 브랜치 금지.
- Report assumptions and verification results.
