# Codex Handoff Task

## Source Issue

이슈 #340 — 다자산 대상 지표 집계의 current·previous 자산 불일치. `gh issue view 340`으로
맥락을 읽는다. 문제의 출처는 PR #338 로컬 리뷰(`docs/reviews/pr-338.md`)의 S1이다.

선행 결정은 ADR-015(`docs/decisions/ADR-015-asset-level-alert-evaluation.md`, PR #344로 `dev`에
머지 완료)다. 설계 정본 `docs/designs/alert-rule-event-unified.md` §5·§6도 함께 갱신됐다.
두 문서를 먼저 읽는다.

## Task Summary

다자산 대상(`WATCHLIST`·`PORTFOLIO`) 규칙의 평가 단위를 규칙 단위에서 자산 단위로 바꾼다.
자산마다 독립적으로 평가하고, 조건을 충족한 자산마다 별도 `AlertEvent`를 만든다. 중복 방지
세 장치도 모두 자산 단위로 내린다.

## Goal

- 한 규칙이 대상 자산 각각에 대해 평가되고, 충족한 자산마다 이벤트가 생성된다.
- 한 종목의 상태가 다른 종목의 변화를 가리지 않는다.
- 이벤트의 `current`와 `previous`가 같은 자산에서 나온다.

## Background — 현재 코드

- `app/domains/alert_engine/snapshot_provider.py`
  - `get_snapshot(rule, as_of) -> MetricSnapshot` — 규칙당 스냅샷 하나를 만든다.
  - `_aggregate_derived_metric(metric, pairs)` — 여러 자산의 파생 지표를 하나로 합친다.
    `NEWS_RISK`·`THEME_HEAT`은 최고 심각도 자산을 `current`로 쓰고 `previous`는 전체 이전
    값의 최댓값을 따로 구한다. 이 불일치가 이번 이슈의 출처다.
  - `_target_asset_ids(rule)` — 대상 자산 목록. 그대로 재사용한다.
  - `_position_weight(rule)` — 포트폴리오에서 비중 최대 종목 하나만 본다.
  - `_earnings_date(rule, today)` — 워치리스트에서 가장 가까운 실적 하나만 본다.
  - `_price_change`·`_signal_change` — `_symbol_asset`을 쓰므로 `SYMBOL` 대상 전용이고 자산이
    하나다.
- `app/domains/alert_engine/service.py`
  - `run_cycle()` — 활성 규칙을 순회하며 규칙당 스냅샷 1개·평가 1회·이벤트 최대 1개.
  - `_create_event(rule, asset_id, result, dedup_key, triggered_at)` — `AlertEvent` 생성.
    `asset_id` 인자를 이미 받는다.
  - 카운터 6종(`evaluated_count`·`matched_count`·`emitted_count`·`deduplicated_count`·
    `unsupported_count`·`unavailable_count`).
- `app/domains/alert_engine/dedup.py`
  - `should_emit(rule, result, *, now)` / `build_dedup_key(rule, result, *, now)` —
    dedup_key는 `rule_id:target_id:sha256(fingerprint)`.
  - `_in_cooldown(rule, now)` — `rule.last_triggered_at` 한 칸으로 판정한다. 규칙당 하나뿐이라
    자산 단위로 쓸 수 없다.
  - `_emitted_today(rule, now)` — `rule_id` + `target_id`로 조회한다.
- `app/domains/alert_events/model.py`
  - `AlertEvent`에 `asset_id`(nullable, index)가 이미 있다. **마이그레이션은 필요 없다.**
  - `rule_id`·`asset_id`·`triggered_at`에 각각 단일 인덱스가 있다.

## Implementation Scope

### 1. 스냅샷 제공자 — 자산별 반환

`MetricSnapshotProvider`에 `get_snapshots(rule, *, as_of) -> list[MetricSnapshot]`을 둔다.

- `_target_asset_ids(rule)`로 대상 자산을 확정한다. 대상을 확정하지 못하면 모든 지표가
  `NO_TARGET`으로 미제공인 스냅샷 하나만 담은 리스트를 돌려준다. 엔진의 `unavailable` 집계가
  지금처럼 동작해야 한다.
- 자산마다 스냅샷을 하나씩 만든다. 각 스냅샷의 `asset_id`는 해당 자산이다.
- 자산별 조회를 자산 수만큼 반복하지 않는다. `latest_pair_by_asset(asset_ids)`처럼 한 번에
  읽어오는 기존 경로를 유지하고, 그 결과를 자산별로 나눠 담는다.

`get_snapshot`(단수)은 제거한다. 호출부는 엔진과 테스트뿐이다.

### 2. 지표별 자산 단위 처리

- **파생 지표 3종** — `_aggregate_derived_metric`을 제거하고 자산 하나의 `latest`·`previous`
  스냅샷에서 직접 값을 만든다. `previous`는 같은 자산의 이전 스냅샷이다. evidence도 그 자산의
  것만 담는다.
- **`PRICE_CHANGE_1D`·`SIGNAL_CHANGED`** — `SYMBOL` 대상 전용이므로 자산이 하나다. 동작은
  같지만 새 구조에 맞춰 자산별 경로로 정리한다.
- **`POSITION_WEIGHT`** — 지금은 비중 최대 종목 하나만 본다. 자산별로 각 포지션의 비중을
  평가하도록 바꾼다. 두 번째로 비중이 큰 종목이 임계를 넘어도 보이지 않던 문제가 파생 지표의
  마스킹과 같은 성격이므로 ADR-015 §1을 동일하게 적용한다.
- **`EARNINGS_DATE`** — 지금은 가장 가까운 실적 하나만 본다. 자산별로 각 종목의 다가오는
  실적까지 남은 일수를 평가하도록 바꾼다.

지표가 지원하는 대상 유형(matrix)은 바꾸지 않는다. 지금 `SYMBOL`만 지원하던 지표를 다자산
대상에서 새로 동작하게 만들지 않는다.

### 3. 엔진 — 자산 단위 순회

`AlertEngineService.run_cycle()`이 규칙마다 `get_snapshots`를 호출하고 스냅샷마다 평가한다.

- 카운터 의미를 다음과 같이 정한다. `evaluated_count`는 (규칙 × 자산) 평가 횟수를 센다.
  나머지 카운터도 같은 단위로 센다.
- `unsupported_metrics`가 있으면 그 규칙은 자산 순회 없이 한 번만 세고 넘어간다. 지원하지
  않는 지표는 자산과 무관하기 때문이다.
- 한 규칙에서 여러 자산이 조건을 충족하면 각각 이벤트를 만든다.
- `rule.last_triggered_at`은 그 규칙에서 이벤트가 하나라도 생성되면 갱신한다. 표시용이다.

### 4. 중복 방지 — 자산 단위

`AlertDedupService`의 시그니처에 `asset_id`를 더한다.

- `build_dedup_key(rule, result, *, asset_id, now)` — 키 구성을
  `rule_id:target_id:asset_id:digest`로 바꾼다. `asset_id`가 `None`이면 `-`처럼 기존
  `target_id` 처리와 같은 방식으로 채운다.
- `should_emit(rule, result, *, asset_id, now)` — 아래 세 판정을 자산 단위로 한다.
- `_in_cooldown` — `rule.last_triggered_at` 대신 `alert_events`에서 (`rule_id`, `asset_id`)의
  최근 `triggered_at`을 조회해 판정한다. ADR-015 §4가 정한 방식이며 새 테이블을 만들지
  않는다.
- `_emitted_today` — 조회 조건에 `asset_id`를 더한다.
- state-transition은 evaluator가 자산별 스냅샷으로 이미 판정하므로 별도 변경이 없다. 자산별
  `previous`가 들어오는지만 확인한다.

### 5. 인덱스 확인

cooldown 판정이 `alert_events`의 (`rule_id`, `asset_id`, `triggered_at`) 조회에 의존하게 된다.
현재 세 컬럼에 각각 단일 인덱스가 있다. 복합 인덱스가 필요한지 판단하고, **필요하다고
판단되면 추가하지 말고 멈춰서 보고한다.** 인덱스 추가는 마이그레이션을 동반하므로 이번
범위 밖이다.

## Out of Scope

- 마이그레이션 추가. `asset_id`가 이미 있으므로 스키마 변경 없이 구현한다.
- 알림량 상한·묶음 알림·요약 digest. ADR-015 §5가 관측 후 대응으로 미뤘다.
- 지표별 지원 대상 유형(matrix) 변경.
- `AlertEvent`의 `title`·`message` 문안 개선. 자산 단위가 되면 문구를 다듬을 여지가 있지만
  이번 범위 밖이다. 기존 형식을 유지한다.
- API 응답 스키마·엔드포인트 변경.
- FE 변경.

## Protected Files

- `alembic/` 아래 전부.
- `app/domains/alert_events/model.py` — 스키마 무변경.
- `MetricSnapshot`·`AlertEvaluationResult`의 기존 필드. 필요하면 추가만 한다.

## Requirements

1. `WATCHLIST`·`PORTFOLIO` 대상 규칙이 자산마다 평가되고, 충족한 자산마다 `AlertEvent`가
   생성된다. 이벤트의 `asset_id`가 해당 자산을 가리킨다.
2. 이벤트의 `triggered_value`에 담기는 `current`와 `previous`가 같은 자산에서 나온다.
3. 만성적으로 위험한 종목이 있어도 다른 종목의 새로운 전이가 `ONCE_PER_TRANSITION` 규칙에서
   발동한다. 이슈 #340이 지목한 마스킹이 해소된다.
4. cooldown이 (규칙 × 자산) 단위로 걸린다. 한 종목의 발생이 같은 대상의 다른 종목을 억제하지
   않는다.
5. `ONCE_PER_DAY`가 자산·규칙당 하루 1회로 동작한다.
6. `SYMBOL` 대상 규칙의 동작이 기존과 같다.
7. `_aggregate_derived_metric`이 제거된다.

## Test Requirements

- 다자산 대상에서 두 자산이 동시에 조건을 충족하면 이벤트가 두 건 생성되는지.
- 만성 위험 종목이 있는 포트폴리오에서 다른 종목이 새로 전이될 때 발동하는지(#340의 시나리오를
  그대로 테스트로 옮긴다).
- `current`·`previous`가 같은 자산에서 나오는지. evidence의 `asset_id`가 일치하는지.
- cooldown이 자산별로 독립인지. 한 자산이 cooldown 중이어도 다른 자산은 발동하는지.
- `ONCE_PER_DAY`가 자산별로 하루 1회인지.
- 대상 확정 실패 시 `unavailable`(`NO_TARGET`) 처리가 기존과 같은지.
- `SYMBOL` 대상 규칙의 기존 테스트가 회귀하지 않는지.
- `POSITION_WEIGHT`·`EARNINGS_DATE`가 자산별로 평가되는지.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`
- `uv run alembic heads` — 마이그레이션을 추가하지 않았으므로 head가 하나인지 확인한다.

## Documentation Impact

설계 문서는 ADR-015와 함께 이미 갱신됐다. 구현이 문서와 어긋나면 코드를 문서에 맞추고, 문서가
틀렸다고 판단되면 멈추고 보고한다.

## Risk Level

Medium-High — 엔진의 순회 단위와 중복 방지의 판정 단위가 함께 바뀐다. cooldown 판정 근거가
`rule.last_triggered_at`에서 `alert_events` 조회로 옮겨가므로 기존 테스트가 여럿 영향을 받는다.
dedup_key 구성이 바뀌어 전환 직후 한 주기는 기존 키와 겹치지 않고, 이미 발생한 알림이 한 번
더 나올 수 있다. 이는 ADR-015 Follow-up이 예고한 사항이며 데이터 정리는 하지 않는다. 관련
사실을 보고에 적는다.

## Expected Output

- `snapshot_provider.py`·`service.py`·`dedup.py` 수정과 테스트 추가·갱신.
- 지정된 현재 브랜치에 커밋. 자체 브랜치 생성 금지.
- 검증 4종 통과 보고. 인덱스 필요 여부 판단과 근거, dedup_key 전환 영향에 대한 확인 결과를
  함께 보고한다.

## Rules

- Stay within scope. 마이그레이션과 알림량 제어는 건드리지 않는다.
- Do not weaken verification. 테스트를 지워서 통과시키지 않는다.
- 지정된 현재 브랜치를 유지한다. 새 브랜치 금지.
- Report assumptions and verification results.
