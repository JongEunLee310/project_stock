# Codex Handoff Task

## Source Issue

이슈 #336 — B5(#331) 후속. 알림 엔진의 `MetricSnapshotProvider`가 `NEWS_RISK`·`THEME_HEAT`·
`AI_JUDGMENT_CHANGED` 3종 지표를 소싱하지 못해 `UNSUPPORTED_METRICS`로 남겨 두었고, 이
지표를 쓰는 활성 템플릿(HOLDING_NEWS_RISK·WATCHLIST_AI_JUDGMENT·NEWS_RISK_HIGH) 규칙이
발동하지 않는다. `gh issue view 336`으로 맥락을 읽는다. 설계 정본은
`docs/designs/alert-rule-event-unified.md` §5(기존 인프라 재사용, 신규 수집 파이프라인 금지,
엔진은 시그널을 생성하지 않음).

## Task Summary

`app/domains/alert_engine/snapshot_provider.py`의 `MetricSnapshotProvider`에 3종 지표 읽기를
추가하고 `UNSUPPORTED_METRICS`에서 제거한다(`TOPIC_IMPACT_SCORE`만 남긴다). evaluator·dedup은
무변경.

## Sourcing 결정 (중요 — 이 방향을 따른다)

이슈 본문은 "watchlists(trend/analysis) 최신 스냅샷"을 언급하지만, 조사 결과
`NewsRisk`·`ThemeHeat`·`AiJudgment` 값은 `WatchlistEvaluationsService`의 **LLM on-demand
응답으로만 존재하고 어디에도 영속되지 않는다**. 엔진(스케줄러)에서 LLM을 호출하는 것은
비용·비결정성 때문에 금지다(설계 §5).

따라서 3종 지표는 기존에 영속되는 **일별 시그널 스냅샷**(`AssetSignalSnapshot`,
`SignalSnapshotRepository.latest_pair_by_asset` — B5의 `_signal_change`가 이미 사용)에서
`signal_type`을 결정론적으로 매핑해 파생한다. LLM 평가 값 영속·연동은 범위 밖(후속).

### 매핑 (signal_type → 지표 값, 출처: `app/domains/signals/types.py`의 `SignalType`, `app/domains/watchlists/types.py`의 enum)

| snapshot signal_type | NEWS_RISK | THEME_HEAT | AI_JUDGMENT |
| --- | --- | --- | --- |
| `RISK_ALERT` · `THESIS_BROKEN` | `HIGH` | `NEUTRAL` | `RISK_INCREASING` |
| `WATCH` · `SELL_REVIEW` | `MEDIUM` | `NEUTRAL` | `WATCH` |
| `OVERHEATED` | `MEDIUM` | `OVERHEATED` | `WATCH` |
| `BUY_CANDIDATE` | `LOW` | `NEUTRAL` | `WATCH` |
| 그 외 · snapshot 없음 · signal_type None | `LOW` | `NEUTRAL` | `STABLE` |

- evaluator의 `_ORDERED_VALUES`(NEWS_RISK: LOW<MEDIUM<HIGH, THEME_HEAT:
  COLD<NEUTRAL<OVERHEATED)와 정확히 같은 리터럴을 쓴다. `COLD`는 파생 매핑에서 사용하지
  않는다.
- `AI_JUDGMENT_CHANGED`는 값 자체가 아니라 전이 지표다: current = 최신 스냅샷의 매핑 값,
  previous = 직전 스냅샷의 매핑 값. `_signal_change`와 동일하게 (current, previous,
  has_previous, evidence, asset_id)를 반환하면 evaluator의 `CHANGED` 연산이 판정한다.
  직전 스냅샷이 없으면 has_previous=False.

### 대상(target_type)별 스코프

- `SYMBOL`: 기존 `_symbol_asset`으로 자산 확정 → 해당 자산의 latest/previous 스냅샷 매핑.
- `WATCHLIST`: `_earnings_date`와 같은 방식으로 소유 검증 후 아이템 자산 목록 →
  `latest_pair_by_asset` 일괄 조회.
- `PORTFOLIO`: `_position_weight`와 같은 방식으로 소유 검증 후 포지션 자산 목록 → 동일.
- 다자산 집계(WATCHLIST·PORTFOLIO):
  - `NEWS_RISK`·`THEME_HEAT`: 자산별 매핑 값 중 **최댓값**(ordered 기준). previous도 같은
    규칙으로 집계하고, 대상 자산 중 하나라도 직전 스냅샷이 있으면 has_previous=True.
  - `AI_JUDGMENT_CHANGED`: 매핑 값이 전이(current != previous, 직전 존재)한 자산이 있으면 그
    자산의 (current, previous)를 채택한다. 복수면 `RISK_INCREASING` 우선, 그다음 asset_id
    오름차순으로 결정론적으로 하나를 고른다. 전이 자산이 없으면 전체 집계 값
    (최신 매핑 값 중 최고 심각도 자산 기준)을 current로, 그 자산의 직전 값을 previous로 쓴다.
  - evidence·asset_id는 채택된(또는 최고 심각도) 자산 기준.
- 대상 검증 실패(소유 아님·자산 없음 등)는 기존 메서드들과 동일하게 `None` 반환.

### Evidence

`_signal_change`의 `SIGNAL_SNAPSHOT` kind를 재사용하되, 파생 값을 함께 남긴다(예:
`{"kind": "SIGNAL_SNAPSHOT", "asset_id", "snapshot_date", "signal_id", "score",
"signal_type", "derived_metric", "derived_value"}`). FE 상세는 kind 기반 일반 렌더라 필드
추가는 안전하다. 새 kind 리터럴은 만들지 않는다.

## Implementation Scope

- `app/domains/alert_engine/snapshot_provider.py` — `UNSUPPORTED_METRICS`에서 3종 제거,
  `_read_metric` 분기 추가, 매핑·집계 헬퍼 추가.
- 매핑 함수는 snapshot_provider 내 private로 둔다(다른 도메인에서 아직 재사용처 없음).
- 단위·통합 테스트 추가(아래).

## Out of Scope

- evaluator·dedup·service·worker 변경(계약 그대로).
- LLM 평가 값 영속화·신규 테이블·마이그레이션.
- `TOPIC_IMPACT_SCORE` 소싱(토픽 인프라 보류로 UNSUPPORTED 유지).
- 템플릿 카탈로그·조건 스키마 변경.

## Protected Files / 주의

- `app/domains/signals/repository.py`·`watchlists`·`portfolios` 등 원천 도메인은 읽기만 하고
  수정하지 않는다.
- 기존 `_price_change`·`_signal_change`·`_position_weight`·`_earnings_date` 동작·반환 계약을
  바꾸지 않는다.

## Requirements

1. `UNSUPPORTED_METRICS == {TOPIC_IMPACT_SCORE}`.
2. SYMBOL 대상 `NEWS_RISK_HIGH` 규칙이 RISK_ALERT 스냅샷 자산에서 matched=True로 평가된다.
3. WATCHLIST 대상 `WATCHLIST_AI_JUDGMENT` 규칙이 아이템 자산의 판단 전이
   (예: WATCH→RISK_INCREASING) 시 matched=True, 전이 없으면 False.
4. PORTFOLIO 대상 `HOLDING_NEWS_RISK` 규칙이 보유 자산 중 최고 위험 기준으로 평가된다.
5. 스냅샷이 없는 자산만 있는 대상은 기본값(LOW/NEUTRAL/STABLE)으로 평가되어 발동하지 않는다
   (조용한 미발동, 예외 없음).
6. 반환 evidence는 `SIGNAL_SNAPSHOT` kind + 파생 값 필드를 포함한다.

## Test Requirements

- 매핑 단위 테스트: signal_type 전 케이스(6종 + None/없음) → 3지표 값.
- 집계 단위 테스트: 다자산 max, AI_JUDGMENT 전이 자산 선택(복수 전이 시 결정론적 tie-break),
  has_previous 규칙.
- 통합(DB) 테스트: 실제 `AssetSignalSnapshot` 픽스처(실계약 형태)로 SYMBOL·WATCHLIST·
  PORTFOLIO 각 1개 이상 — provider.get_snapshot이 값·previous·evidence·asset_id를 채우는지,
  evaluator까지 물려 matched 판정 1건 이상.
- 기존 테스트 회귀 없음.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

- 없음(설계 §5 범위 내 구현). 매핑이 설계와 어긋난다고 판단되면 멈추고 보고한다.

## Risk Level

Medium — 코드 범위는 파일 하나지만, 다자산 집계·전이 판정의 결정론과 기본값(스냅샷 부재)
경계가 틀리면 오발동·미발동으로 직결된다. 매핑 리터럴은 evaluator `_ORDERED_VALUES`·
`watchlists.types` enum과 정확히 일치해야 한다.

## Expected Output

- snapshot_provider 확장 + 단위·통합 테스트.
- 지정된 현재 브랜치(아래)에 커밋. 자체 브랜치 생성 금지.
- 검증 3종(ruff·mypy·pytest) 통과 보고.

## Rules

- Stay within scope. 엔진에서 LLM 호출·신규 테이블 추가 금지.
- 원천 도메인은 읽기 전용.
- Do not weaken verification.
- 지정된 현재 브랜치를 유지한다. 새 브랜치 금지.
- Report assumptions and verification results.
