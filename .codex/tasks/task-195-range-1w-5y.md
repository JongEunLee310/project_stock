# Codex Handoff Task

## Source Issue

이슈 #319 — 가격 시계열 range 확장 (1W 30분봉·5Y 주봉). 이슈 본문을
먼저 읽는다.

## Task Summary

`GET /stocks/{symbol}/prices`의 range에 `1W`(interval 30m, 65봉)와
`5Y`(interval 1wk, 260봉)를 추가한다. 직전 라운드(#316, PR #317)의
5m 전환과 같은 구조 확장이다.

## Goal

- `range=1W` → `interval: "30m"`, ISO datetime `date`, 최대 65봉.
- `range=5Y` → `interval: "1wk"`, 캘린더 날짜 `date`(주 시작일),
  최대 260봉.
- 기존 range 5종(1D·1M·3M·6M·1Y)은 회귀 없음.

## Implementation Scope

- `app/domains/prices/service.py` — `_RANGE_COUNTS`·`_RANGE_INTERVALS`
  확장, `_to_bar`의 date 분기(`1d`뿐 아니라 `1wk`도 캘린더 날짜)
  정리.
- `app/adapters/market/yfinance.py` — 1W(`period="5d"`,
  `interval="30m"`)·5Y(`period="5y"`, `interval="1wk"`) 수집 경로.
  기존 intraday/일봉 함수 구조를 따르되 과한 추상화 없이 확장한다.
- `app/adapters/market/mock.py` — 30m·1wk 결정적 생성 동기화.
- `tests/test_price_series.py` — 신규 range 2종의 interval·봉 수·
  date 포맷 검증 + 기존 회귀.
- 문서 — `docs/designs/price-series-api.md` 허용값 표,
  `docs/api/frontend-api-spec.md`.

## Out of Scope

- benchmark-comparison 계약 확장 (1W·5Y 벤치마크 비교 미지원)
- 워치리스트 스파크라인 (1D 경로 그대로)
- FE 수정 (별도 repo, FE #215)

## Protected Files

없음.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Constraints

- 현재 브랜치(`feat/319-range-1w-5y`)에서 그대로 작업한다. 새 브랜치
  생성·checkout 금지.
- 커밋은 한국어 `type: 본문` 형식으로 작성한다.
- 이 태스크 문서와 구현이 같은 PR에 함께 실린다.
