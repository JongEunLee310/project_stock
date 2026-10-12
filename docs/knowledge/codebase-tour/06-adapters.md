# 06. 어댑터 층

대상 파일: `app/adapters/factory.py`, `app/adapters/market/{base,mock,yfinance,cache}.py`,
`app/adapters/news/*`, `app/adapters/disclosure/*`, `app/adapters/portfolio/*`

## 어댑터 층이 푸는 문제

도메인 코드는 "시세를 가져온다"만 알아야 하고, "yfinance가 `.KS` 접미사를 요구한다"는 사실은
몰라야 합니다. 어댑터 층은 그 경계입니다.

```text
app/adapters/
  factory.py          설정을 보고 어떤 구현을 쓸지 결정
  market/
    base.py           인터페이스(ABC) + 결과 dataclass    ← 도메인이 아는 것은 여기까지
    mock.py           결정적 가짜 구현
    yfinance.py       실제 외부 API 구현
    cache.py          Redis 캐시 데코레이터
  news/     base.py / mock.py / rss.py
  disclosure/ base.py / mock.py
  portfolio/  base.py / mock.py
  llm/      (07단계에서 별도로 다룸)
```

**한 도메인당 `base` / `mock` / `real` 삼각 구조**가 반복됩니다.

## market/base.py — 계약 정의

### 인터페이스가 7개로 쪼개져 있다

```python
class MarketDataProvider(ABC):     # 현재가·시세
class PriceSeriesProvider(ABC):    # OHLCV 시계열
class IndexQuoteProvider(ABC):     # 지수
class ExchangeRateProvider(ABC):   # 환율
class SymbolLookupProvider(ABC):   # 종목 검색
class ValuationProvider(ABC):      # 밸류에이션 지표
class EarningsProvider(ABC):       # 실적
```

`MarketProvider` 하나에 메서드 15개를 넣지 않고 **관심사별로 인터페이스를 나눴습니다.** 인터페이스
분리 원칙(ISP)의 적용이고, 실익이 분명합니다.

- 05단계의 `PriceSeriesService`는 `PriceSeriesProvider`만 받으므로 다른 메서드의 존재를 모릅니다.
- 테스트에서 가짜를 만들 때 필요한 메서드 1~2개만 구현하면 됩니다.
- 캐시가 필요한 것(시세·지수·환율)과 아닌 것(시계열·검색)을 **인터페이스 단위로 갈라** 감쌀 수
  있습니다.

### 필수 메서드와 선택 메서드

```python
class MarketDataProvider(ABC):
    @abstractmethod
    def get_quote(self, symbols: list[str]) -> list[QuoteResult]:
        """Return current market quotes for the given symbols."""

    def get_price_targets(self, symbols: list[str]) -> list[PriceTargetResult]:
        """Return price target consensus without requiring quote callers to fetch it."""
        return [PriceTargetResult(symbol=symbol.upper()) for symbol in symbols]

    def get_analyst_opinions(self, symbol: str, limit: int) -> list[AnalystOpinionResult]:
        return []
```

`@abstractmethod`가 붙은 것만 필수입니다. 붙지 않은 두 메서드는 **기본 구현이 있어 선택적**입니다.
기본값이 "빈 값"이라는 점이 설계 의도를 드러냅니다 — 목표주가나 애널리스트 의견을 제공하지 못하는
공급자가 있어도 호출부는 `None` 체크 없이 빈 리스트를 받습니다.

`@abstractmethod`가 붙은 메서드를 구현하지 않은 클래스는 **인스턴스화 시점에 `TypeError`** 가
납니다. 런타임 첫 호출이 아니라 객체를 만들 때 터지므로 실수가 빨리 드러납니다.

### 모든 메서드가 배치 인터페이스

```python
    def get_quote(self, symbols: list[str]) -> list[QuoteResult]:
    def get_quotes(self, symbols: list[str]) -> list[IndexQuoteResult]:
    def get_rates(self, pairs: list[str]) -> list[ExchangeRateResult]:
```

단건이 아니라 **리스트를 받고 리스트를 돌려줍니다.** 외부 API 왕복 비용이 크므로 인터페이스
수준에서 배치를 강제한 것입니다. 04단계에서 `WatchlistService`가 심볼 목록을 한 번에 넘긴 것,
05단계에서 DB 조회만 N+1로 남은 것의 배경이 여기 있습니다.

리스트를 돌려주므로 **입력 개수와 출력 개수가 다를 수 있습니다.** 실제로 yfinance 구현은 실패한
심볼을 건너뛰므로 3개를 요청해 2개가 올 수 있습니다. 호출부가 `results[0]`으로 첨자 접근하면
위험한 지점이며, `{q.symbol: q for q in ...}`처럼 심볼로 매핑하는 04단계의 방식이 안전합니다.

### 결과는 frozen dataclass

```python
@dataclass(frozen=True)
class QuoteResult:
    symbol: str
    name: str
    price: Decimal
    ...
    per: Decimal | None = None
```

Pydantic이 아니라 **표준 라이브러리 dataclass**입니다. 이 프로젝트의 타입 사용 구분이 여기서
명확해집니다.

| 계층 | 타입 | 이유 |
| --- | --- | --- |
| HTTP 경계 | Pydantic `BaseModel` | 검증·직렬화·OpenAPI가 필요 |
| 어댑터 결과 | `@dataclass(frozen=True)` | 내부 전달용. 검증 오버헤드 불필요 |
| DB | SQLAlchemy 모델 | 영속성 |

`frozen=True`는 불변이라 어댑터가 돌려준 값을 도메인이 실수로 수정할 수 없게 합니다. 필수 필드가
앞, 기본값 있는 선택 필드가 뒤에 오는 순서는 dataclass 문법상 강제입니다.

숫자는 전부 `Decimal`, 시각은 전부 `datetime`(aware)입니다. **문자열 → 타입 변환은 어댑터가
책임지고, 도메인은 이미 변환된 값을 받습니다.**

## factory.py — 설정 → 구현 선택

```python
def get_market_provider() -> MarketDataProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockMarketDataProvider()
    if settings.MARKET_PROVIDER == "yfinance":
        return CachedMarketDataProvider(YFinanceMarketDataProvider())
    raise NotImplementedError("market real provider 미구현")
```

1단계에서 본 `MARKET_PROVIDER: Literal["mock", "real", "yfinance"]`가 여기서 쓰입니다.

**반환 타입이 구체 클래스가 아니라 인터페이스(`MarketDataProvider`)** 인 것이 핵심입니다. 호출부는
`MockMarketDataProvider`나 `YFinanceMarketDataProvider`라는 이름을 알지 못하고, mypy도 인터페이스에
있는 메서드만 허용합니다.

`"real"`은 `Literal`에 있지만 구현이 없어 `NotImplementedError`가 납니다. **설정으로 허용된 값과
실제 구현된 값이 다른 상태**이며, 향후 다른 데이터 소스를 붙일 자리를 예약해 둔 것입니다. 다만
설정 검증은 통과하고 첫 호출에서 터지므로, 기동 시점 검증으로 옮기면 더 안전합니다.

### 캐시를 씌우는 위치

```python
    return CachedMarketDataProvider(YFinanceMarketDataProvider())   # 감쌈
    ...
    return YFinancePriceProvider()                                   # 안 감쌈
```

**데코레이터 패턴**입니다. `CachedMarketDataProvider`도 `MarketDataProvider`를 구현하므로 호출부는
캐시가 끼었는지 알 수 없습니다.

감싸는 대상과 아닌 대상이 갈립니다.

| 감쌈 | 감싸지 않음 |
| --- | --- |
| 시세(60초), 지수(60초), 환율(300초) | 시계열, 종목 검색, 밸류에이션, 실적 |

기준은 **호출 빈도 × 변동성**입니다. 시세는 여러 사용자가 같은 심볼을 계속 조회하고 1분 정도는
낡아도 무방합니다. 시계열은 05단계에서 본 대로 이미 DB에 저장되므로 DB가 캐시 역할을 합니다.
mock은 감싸지 않는데, 어차피 외부 호출이 없기 때문입니다.

### 매 호출마다 새 인스턴스

```python
    return MockMarketDataProvider()
```

싱글턴이 아니라 **호출할 때마다 새로 만듭니다.** 어댑터가 상태를 갖지 않기 때문에 가능한
선택이고, 테스트에서 설정을 바꾸면 즉시 반영된다는 장점이 있습니다.

예외가 하나 있습니다. `YFinancePriceProvider`는 `self.last_payload`라는 **상태를 갖습니다**(05단계에서
`getattr`로 꺼내 쓰던 그것). 매번 새 인스턴스라 이 방식이 동작하지만, 인스턴스를 재사용하는
코드가 생기면 이전 호출의 payload가 섞일 수 있는 구조입니다.

### FastAPI 의존성이 아니라 직접 호출

02단계의 `get_db`는 `Depends(get_db)`로 주입되는데, 어댑터 팩토리는 `get_market_provider()`처럼
service 안에서 직접 호출됩니다.

```python
        quotes = {q.symbol: q for q in get_market_provider().get_quote(symbols)}
```

의존성으로 만들면 엔드포인트 시그니처마다 파라미터가 늘어나고, 워커·스케줄러처럼 FastAPI 밖에서
도는 코드(08단계)에서는 `Depends`를 쓸 수 없습니다. **HTTP 안팎에서 같은 방식으로 쓰기 위한
선택**입니다.

대가는 테스트에서 교체하려면 `monkeypatch`로 모듈 속성을 바꿔야 한다는 점입니다. 일부 service는
생성자로 주입받는 형태(`WatchlistObservationsService(db, get_llm_gateway())`)를 쓰는데, 이쪽이
테스트하기 쉽습니다. 두 방식이 공존하고 있습니다.

## mock.py — 결정적 가짜

```python
_AS_OF = datetime(2026, 6, 19, 0, 0, tzinfo=timezone.utc)
_PRICE_SERIES_END_DATE = date(2026, 6, 25)
```

**시각이 고정 상수입니다.** `datetime.now()`를 쓰면 테스트가 실행 시점에 따라 다른 값을 얻어
스냅샷 비교가 불가능해집니다.

```python
        seed = _stable_seed(f"{normalized_symbol}:{normalized_market}")
        base_price = Decimal(seed % 50000 + 5000)
        ...
            drift = Decimal(((seed + index * 17) % 900) - 450) / Decimal("100")
```

`_stable_seed`는 `sha256`으로 심볼 문자열에서 정수를 만듭니다. `random`을 쓰지 않는 이유는
명확합니다 — **같은 심볼은 언제 어디서 호출해도 같은 가격 시계열**이 나와야 합니다. 파이썬의
`hash()`도 쓸 수 없는데, 프로세스마다 문자열 해시 시드가 달라지기 때문입니다(PYTHONHASHSEED).

`% 900 - 450`처럼 나머지 연산으로 범위를 만들고 `Decimal("100")`으로 나눠 소수점 둘째 자리까지의
변동을 만듭니다. `index`를 곱해 더하는 것은 바마다 다른 값을 얻기 위한 것이고, `17`·`13`·`5`
같은 소수를 쓰는 것은 패턴이 반복되지 않게 하려는 흔한 기법입니다.

```python
    def get_analyst_opinions(self, symbol: str, limit: int) -> list[AnalystOpinionResult]:
        if symbol.upper() != "AAPL":
            return []
        return _SAMPLE_ANALYST_OPINIONS[:limit]
```

**특정 심볼에만 데이터가 있습니다.** "데이터가 있는 경우"와 "없는 경우"를 둘 다 재현할 수 있어야
빈 상태 UI를 테스트할 수 있습니다. 의도적으로 만든 비대칭입니다.

mock의 `_RANGE_COUNTS`가 05단계 `PriceSeriesService`의 상수와 겹치는 점은 눈여겨볼 만합니다. 값이
어긋나면 조회 개수와 생성 개수가 맞지 않으므로, 한쪽에서 가져다 쓰는 편이 안전합니다.

## yfinance.py — 실제 구현이 흡수하는 지저분함

841줄로 어댑터 중 가장 큽니다. 그 대부분이 **외부 세계의 불규칙성을 흡수하는 코드**입니다.

### 심볼 표기 변환

```python
_MARKET_SUFFIXES = {"KOSPI": ".KS", "KOSDAQ": ".KQ", "NASDAQ": "", "NYSE": ""}
_YFINANCE_EXCHANGE_MARKETS = {
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ",
    "NYQ": "NYSE", "ASE": "NYSE", "PCX": "NYSE",
    "KSC": "KOSPI", "KQ": "KOSDAQ",
}
_INDEX_TICKERS = {"SPX": "^GSPC", "IXIC": "^IXIC", "KOSPI": "^KS11", "VIX": "^VIX"}
_EXCHANGE_RATE_TICKERS = {"USD/KRW": "KRW=X"}
```

**이 프로젝트의 어휘와 yfinance의 어휘를 잇는 사전들**입니다. 삼성전자는 우리 표기로
`("005930", "KOSPI")`, yfinance 표기로 `005930.KS`입니다. S&P 500은 `SPX` ↔ `^GSPC`입니다.

역방향 사전(`_YFINANCE_EXCHANGE_MARKETS`)이 더 큰 이유는 yfinance가 거래소를 `NMS`, `NGM`, `NCM`
처럼 세분화해 돌려주기 때문입니다. 우리 도메인은 `NASDAQ` 하나로 충분하므로 여러 값을 하나로
접습니다.

**이 사전들이 어댑터 안에만 있다는 점이 중요합니다.** 도메인 어디에도 `.KS`나 `^GSPC`가 등장하지
않습니다. 데이터 소스를 바꾸면 이 파일만 새로 쓰면 됩니다.

### 실패를 격리한다

```python
    def get_quote(self, symbols: list[str]) -> list[QuoteResult]:
        results: list[QuoteResult] = []
        for symbol in symbols:
            try:
                fast_info = yf.Ticker(to_yfinance_quote_ticker(normalized_symbol)).fast_info
                result = quote_result_from_fast_info(normalized_symbol, fast_info, as_of=datetime.now(UTC))
                if result is None:
                    raise ValueError("required quote value is missing")
            except Exception:
                logger.exception("Failed to collect market quote", extra={"symbol": normalized_symbol})
                continue
            results.append(result)
        return results
```

05단계 수집 파이프라인과 같은 원칙 — **심볼 단위로 예외를 격리**합니다. 한 종목이 상장폐지됐거나
yfinance가 그 종목만 실패해도 나머지는 정상 반환됩니다.

메서드마다 실패 시 처리가 다른 점이 설계 판단을 보여줍니다.

| 메서드 | 실패 시 | 이유 |
| --- | --- | --- |
| `get_quote` | `continue`로 **제외** | 가격 없는 시세는 의미 없음 |
| `get_price_targets` | 빈 `PriceTargetResult` **추가** | 부가 정보. 자리는 유지 |
| `get_analyst_opinions` | 빈 리스트 반환 | 전체가 부가 정보 |

`result is None`일 때 일부러 `raise ValueError`를 던져 `except` 블록으로 보내는 것도 기법입니다.
"값이 없음"과 "예외 발생"을 한 곳에서 처리하기 위한 것입니다.

### `except Exception`이 정당한 자리

이 파일에는 `except Exception`이 12곳 있습니다. 전역 지침의 "에러 처리는 시스템 경계에서만"에
비추면 **정확히 그 경계**입니다. yfinance는 내부적으로 HTTP 요청, HTML 파싱, pandas 연산을 하므로
어떤 예외가 나올지 열거할 수 없습니다.

중요한 것은 **여기서 잡고 로그를 남긴 뒤 빈 값으로 되돌린다**는 점입니다. 예외가 도메인까지
올라가지 않으므로, 05단계 `PriceSeriesService`의 502 변환은 그보다 더 심각한 경우(팩토리 자체
실패 등)를 위한 이중 방어가 됩니다.

### pandas 경계

```python
        frame = ticker.history(period=..., interval=interval, auto_adjust=adjusted)
        return _bars_from_frame(frame=frame, symbol=..., market=..., currency=..., interval=interval)
```

yfinance는 pandas `DataFrame`을 돌려줍니다. `_bars_from_frame`이 그것을 `list[PriceBarResult]`로
바꾸는 **경계 함수**입니다. `DataFrame`이 어댑터 밖으로 나가지 않으므로, 도메인과 테스트는 pandas를
몰라도 됩니다.

`import math`와 `float`이 이 파일에만 등장하는 것도 같은 이유입니다. pandas가 결측을 `NaN`(float)으로
표현하므로 `math.isnan` 검사가 필요하고, 그것을 `Decimal | None`으로 변환한 뒤에야 도메인으로
넘깁니다.

### `last_payload` — 원본 보관 통로

```python
class YFinancePriceProvider(PriceSeriesProvider):
    source = "yfinance"

    def __init__(self) -> None:
        self.last_payload: dict[str, Any] | None = None

    def get_daily_bars(self, ...) -> list[PriceBarResult]:
        ...
        self.last_payload = _payload_from_frame(frame=frame, ...)
        return _bars_from_frame(...)
```

05단계의 `raw_prices`가 원본을 보관하려면 변환 전 데이터가 필요한데, 반환 타입은
`list[PriceBarResult]`(이미 변환된 것)입니다. 그래서 **원본을 인스턴스 속성에 남겨** 호출부가
꺼내 가게 했습니다.

인터페이스에 없는 속성이라 05단계 호출부가 `getattr(provider, "last_payload", None)`로 더듬어야
합니다. 깔끔한 방법은 `get_daily_bars`가 `(bars, payload)` 튜플이나 payload를 포함한 결과 객체를
돌려주는 것입니다. 지원하지 않는 시장일 때 `{"skipped": "unsupported_market"}`를 넣어두는 것은
"왜 데이터가 없는지"를 원본 테이블에 남기려는 세심한 처리입니다.

## cache.py — Redis 캐시 데코레이터

```python
def fetch_json_cached(key: str, ttl_seconds: int, loader: Callable[[], Any]) -> Any:
    try:
        redis = get_redis_connection()
        cached = redis.get(key)
        if cached is not None:
            return _decode_json(json.loads(raw))
    except Exception:
        # Market data must remain available when Redis is unavailable or corrupt.
        logger.exception("Market cache read failed; loading from provider", extra={"key": key})
        return loader()

    value = loader()
    try:
        redis.setex(key, ttl_seconds, json.dumps(_encode_json(value), separators=(",", ":")))
    except Exception:
        # A cache write failure must not discard successfully loaded market data.
        logger.exception("Market cache write failed", extra={"key": key})
    return value
```

**캐시 실패가 기능 실패가 되지 않게** 하는 것이 이 함수의 전부입니다. 읽기 실패도, 쓰기 실패도
로그만 남기고 원래 값을 돌려줍니다. Redis가 죽어도 시세 조회는 계속 동작합니다.

`loader`를 콜러블로 받는 것이 핵심 설계입니다. 값을 먼저 계산해 넘기면 캐시가 있어도 외부 API를
호출하게 됩니다. 지연 평가라 **캐시 적중 시 `loader`가 아예 실행되지 않습니다.**

이 파일의 주석 두 줄은 프로젝트에서 드문 사례인데, 전역 지침의 "주석은 WHY가 명확하지 않을 때만"에
정확히 부합합니다. `except Exception: pass`에 가까운 코드는 의도가 안 보이므로 이유를 적어둔
것입니다.

### 캐시 키

```python
def _cache_key(kind: str, values: list[str]) -> str:
    normalized_values = sorted(value.upper() for value in values)
    return f"market:{kind}:{','.join(normalized_values)}"
```

`sorted`가 중요합니다. `["AAPL", "MSFT"]`와 `["MSFT", "AAPL"]`은 같은 요청이므로 같은 키여야
합니다. `market:` 접두사는 Redis를 워커 큐·LLM 캐시와 공유하므로 네임스페이스를 나누는 것입니다.

다만 **조합 단위 캐싱**이라는 한계가 있습니다. `[AAPL, MSFT]`를 캐시해 둬도 `[AAPL]` 요청은 캐시
미스입니다. 심볼별로 캐싱하고 미스인 것만 모아 조회하는 방식이 적중률은 높지만, 구현이
복잡해집니다. TTL이 60초로 짧아 감당 가능하다는 판단입니다.

### Decimal·datetime을 JSON에 담기

```python
_TYPE_KEY = "__market_cache_type__"

def _encode_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {_TYPE_KEY: "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {_TYPE_KEY: "datetime", "value": value.isoformat()}
    ...

def _decode_json(value: Any) -> Any:
    ...
    if value_type == "decimal":
        return Decimal(value["value"])
```

JSON에는 `Decimal`도 `datetime`도 없습니다. 그냥 `float`으로 바꾸면 **정밀도가 깨지고**(이 프로젝트가
`Decimal`을 고집한 이유가 무의미해집니다), `str`로 바꾸면 복원할 때 타입을 알 수 없습니다.

그래서 **타입 태그를 붙인 dict로 감싸는 자체 인코딩**을 만들었습니다. `__market_cache_type__`처럼
충돌 가능성이 낮은 키를 쓰는 것이 관례입니다. `_encode_json`/`_decode_json`이 재귀적으로 dict와
list를 순회하므로 중첩 구조도 처리됩니다.

```python
def _dataclasses_to_dicts(items: list[Any]) -> list[dict[str, Any]]:
    return [asdict(item) for item in items]

def _quote_results_from_dicts(payload: Any) -> list[QuoteResult]:
    return [QuoteResult(**cast(dict[str, Any], item)) for item in payload]
```

`dataclasses.asdict`로 풀고 `**`로 다시 조립합니다. `cast`는 런타임에 아무 일도 하지 않고 mypy에게만
"이건 dict다"라고 알려주는 표시입니다.

**결과 타입마다 `_xxx_results_from_dicts` 함수를 하나씩 만든 반복**이 있습니다. 제네릭으로 묶을 수
있지만, dataclass 타입을 런타임에 다루는 코드는 타입 안전성이 떨어져 명시적 반복을 택한 것으로
보입니다.

## news / disclosure / portfolio — 같은 골격, 더 단순

```python
class NewsAdapter(ABC):
    @abstractmethod
    def fetch(self, symbols: list[str]) -> list[NewsAdapterResult]:
        """Fetch news items matching the given symbols."""

    def fetch_query(self, query: str, market: str) -> list[NewsAdapterResult]:
        raise NotImplementedError("query-based news fetch is not implemented")
```

`fetch_query`가 **기본 구현이 `raise NotImplementedError`** 인 선택 메서드입니다. 시장 어댑터가
"빈 값"을 기본으로 준 것과 다릅니다. 뉴스 검색은 없으면 조용히 넘어갈 수 없는 기능이므로,
지원하지 않는 어댑터에 호출하면 명확히 터지게 한 것입니다. **선택 메서드의 기본값을 "빈 값"으로
할지 "예외"로 할지가 기능의 성격에 따라 갈립니다.**

```python
@dataclass(frozen=True)
class NewsAdapterResult:
    title: str
    url: str
    body: str | None
    source: str
    published_at: datetime | None
    payload: dict[str, Any] | None
```

`payload` 필드가 있는 것이 시장 어댑터와 다른 점입니다. 05단계에서 본 "원본 보존" 요구를
`last_payload`라는 사이드 채널이 아니라 **결과 객체에 정식 필드로** 넣었습니다. 이쪽이 더 나은
설계이며, `DisclosureResult`도 같은 형태입니다.

`disclosure`와 `portfolio`는 mock만 있고 실제 구현이 없습니다. `factory`가 `real`을 요구하면
`NotImplementedError`를 냅니다 — **인터페이스를 먼저 정의하고 구현을 나중에 채우는** 진행 방식이
드러나는 부분입니다.

## 전체 흐름

```text
[설정]  MARKET_PROVIDER=yfinance
           ↓
[팩토리] get_market_provider()
           ↓
[캐시]   CachedMarketDataProvider          ← Redis 조회. 있으면 여기서 반환
           ↓ (미스)
[실구현] YFinanceMarketDataProvider        ← 심볼 변환 → yfinance 호출 → 예외 격리
           ↓
[변환]   DataFrame/fast_info → QuoteResult (frozen dataclass, Decimal·datetime)
           ↓
[도메인] AssetService / WatchlistService   ← 인터페이스 타입만 안다
```

## 이 단계에서 확인한 프로젝트 규칙

1. 외부 연동은 `base.py`(ABC + frozen dataclass) / `mock.py` / `<real>.py` 삼각 구조로 만든다.
2. 인터페이스는 관심사별로 잘게 나눈다. 한 클래스에 무관한 메서드를 모으지 않는다.
3. 어댑터 메서드는 배치 인터페이스(리스트 입력, 리스트 출력)로 설계한다.
4. 어댑터 결과는 Pydantic이 아니라 `@dataclass(frozen=True)`, 숫자는 `Decimal`, 시각은 aware
   `datetime`.
5. 실제 구현은 항목 단위로 `except Exception` + 로그 + 건너뛰기로 실패를 격리한다. 외부 라이브러리
   타입(pandas 등)은 어댑터 밖으로 내보내지 않는다.
6. 캐시는 데코레이터로 씌우고, 캐시 실패는 기능 실패가 되지 않게 한다.
7. mock은 `random`이나 `now()`를 쓰지 않고 해시 시드와 고정 시각으로 결정적으로 만든다.
8. 선택 메서드의 기본 구현은 부가 정보면 빈 값, 필수 기능이면 `NotImplementedError`.

## 알아둘 만한 개선 지점

- `last_payload` 사이드 채널은 `NewsAdapterResult.payload`처럼 결과 객체 필드로 옮기는 편이 안전하다.
- `MARKET_PROVIDER="real"`은 설정 검증을 통과하지만 첫 호출에서 터진다.
- 캐시 키가 심볼 조합 단위라 부분 집합 요청은 항상 미스다.
- mock의 `_RANGE_COUNTS`가 `PriceSeriesService`의 상수와 중복되어 어긋날 수 있다.

## 다음 단계로 이어지는 질문

- `LLMGateway`가 다른 어댑터와 달리 캐시·예산·에스컬레이션을 한 객체에 모은 이유는? (07단계)
- 프롬프트는 어디에 정의되고 응답 JSON은 어떻게 검증되는가? (07단계)
- `get_redis_connection()`은 어디에 정의되어 있고 워커와 무엇을 공유하는가? (08단계)
