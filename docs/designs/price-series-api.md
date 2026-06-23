# BE 추가 필요 작업: 주식 종목 가격 시계열 API

상태: **제안(Draft)** — 작성 2026-06-23. `docs/api/contract-alignment.md`의 G4/N4 후속.
구현 전 작업지도다. 실제 issue/ADR로 쪼갤 때 기준 문서로 쓴다.

## 배경

FE에는 종목 상세 화면 또는 대시보드에서 시계열 차트를 표시하는 기능이 있다.
하지만 현재 BE에는 주식 종목의 가격 흐름을 조회할 수 있는 API가 없기 때문에, 차트 렌더링에
필요한 가격 시계열 API를 추가해야 한다. 지금 단계에서는 **"FE 차트를 살리기 위해 BE에
무엇이 필요한가"**만 정리한다. (FE Signal 모멘텀 시각화도 이 API에 의존하므로 **Signal
연동보다 먼저 완성**한다 — contract-alignment N4.)

## 만들어야 할 것

### 1. 종목 가격 시계열 조회 API

FE에서 특정 종목의 가격 데이터를 조회할 수 있는 API를 만든다.

```http
GET /api/v1/stocks/{symbol}/prices
```

지원할 주요 조회 조건:

```text
- market: 시장 구분, 예: KRX, NASDAQ, NYSE
- range: 조회 기간, 예: 1M, 3M, 6M, 1Y
- interval: 봉 단위, MVP에서는 1d
- adjusted: 수정주가 사용 여부
```

### 2. 가격 시계열 응답 스키마

FE 차트에서 사용할 수 있도록 날짜별 가격 정보를 반환한다.

필수 데이터:

```text
- date
- open
- high
- low
- close
- adjustedClose
- volume
```

메타 정보:

```text
- symbol
- market
- currency
- source
- lastUpdatedAt
```

### 3. 가격 데이터 저장 테이블

주식 가격 데이터를 저장하기 위한 테이블을 추가한다.

예상 테이블명: `stock_price_bars`

주요 컬럼:

```text
- symbol
- market
- interval
- timestamp
- open_price
- high_price
- low_price
- close_price
- adjusted_close_price
- volume
- currency
- source
```

### 4. Market Data Provider 구조

외부 시세 API 또는 Mock 데이터를 쉽게 교체할 수 있도록 Provider 인터페이스를 둔다.
기존 `app/adapters/*`(market/news/...)의 `*_PROVIDER` 전환 패턴과 일관되게 둔다.

필요 구성:

```text
- PriceProvider 인터페이스
- MockPriceProvider
- 향후 ExternalPriceProvider
```

MVP에서는 실제 외부 API 연동보다 Mock Provider를 먼저 구현해 FE와 연결할 수 있도록 한다.

### 5. 에러 처리

다음 상황에 대한 에러 응답을 정의한다. 코드는 `app/core/error_codes.py`의 `ErrorCode`에 추가한다.

```text
- 지원하지 않는 range
- 지원하지 않는 interval
- 존재하지 않는 종목
- 가격 데이터 없음
- 외부 시세 provider 오류
```

예상 에러 코드:

```text
- INVALID_PRICE_RANGE
- INVALID_PRICE_INTERVAL
- STOCK_NOT_FOUND
- PRICE_SERIES_NOT_FOUND
- MARKET_DATA_PROVIDER_ERROR
```

## MVP 범위

초기 구현 범위는 다음으로 제한한다.

```text
- 단일 종목 가격 조회
- 일봉 데이터만 지원
- OHLCV 응답 제공
- Mock Provider 사용
- FE 차트 연동 가능 상태까지 구현
```

실시간 시세, 분봉, 다중 종목 비교, 외부 API 연동은 후속 작업으로 분리한다.

## 후속 작업 후보

```text
- 실제 외부 시세 API 연동
- 가격 데이터 주기적 동기화
- 다중 종목 가격 비교 API
- 수익률 정규화 API
- 이동평균선 계산
- 거래량 차트 지원
- 캐시 전략 추가
```

## 정렬 주의

- **리소스 네이밍 = symbol 기반 확정**: 본 API는 `/stocks/{symbol}` + `market`을 키로 쓴다
  (`/assets/{asset_id}` 아님). FE 라우팅(`/research/:symbol`)·G6와 정합.
- **키는 (symbol, market) 복합**: symbol은 거래소 간 유일하지 않으므로(국내 `005930` vs 해외
  티커 중복) **항상 `market`과 함께** 식별한다. `stock_price_bars`도
  `(symbol, market, interval, timestamp)` 유니크로 둔다.
- **assets와의 관계**: 종목 등록(`POST /assets`)이 이미 `symbol`+`market`을 받으므로 **별도 필드
  추가는 불필요**하다. 가격 테이블은 `asset_id` FK 대신 `(symbol, market)`로 느슨히 연결한다 —
  등록 전 종목도 가격 적재 가능. symbol+market이 assets에 존재하는지 검증할지(soft validate)는 구현 시 결정.
- **응답 필드 표기**: 위 스키마는 camelCase로 적었으나 최종 와이어 표기(snake_case)·금액 문자열
  Decimal(C5)은 contract 확정 시 맞춘다.
- **시간 표기**: `timestamp`/`lastUpdatedAt`은 C6에 따라 **와이어 UTC**, FE에서 KST 표시.
