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

---

## 계약 확정 (Frozen Contract) — 2026-06-25, Opus

이 섹션이 **확정 계약**이다. FE#47은 이 표기를 기준으로 병렬 착수한다. 와이어 표기는 기존 BE 컨벤션(snake_case 필드, Decimal=문자열, `UtcDatetime`=`...Z`, `ApiResponse` 엔벨로프)에 정렬했다 — `app/domains/assets/schema.py`·`app/core/response.py`·`app/core/schema.py` 확인 기준.

### 엔드포인트
```
GET /api/v1/stocks/{symbol}/prices
```

### 쿼리 파라미터 (확정)
| 파라미터 | 필수 | 기본 | 허용값 | 위반 시 |
|----------|------|------|--------|---------|
| `market` | 필수 | — | `KRX` `NASDAQ` `NYSE` | VALIDATION_ERROR (422) |
| `range` | 선택 | `3M` | `1M` `3M` `6M` `1Y` | INVALID_PRICE_RANGE (400) |
| `interval` | 선택 | `1d` | `1d` (MVP 한정) | INVALID_PRICE_INTERVAL (400) |
| `adjusted` | 선택 | `true` | bool | — |

- `symbol`+`market` 복합키. `market` 필수(거래소 간 symbol 중복 방지).
- `adjusted=false`면 mock은 `adjusted_close == close`로 응답. 두 필드는 항상 포함.
- **soft validate 안 함(MVP)**: 미등록 symbol도 조회 가능. 데이터 없으면 PRICE_SERIES_NOT_FOUND(404).

### 응답 (성공) — `ApiResponse[PriceSeriesResponse]`
```jsonc
{
  "data": {
    "symbol": "005930",
    "market": "KRX",
    "currency": "KRW",
    "interval": "1d",
    "range": "3M",
    "source": "mock",
    "last_updated_at": "2026-06-25T06:00:00Z",   // UtcDatetime, ...Z
    "bars": [
      {
        "date": "2026-06-24",        // 거래일 캘린더 날짜 (YYYY-MM-DD, 타임존 없음)
        "open": "71000",             // Decimal 문자열
        "high": "72500",
        "low": "70800",
        "close": "72000",
        "adjusted_close": "72000",
        "volume": 12345678            // 정수(JSON number)
      }
      // ... range에 해당하는 일봉 오름차순
    ]
  },
  "message": null,
  "error": null,
  "meta": null
}
```

- **필드 표기 snake_case**: `adjusted_close`, `last_updated_at`. FE 어댑터(#45)가 도메인 camelCase로 매핑.
- **OHLC + adjusted_close = Decimal 문자열**(C5). `volume` = 정수.
- **`bars`는 페이지네이션 없음** — `range` 전체를 한 번에 반환, `meta=null`. 일봉이라 양 제한적.

### 시간 표기 결정 (타임존 주의 — 오프바이원 방지)
- **`bars[].date`는 캘린더 날짜 문자열 `YYYY-MM-DD`, 타임존 없음.** 일봉은 "순간(instant)"이 아니라 거래일 집계이므로 UTC instant로 인코딩하지 않는다. UTC instant로 주면 FE가 KST 변환 시 하루 밀리는 버그(오프바이원)가 난다. FE는 `date`를 **타임존 변환 없이** 캘린더 날짜로 그대로 표시한다.
- **`last_updated_at`은 실제 instant이므로 `UtcDatetime`(`...Z`)**, FE에서 KST 표시.
- 검증: 날짜 경계 테스트는 `TZ=UTC`로 수행, mock 생성 날짜와 응답 `date` 1:1 단언. [[verify-timezone-tz-utc]]

### 에러 코드 (확정) — `app/core/error_codes.py` 추가
| 코드 | HTTP | 상황 |
|------|------|------|
| `INVALID_PRICE_RANGE` | 400 | 미지원 range |
| `INVALID_PRICE_INTERVAL` | 400 | 미지원 interval(MVP는 1d 외 전부) |
| `PRICE_SERIES_NOT_FOUND` | 404 | symbol+market 데이터 없음 |
| `MARKET_DATA_PROVIDER_ERROR` | 502 | provider 오류 |

- `STOCK_NOT_FOUND`는 **추가 안 함** — soft validate를 안 하므로 미등록/무데이터는 PRICE_SERIES_NOT_FOUND로 흡수. (`market`/필수 누락은 기존 VALIDATION_ERROR.)

### Provider 구조
- `app/adapters/market/`에 `PriceSeriesProvider`(ABC) + `MockPriceSeriesProvider` 추가. 기존 `MarketDataProvider`(quote)와 병렬.
- 선택은 기존 `MARKET_PROVIDER`(`app/core/config.py`, mock/real) 스위치 재사용. 별도 env 추가 안 함.
- `MockPriceSeriesProvider`는 symbol 시드 기반 **결정론적** 합성 OHLCV 생성(테스트 재현성). range→봉 개수 매핑(1M≈22, 3M≈66, 6M≈132, 1Y≈252 영업일 근사).

### 저장 테이블 `stock_price_bars` (확정 — 이슈대로 생성)
사용자 결정(2026-06-25): 이슈대로 테이블 생성. **DB 스키마 변경이므로 human-gate 선행**(ADR-005 #6).

**read 경로 = 테이블 경유(확정)**: MockPriceSeriesProvider가 결정론적 OHLCV 생성 → 서비스가 `stock_price_bars`에 **유니크키 기준 idempotent upsert**(lazy seed) → range 필터·`timestamp` 오름차순으로 **DB에서 조회해 응답**. 테이블이 실제로 사용되도록(빈 테이블 방지) 한다.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `id` | PK int | |
| `symbol` | String(20) | |
| `market` | String(20) | |
| `interval` | String(10) | MVP `1d` |
| `timestamp` | DateTime(timezone=True) | 일봉은 거래일 **00:00:00+00**(UTC 자정)으로 저장. 와이어 `date`=이 값의 UTC 날짜부분 |
| `open_price` | Numeric(20,4) | |
| `high_price` | Numeric(20,4) | |
| `low_price` | Numeric(20,4) | |
| `close_price` | Numeric(20,4) | |
| `adjusted_close_price` | Numeric(20,4) | |
| `volume` | BigInteger | |
| `currency` | String(10) | |
| `source` | String(30) | mock 등 |
| (TimestampMixin) | created_at/updated_at | ingest 추적 |

- `UniqueConstraint(symbol, market, interval, timestamp)` 이름 `uq_price_bars_symbol_market_interval_ts`.
- Alembic 마이그레이션 신규(리비전 체인 `c3d4e5f60055...` 다음). down_revision 최신 head 확인 필수.
- **와이어 `date` 도출**: `timestamp`를 UTC 자정에 저장하므로 `date` = `timestamp`의 UTC 날짜부분. KST 변환 없음 → 오프바이원 차단. [[verify-timezone-tz-utc]]
