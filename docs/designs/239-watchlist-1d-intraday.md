# Design: watchlist 1D 스파크라인 인트라데이 지원

## Status

Implemented

## Revision History

| 버전 | 날짜 | 변경 내용 |
|---|---|---|
| R0 | 2026-07-08 | 초안 작성. |

## Source Issue

https://github.com/JongEunLee310/project_stock/issues/239

## Context

watchlist 페이지 변화(1D) 컬럼은 당일 가격 움직임을 스파크라인으로 표현한다. 현재
`GET /api/v1/watchlists/{id}/sparklines?range=1D`는 `"1D"`를 허용하지 않아 422를 반환한다.
지원 범위가 `"1M"·"3M"·"6M"·"1Y"` 네 가지뿐이고 모두 interval="1d" 일봉으로 고정되어
있기 때문이다. 하루 동안의 변화를 표현하기에 일봉은 부적합하므로, 15분 간격 당일
인트라데이 바를 반환하는 `range=1D` 경로를 신설한다.

## Verified Facts (dev, 2026-07-08 확인)

- `app/domains/prices/service.py:14-20` — `_RANGE_COUNTS = {"1M": 22, "3M": 66, "6M": 132, "1Y": 252}`,
  `_SUPPORTED_INTERVAL = "1d"` 단일. `"1D"` 키 없음.
- `app/domains/prices/service.py:91-105` — `_validate_range()`는 `_RANGE_COUNTS` 키 이외 값에
  `ErrorCode.INVALID_PRICE_RANGE`(400) 발생. `_validate_interval()`는 `"1d"` 이외 값에
  `ErrorCode.INVALID_PRICE_INTERVAL`(400) 발생.
- `app/domains/prices/service.py:127-135` — `_to_bar()`가 `bar.timestamp.date().isoformat()`을
  `PriceBar.date`에 넣는다. 시간 정보가 소실된다.
- `app/domains/prices/service.py:40-47` — `get_series()`가 `get_price_series_provider().get_daily_bars()`를
  호출한다. interval은 provider에 전달되지 않는다.
- `app/domains/prices/model.py:12-19` — `StockPriceBar`에 `interval: Mapped[str]`(String(10)) 컬럼과
  `uq_price_bars_symbol_market_interval_ts` UniqueConstraint가 이미 존재한다. DB 마이그레이션 불필요.
- `app/domains/watchlists/sparkline_service.py:40-45` — `price_series_service.get_series()`를
  `interval="1d"` 하드코딩으로 호출한다.
- `app/api/v1/endpoints/watchlists.py:191-194` —
  `sparkline_range: Annotated[Literal["1M", "3M", "6M", "1Y"], Query(alias="range")] = "1M"`.
  `"1D"` 리터럴 없음.
- `app/adapters/market/base.py:49-57` — `PriceSeriesProvider`에 `get_daily_bars()` 추상 메서드 하나만 있다.
  interval 파라미터를 받지 않는다.
- `app/adapters/market/yfinance.py:46-88` — `YFinancePriceProvider.get_daily_bars()`는
  `ticker.history(period=_range_to_period(range_value), interval="1d", auto_adjust=adjusted)`로
  호출한다. interval="1d" 하드코딩.
- `app/adapters/market/yfinance.py:150-156` — `_range_to_period()`는
  `"1M"→"1mo", "3M"→"3mo", "6M"→"6mo", "1Y"→"1y"` 매핑. `"1D"` 없음.
- `app/core/error_codes.py:13-15` — `INVALID_PRICE_RANGE`, `INVALID_PRICE_INTERVAL`,
  `PRICE_SERIES_NOT_FOUND` 이미 정의되어 있다.
- `app/domains/watchlists/schema.py:68-70` — `SparklineBar.date: str`, `SparklineBar.close: str`.
  FE는 `bars[].close`만 사용하므로 `date` 필드 형식 변경은 안전하다.
- `app/domains/prices/schema.py:6-13` — `PriceBar.date: str`. 타입 선언 변경 불필요.

## Design Decisions

### 1. `PriceSeriesProvider` 인터페이스 — `get_intraday_bars()` 추상 메서드 추가

기존 `get_daily_bars()`는 일봉 전용이고 interval 파라미터가 없다. 기존 시그니처를 그대로
유지하고, 인트라데이 조회를 위한 별도 추상 메서드 `get_intraday_bars(symbol, market)`를
추가한다. `YFinancePriceProvider`와 `MockPriceSeriesProvider` 모두 이를 구현한다.

yfinance 호출: `ticker.history(period="1d", interval="15m", auto_adjust=True)`.
`PriceBarResult.interval`은 `"15m"`으로 설정해 기존 일봉(`interval="1d"`)과 구별한다.

### 2. `PriceSeriesService` — range-interval 연결 테이블 도입

`_RANGE_COUNTS`에 `"1D": 26`을 추가한다. 26의 근거는 미국·한국 정규장 기준 6.5시간
(390분) ÷ 15분 = 26 바다(시장 관행, 가정). `_RANGE_INTERVALS` 매핑
`{"1M": "1d", "3M": "1d", "6M": "1d", "1Y": "1d", "1D": "15m"}`을 추가한다.

`get_series()`는 `range_value`로부터 interval을 파생한다. `range_value="1D"`이면
`get_intraday_bars()`를 호출하고, 나머지는 기존 `get_daily_bars()`를 그대로 호출한다.
외부에서 interval이 명시적으로 넘어올 경우 파생값과 일치하지 않으면 `INVALID_PRICE_INTERVAL`(400)
을 반환한다.

### 3. `_to_bar()` — 15m 바의 `date` 필드 표현

기존 `bar.timestamp.date().isoformat()`은 일봉에만 적합하다. 15m 바는 분 단위 시각이
필요하므로 `bar.timestamp.isoformat()` 전체 ISO-8601 datetime 문자열을 사용한다.
FE가 `date` 필드를 무시하므로 형식 변경은 소비자에게 영향이 없다.

별도 필드 추가 방식은 `SparklineBar` 스키마 변경이 필요하고 FE 계약이 바뀌므로 채택하지
않는다. 기존 `date: str` 필드를 유지하면서 값만 다르게 넣는 방식이 단순하다.

`_to_bar()`에 `interval` 파라미터를 추가해 `"1d"` 이외 값일 때 전체 datetime 문자열을
반환한다. 기존 1d 경로의 반환값은 그대로 `"YYYY-MM-DD"` 형식을 유지한다.

### 4. `WatchlistSparklineService` — interval 파생

`interval="1d"` 하드코딩 대신 `range_value`에 따라 interval을 결정하는 매핑을 참조한다.
`range_value="1D"`이면 `interval="15m"`, 나머지는 `"1d"`. `price_series_service.get_series()`에
파생된 interval을 전달한다.

### 5. ADR 불필요

DB 스키마 변경이 없고 신규 외부 의존성도 없다. adapter 계층에 메서드 하나를 추가하고
service 범위 값을 확장하는 수준으로, 기존 설계 경계 내의 변경이다.

## Interfaces

### `app/adapters/market/base.py` — PriceSeriesProvider 확장

```
class PriceSeriesProvider(ABC):
    @abstractmethod
    def get_daily_bars(
        self, symbol: str, market: str, range_value: str, adjusted: bool
    ) -> list[PriceBarResult]
        # 기존 일봉 조회. 변경 없음.
    @abstractmethod
    def get_intraday_bars(
        self, symbol: str, market: str
    ) -> list[PriceBarResult]
        # 당일 15분 간격 바 반환. interval="15m" 고정.
```

### `app/adapters/market/yfinance.py` — YFinancePriceProvider 확장

```
def get_intraday_bars(self, symbol: str, market: str) -> list[PriceBarResult]
    # ticker.history(period="1d", interval="15m", auto_adjust=True)
    # PriceBarResult.interval = "15m"
```

### `app/adapters/market/mock.py` — MockPriceSeriesProvider 확장

```
def get_intraday_bars(self, symbol: str, market: str) -> list[PriceBarResult]
    # interval="15m" 고정, 당일 샘플 바 최대 26개 반환
```

### `app/domains/prices/service.py` — PriceSeriesService 변경

```
_RANGE_COUNTS: dict[str, int]
    # 기존 4종 + "1D": 26

_RANGE_INTERVALS: dict[str, str]
    # "1M"/"3M"/"6M"/"1Y" → "1d", "1D" → "15m"

def get_series(
    self,
    symbol: str,
    market: str,
    range_value: str = "3M",
    interval: str | None = None,
    adjusted: bool = True,
) -> PriceSeriesResponse
    # range_value로부터 interval 파생. "1D"이면 get_intraday_bars() 호출.
    # 나머지는 기존 get_daily_bars() 경로 유지.

def _to_bar(self, bar: StockPriceBar, interval: str) -> PriceBar
    # interval="1d" → bar.timestamp.date().isoformat() (기존 동작 유지)
    # interval="15m" → bar.timestamp.isoformat()
```

### `app/domains/watchlists/sparkline_service.py` — WatchlistSparklineService 변경

```
def get_sparklines(
    self,
    watchlist_id: int,
    user_id: int,
    range_value: str = "1M",
) -> WatchlistSparklineResponse
    # range_value="1D"이면 interval="15m", 나머지는 "1d" 파생 후 get_series() 전달
```

### `app/api/v1/endpoints/watchlists.py` — sparkline 라우터 변경

```
GET /{watchlist_id}/sparklines
  sparkline_range: Literal["1M", "3M", "6M", "1Y", "1D"]
  Response: ApiResponse[WatchlistSparklineResponse]
  # 기존 4종 + "1D" 추가
```

## Dependencies

변경되는 파일은 모두 기존 파일이며 신규 모듈·테이블이 없다.

- `app/adapters/market/base` — `PriceSeriesProvider` 추상 메서드 추가
- `app/adapters/market/yfinance` — `YFinancePriceProvider` 구현 추가
- `app/adapters/market/mock` — `MockPriceSeriesProvider` 구현 추가
- `app/domains/prices/service` — range 확장, `_to_bar` 수정
- `app/domains/watchlists/sparkline_service` — interval 파생 로직
- `app/api/v1/endpoints/watchlists` — `Literal` 확장

## Out of Scope

- FE 스파크라인 소비 코드 변경
- prices 공개 엔드포인트(`GET /api/v1/stocks/{symbol}/prices`)에서 `range=1D` 지원
- 프리마켓·애프터마켓 바 포함
- 웹소켓 또는 실시간 업데이트

## ADR Need

불필요. 신규 테이블·외부 의존성 없음. 기존 adapter 계층 내 메서드 추가와 service 범위
값 확장이며, 아키텍처 방향 변경이나 대안 선택 이력을 ADR로 남길 필요가 없다.

## Test Strategy

### 신규·변경 테스트

- `PriceSeriesService.get_series(range_value="1D")` — `get_intraday_bars()` 호출 확인,
  반환 바 수가 limit(26) 이하
- `_validate_range("1D")` — 통과, `_validate_range("2D")` — `INVALID_PRICE_RANGE` 400
- `_to_bar(bar, interval="15m")` — `date` 필드가 ISO datetime 문자열 형식
- `_to_bar(bar, interval="1d")` — `date` 필드가 `"YYYY-MM-DD"` 형식 유지 (기존 동작)
- `WatchlistSparklineService.get_sparklines(range_value="1D")` — `interval="15m"`으로
  `get_series()` 호출 확인
- `GET /api/v1/watchlists/{id}/sparklines?range=1D` 통합 테스트 — 200, bars의 `date`가
  datetime 형식
- `GET /api/v1/watchlists/{id}/sparklines?range=2D` — 422
- 기존 1M/3M/6M/1Y 스파크라인 테스트 전부 통과 유지

### 픽스처 출처 주석 규율

픽스처의 `range` 값(`"1D"`, `"1M"` 등)은 `app/api/v1/endpoints/watchlists.py`의 `Literal`
정의에서 인용하고 출처 주석을 추가한다. `interval` 값(`"15m"`, `"1d"`)은
`app/domains/prices/service.py`의 `_RANGE_INTERVALS`에서 인용한다.

## Open Questions

없음.
