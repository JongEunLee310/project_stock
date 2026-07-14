# Codex Handoff Task

## Source Issue

이슈 #308 — BE: 가격 시계열 API 계약 결함. 이슈 본문에 재현 절차와
원인 분석이 있으므로 먼저 전체를 읽는다.

## Task Summary

`GET /stocks/{symbol}/prices`의 두 가지 계약 결함을 수정한다.

1. `interval` 쿼리 파라미터 기본값이 `"1d"`로 고정되어 있어 range=1D
   (파생 interval `15m`)가 항상 400(`INVALID_PRICE_INTERVAL`)으로
   실패한다.
2. `market` 파라미터가 `Literal["KRX", "NASDAQ", "NYSE"]`라서 자산
   도메인의 실제 값인 KOSPI/KOSDAQ이 422로 거부된다. KRX는 yfinance
   어댑터의 `_MARKET_SUFFIXES`에 매핑이 없는 죽은 값이다.

## Goal

- `range=1D` 요청이 interval 파라미터 없이 15m 봉 시계열을 반환한다.
- `market=KOSPI`·`market=KOSDAQ` 요청이 정상 응답한다.
- NASDAQ/NYSE·일봉 경로는 회귀가 없다.

## Implementation Scope

- `app/api/v1/endpoints/prices.py`
  - `interval` 파라미터를 `str | None = None`으로 변경해 서비스의
    range 기반 파생(`_RANGE_INTERVALS`)에 위임한다.
  - `market` 타입을 `Literal["KOSPI", "KOSDAQ", "NASDAQ", "NYSE"]`로
    교체한다 (KRX 제거 — 자산 도메인 `assets.market` 값과 정렬).
- `app/adapters/market/mock.py`
  - `_currency_for_market`의 `KRX` 분기를 KOSPI/KOSDAQ 기준으로
    교체한다 (yfinance 어댑터의 `_market_currency`와 동일 기준).
- `tests/test_price_series.py`
  - 기존 `market=KRX` 케이스를 KOSPI로 교체한다.
  - 신규 케이스: `range=1D` interval 미지정 요청이 200과 `interval:
    "15m"`를 반환한다 (mock provider 경로).
  - 신규 케이스: `market=KOSDAQ` 정상 응답, `market=KRX`가 422로
    거부된다.
- `docs/designs/price-series-api.md`
  - market 허용 값 표기(27행·173행·187행 예시)를 KOSPI/KOSDAQ/
    NASDAQ/NYSE로 갱신한다.

## Out of Scope

- `PriceSeriesService`·provider 인터페이스 시그니처 변경
- FE 수정 (별도 repo)
- 인덱스(^KS11 등)·환율 등 다른 시세 계약
- 마이그레이션·모델 변경 (없어야 정상)

## Protected Files

없음.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Constraints

- 현재 브랜치(`fix/308-price-series-contract`)에서 그대로 작업한다.
  새 브랜치 생성·checkout 금지.
- 커밋은 한국어 `type: 본문` 형식으로 작성한다.
- 이 태스크 문서와 구현이 같은 PR에 함께 실린다.
