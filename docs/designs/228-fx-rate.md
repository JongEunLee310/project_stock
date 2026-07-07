# Design: 환율 API와 시세 통화 정보 (#228)

## Status

Implemented

## Context

FE에서 달러 현재가에 원화 환산을 병기하고 사이드바에 환율을 상시 노출하려 한다.
이를 위해 BE가 USD/KRW 환율과, 관심종목 확장 조회 시세의 통화 정보를 제공한다.

## Verified Facts (origin/dev 기준, 2026-07-07 확인)

- `app/adapters/market/base.py` — capability별 ABC + frozen dataclass 패턴
  (`IndexQuoteProvider.get_quotes` 등). `QuoteResult.currency: str` 존재.
- `app/adapters/factory.py` — `settings.MARKET_PROVIDER` 분기, mock 외 미구현은
  NotImplementedError.
- `app/domains/market/schema.py` — `MarketIndexQuoteResponse(symbol, name, value,
  change_percent, reference_at)`. `app/api/v1/endpoints/market.py`에 `GET /indices`.
- `app/domains/watchlists/service.py:list_items_expanded` — `AssetBriefResponse`를
  quote에서 조립. quote가 None이면 price/change_percent를 "0"으로 채운다.
- `app/domains/watchlists/schema.py` — `AssetBriefResponse(symbol, market, name,
  price, change_percent, sector)`. currency 없음.

## Interfaces

### ExchangeRateProvider (신규 ABC, `app/adapters/market/base.py`)

- `ExchangeRateResult` (frozen dataclass): `pair: str`(예: "USD/KRW"), `rate: Decimal`,
  `change_percent: Decimal`, `as_of: datetime`
- `ExchangeRateProvider.get_rates(pairs: list[str]) -> list[ExchangeRateResult]`

### 구현체

- `MockExchangeRateProvider` (`app/adapters/market/mock.py`) — 결정적 값
  (USD/KRW 등 소수 페어). 미지원 페어는 결과에서 제외.
- `get_exchange_rate_provider()` (`app/adapters/factory.py`) — mock 분기만 구현.
  yfinance 구현은 provider 전역 스위치 분리 논의(PR #227 인라인) 이후 별도 이슈.

### API

- `GET /api/v1/market/fx?pairs=USD/KRW` — `pairs`는 쉼표 구분 선택 파라미터,
  기본값 `USD/KRW`.
  - 응답: `ApiResponse[list[ExchangeRateResponse]]`
  - `ExchangeRateResponse`: `pair`, `rate: Decimal`, `change_percent: Decimal`,
    `reference_at: UtcDatetime` (기존 `MarketIndexQuoteResponse` 표기 규칙과 동일)
- `AssetBriefResponse`에 `currency: str | None` 추가 — quote가 있으면
  `quote.currency`, 없으면 None. 기존 필드·기본값은 변경하지 않는다 (FE 하위 호환:
  필드 추가만).

## Out of Scope

- yfinance 환율 구현 (provider 스위치 분리 후속)
- FE 표시 (project_stock_frontend#115)
- 다른 응답(AssetDetailResponse 등)의 통화 처리 변경 — 이미 currency 보유

## Test Strategy

- mock provider 단위 테스트 (지원 페어 반환·미지원 페어 제외·결정성)
- `GET /market/fx` 엔드포인트 테스트 (기본 파라미터·명시 파라미터)
- 관심종목 확장 조회 응답에 currency 포함 테스트 (기존 테스트 보강)
- factory 분기 테스트
