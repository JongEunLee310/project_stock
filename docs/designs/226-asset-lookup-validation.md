# Design: 종목 lookup API와 등록 검증 (#226)

## Status

Implemented

## Context

FE 종목 추가 실사용 테스트에서 두 가지 결함이 확인되었다. `GET /assets?symbol=`이
대소문자 구분 완전 일치만 지원해 부분 입력으로 기존 종목을 찾지 못하고, 등록이 자유
입력이라 실존하지 않는 심볼(`APPL`)과 오염된 표기(`apple`, `Communication Services)`)가
DB에 저장되었다. DB에는 검증된 정보만 저장되도록 실시장 데이터 기반 lookup과 등록 시
서버 검증·보강을 도입한다.

## Verified Facts (origin/dev 기준, 2026-07-07 확인)

- `app/adapters/market/base.py` — capability별 ABC 분리 패턴: `MarketDataProvider.get_quote`,
  `PriceSeriesProvider.get_daily_bars`, `IndexQuoteProvider.get_quotes`. 결과는 frozen dataclass.
- `app/adapters/factory.py:33-50` — `get_market_provider`/`get_price_series_provider`/
  `get_index_quote_provider`가 `settings.MARKET_PROVIDER`(mock/real/yfinance) 분기.
  yfinance 분기는 price series에만 존재.
- `app/domains/assets/schema.py` — `AssetCreate(symbol≤20, name≤255, market≤20, sector?, industry?, description?)`.
- `app/domains/assets/service.py:15-37` — `register`: `get_by_symbol_market` 중복 검사(400
  `ASSET_DUPLICATE`) 후 `repo.create`.
- `app/domains/assets/repository.py:36` — symbol 필터는 `Asset.symbol == symbol` 완전 일치.
- `pyproject.toml` — `yfinance>=1.5.1` 의존성 존재. `tests/test_providers.py`에 factory
  분기 테스트 패턴 존재.
- POST API를 직접 호출하는 기존 테스트는 `tests/test_assets.py` 2곳뿐, 나머지 픽스처는
  repository 직접 생성.

## Interfaces

### SymbolLookupProvider (신규 ABC, `app/adapters/market/base.py`)

- `SymbolLookupResult` (frozen dataclass): `symbol: str`, `name: str`, `market: str`,
  `sector: str | None`
- `SymbolLookupProvider.search(query: str, market: str | None) -> list[SymbolLookupResult]`
  — 심볼·종목명 부분 일치(대소문자 무시), market 지정 시 해당 시장으로 제한

### 구현체

- `MockSymbolLookupProvider` (`app/adapters/market/mock.py`) — 결정적 소형 카탈로그
  (주요 미국 종목 10여 개, market·sector 포함). 로컬·테스트 기본.
- `YFinanceSymbolLookupProvider` (`app/adapters/market/yfinance.py`) — Yahoo Finance
  search 기반. sector가 없으면 None. 네트워크 오류는 `MARKET_DATA_PROVIDER_ERROR`로 변환.
- `get_symbol_lookup_provider()` (`app/adapters/factory.py`) — mock/yfinance 분기,
  그 외 NotImplementedError (기존 패턴 동일).

### API

- `GET /api/v1/assets/lookup?query=<str>&market=<str|None>` (인증 필요, 기존 assets
  라우터와 동일 규칙)
  - 응답: `ApiResponse[AssetLookupResponse]` — `items: list[AssetLookupItem]`
  - `AssetLookupItem`: `symbol`, `name`, `market`, `sector: str|None`,
    `registered: bool` (repo `get_by_symbol_market` 존재 여부)
  - 라우터 등록 순서 주의: `/{asset_id}` 경로보다 먼저 선언해야 `lookup`이 int 파싱
    422로 빠지지 않는다.
- `POST /api/v1/assets` 계약 변경 (breaking, 유일 클라이언트 FE는 #112에서 대응)
  - `AssetCreate` → `symbol: str(≤20)`, `market: str(≤20)` 2필드
  - `register` 책임: symbol 대문자 정규화 → 중복 검사(기존 400 유지) → lookup provider로
    실존 검증(정확 심볼 일치) → 실존하지 않으면 422 `ASSET_NOT_IN_MARKET`(신규 ErrorCode)
    → provider가 준 name·sector로 보강해 저장 (sector 조회 실패 시 null)

## Out of Scope

- FE 모달 개편 (project_stock_frontend#112)
- `GET /assets?symbol=` 완전 일치 필터 변경 — lookup이 검색 역할을 대체하므로 유지
- 기존 industry/description 컬럼 제거 (컬럼은 유지, 등록 시 null)
- dev DB 오염 행 정리 (일회성 SQL, 별도 수행)

## Test Strategy

- mock lookup provider 단위 테스트 (부분 일치·대소문자 무시·market 필터)
- lookup 엔드포인트 테스트 (registered 플래그 포함)
- 등록 검증 테스트: 실존 심볼 등록 성공·name/sector 보강 확인, 미실존 심볼 422,
  중복 400 유지
- yfinance lookup 어댑터는 네트워크 없이 monkeypatch로 검증 (기존 yfinance 테스트 패턴)
- factory 분기 테스트 (`tests/test_providers.py` 패턴)
