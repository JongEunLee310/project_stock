# Codex Handoff Task

## Source Issue

https://github.com/JongEunLee310/project_stock/issues/239

## Task Summary

watchlist 변화(1D) 스파크라인용으로 15분 간격 당일 인트라데이 가격 시리즈를 지원한다.
`GET /api/v1/watchlists/{id}/sparklines?range=1D`가 15분 바를 반환하고, 기존 일봉
경로(1M/3M/6M/1Y + 1d)는 계약과 동작이 변하지 않는다.

## Goal

- `range=1D` 요청 시 15분 간격 당일 바가 시간 정보를 포함한 `date` 값과 함께 반환된다.
- 지원하지 않는 range 값은 기존과 동일하게 검증 오류를 반환한다.
- 기존 1M/3M/6M/1Y 경로의 응답 형식·동작이 변하지 않는다.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 모두 통과한다.

## Background

설계 문서: `docs/designs/239-watchlist-1d-intraday.md` — Verified Facts에 현재 코드
위치가, Design Decisions·Interfaces에 정확한 명세가 있다. 구현 전 Verified Facts를
실제 파일과 대조하고, 불일치하면 실코드를 우선한다.

핵심 명세 요약 (상세는 설계 문서):

- `PriceSeriesProvider`에 `get_intraday_bars(symbol, market)` 추상 메서드 추가.
  yfinance 구현은 `ticker.history(period="1d", interval="15m", auto_adjust=True)`,
  `PriceBarResult.interval="15m"`. Mock provider도 구현한다 (당일 샘플 바 최대 26개).
- `PriceSeriesService`: `_RANGE_COUNTS`에 `"1D": 26` 추가, `_RANGE_INTERVALS` 매핑
  신설 (`"1D"→"15m"`, 나머지 `"1d"`). `get_series()`는 range로부터 interval을 파생하고
  `"1D"`이면 `get_intraday_bars()`를 호출한다. 명시 interval이 파생값과 다르면
  `INVALID_PRICE_INTERVAL`(400).
- `_to_bar(bar, interval)`: `"1d"`는 기존 `timestamp.date().isoformat()` 유지,
  `"15m"`은 `timestamp.isoformat()` 전체 datetime 문자열.
- `WatchlistSparklineService.get_sparklines()`: interval="1d" 하드코딩 제거, range로부터
  파생한 interval을 `get_series()`에 전달.
- 엔드포인트 `sparkline_range` Literal에 `"1D"` 추가
  (`app/api/v1/endpoints/watchlists.py:191-194`).

DB 마이그레이션 불필요 — `stock_price_bars`에 `interval` 컬럼과 유니크 제약이 이미 있다.

## Implementation Scope

**수정 파일:**

- `app/adapters/market/base.py` — `get_intraday_bars` 추상 메서드 추가
- `app/adapters/market/yfinance.py` — `YFinancePriceProvider.get_intraday_bars` 구현
- `app/adapters/market/mock.py` — `MockPriceSeriesProvider.get_intraday_bars` 구현
- `app/domains/prices/service.py` — `_RANGE_COUNTS`·`_RANGE_INTERVALS`·`get_series`·
  `_validate_interval`·`_to_bar` 변경
- `app/domains/watchlists/sparkline_service.py` — interval 파생
- `app/api/v1/endpoints/watchlists.py` — `sparkline_range` Literal 확장

**테스트 파일:**

- 설계 문서 Test Strategy 절의 신규·변경 테스트를 모두 구현한다. 기존 테스트 배치를
  따른다 (`tests/` 아래 해당 도메인 테스트 파일에 추가).

## Out of Scope

- FE 변경
- prices 공개 엔드포인트(`GET /api/v1/stocks/{symbol}/prices`)의 `range=1D` 지원
- 프리마켓·애프터마켓 바, 실시간 업데이트
- DB 마이그레이션

## Protected Files

없음.

## Requirements

- 기존 테스트를 약화하거나 삭제하지 않는다.
- 테스트 픽스처의 range·interval 리터럴은 실제 계약 출처 주석을 명시한다
  (range는 `app/api/v1/endpoints/watchlists.py`의 Literal, interval은
  `app/domains/prices/service.py`의 `_RANGE_INTERVALS`).
- yfinance 실호출 없이 provider를 모킹해 테스트한다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

- `docs/designs/239-watchlist-1d-intraday.md` — 구현 완료 후 Status를 `Implemented`로
  갱신한다.

## ADR Need

불필요. 설계 문서 ADR Need 절 참조.

## Failure Record Need

불필요.

## Risk Level

Low — adapter 메서드 추가와 service 범위 값 확장. 기존 일봉 경로는 분기만 추가되고
동작이 유지된다.

## Expected Output

- 변경 파일 목록 보고
- 검증 3종 실행 결과 보고
- 가정·잔여 위험 보고

## Rules

- Stay within scope.
- Do not weaken verification.
- Report assumptions and verification results.
- 현재 브랜치 `feat/watchlist-intraday-sparkline`에서 작업한다. 새 브랜치를 생성하지 않는다.
- 커밋하지 않는다 (커밋은 오케스트레이터가 별도 지시한다).
