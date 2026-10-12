# 05. 조회와 수집 슬라이스 — assets, prices, raw_prices

대상 파일: `app/domains/assets/*`, `app/domains/prices/*`, `app/domains/raw_prices/*`,
`app/api/v1/endpoints/assets.py`, `app/api/v1/endpoints/prices.py`

04단계가 "사용자가 만든 데이터"를 다뤘다면 여기는 **외부에서 들어오는 데이터**를 다룹니다. 그
차이가 도메인 구조를 바꿉니다.

## 세 도메인의 역할 분담

```text
assets       종목 마스터. 사용자가 등록한 관심 종목의 식별 정보
raw_prices   외부에서 받은 원본 응답을 그대로 보관 (감사·재처리용)
prices       정규화·검증을 거친 OHLCV 바 + 조회 API
```

`raw_prices`와 `prices`가 나뉜 것이 핵심 설계입니다. **원본 보존과 가공 결과를 분리**하면, 파싱
로직에 버그가 있어도 원본에서 다시 만들 수 있고 "이 값이 왜 이런가"를 추적할 수 있습니다.

`prices` 도메인의 파일 구성이 04단계와 다릅니다.

```text
model.py             StockPriceBar 테이블
schema.py            응답 스키마
repository.py        조회·upsert
service.py           조회 API (PriceSeriesService)
ingestion_service.py 수집 파이프라인 (PriceIngestionService)
normalizer.py        표기 정규화
validator.py         품질 검증
universe.py          "무엇을 수집할지" 결정
```

**조회 service와 수집 service가 분리**되어 있고, 수집 쪽에만 `normalizer` / `validator` /
`universe`가 붙습니다. 외부 데이터는 신뢰할 수 없다는 전제가 파일 구조에 드러난 것입니다.

## assets — 외부 검증을 거치는 등록

### 모델

```python
class Asset(Base, TimestampMixin):
    __table_args__ = (UniqueConstraint("symbol", "market", name="uq_assets_symbol_market"),)

    symbol: Mapped[str] = mapped_column(String(20))
    market: Mapped[str] = mapped_column(String(20))
    ...
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
```

유니크 키가 `symbol` 단독이 아니라 **`(symbol, market)` 복합**입니다. 같은 티커가 시장마다 다른
회사일 수 있기 때문입니다. 이 복합 키가 코드 전반에 파급되어, 가격·시세·수집 대상이 모두
`(symbol, market)` 쌍으로 다뤄집니다.

`is_active`는 **소프트 삭제** 플래그입니다. 종목 행을 실제로 지우면 이를 참조하는 관심목록 항목,
가격 바, 시그널이 모두 깨지므로 비활성 표시만 합니다.

### repository — 04단계에 없던 배치 조회

```python
    def list_by_ids(self, asset_ids: list[int]) -> list[Asset]:
        if not asset_ids:
            return []
        stmt = select(Asset).where(Asset.id.in_(asset_ids)).order_by(Asset.id)
        return list(self.db.scalars(stmt).all())
```

**04단계에서 지적한 N+1의 해법이 이미 여기 있습니다.** `WatchlistService.list_items_expanded`가
`get_by_id`를 루프로 돌리는 대신 이 메서드를 쓰면 쿼리가 N번에서 1번으로 줄어듭니다. 도구는
있는데 호출부가 안 쓰는 상태입니다.

빈 리스트를 먼저 걸러내는 것도 필요한 방어입니다. `IN ()`는 SQL 문법 오류이거나 항상 거짓이 되어
DB마다 동작이 다릅니다.

```python
    def list_all(self, is_active=None, symbol=None, offset=0, limit=None) -> list[Asset]:
        stmt = select(Asset).order_by(Asset.id)
        if is_active is not None:
            stmt = stmt.where(Asset.is_active == is_active)
        if symbol is not None:
            stmt = stmt.where(Asset.symbol == symbol)
```

**조건부 쿼리 조립**입니다. SQLAlchemy의 `select()` 객체는 불변이라 `.where()`가 새 객체를
돌려주고, 그래서 이렇게 단계적으로 쌓을 수 있습니다. 필터가 `None`이면 조건을 붙이지 않으므로
"전체 조회"와 "필터 조회"를 한 메서드로 처리합니다.

`count_all`이 같은 조건을 **다시 씁니다.** 목록과 카운트의 조건이 어긋나면 페이지네이션 총계가
틀리므로, 조건을 추가할 때 두 메서드를 함께 고쳐야 하는 구조적 취약점입니다.

### service — 외부 시장 데이터로 존재를 검증

```python
    def register(self, data: AssetCreate) -> AssetResponse:
        normalized_symbol = data.symbol.strip().upper()
        normalized_market = data.market.strip().upper()
        if self.repo.get_by_symbol_market(normalized_symbol, normalized_market):
            raise AppException(400, "이미 등록된 종목입니다.", ErrorCode.ASSET_DUPLICATE)
        lookup_item = self._find_exact_market_symbol(normalized_symbol, normalized_market)
        if lookup_item is None:
            raise AppException(422, "시장 데이터에서 확인되지 않은 종목입니다.",
                               ErrorCode.ASSET_NOT_IN_MARKET)
        try:
            asset = self.repo.create(symbol=lookup_item.symbol, name=lookup_item.name, ...)
        except IntegrityError as exc:
            raise AppException(400, ..., ErrorCode.ASSET_DUPLICATE) from exc
```

04단계의 중복 방어 2겹 패턴이 그대로 반복되고, 그 사이에 **외부 검증 단계**가 추가됐습니다.

`_find_exact_market_symbol`은 시장 데이터 공급자에 검색을 요청해 **정확히 일치하는 심볼이 있을
때만** 통과시킵니다. 사용자가 오타를 내거나 존재하지 않는 티커를 넣으면 등록 자체가 막힙니다.

주목할 점은 **`repo.create`에 넘기는 값이 사용자 입력이 아니라 `lookup_item`의 값**이라는 것입니다.
이름·시장·섹터를 외부 데이터에서 가져오므로, 사용자가 "AAPL / 애플전자"라고 보내도 실제 저장되는
이름은 시장 데이터의 정식 명칭입니다. **신뢰 경계에서 데이터를 갈아끼우는** 처리입니다.

422를 쓴 것도 의도적입니다. 400(잘못된 요청)이 아니라 422(형식은 맞지만 처리할 수 없는 내용)로
"입력 형식이 아니라 내용이 현실과 맞지 않는다"를 구분합니다.

```python
    def lookup(self, query: str, market: str | None = None) -> AssetLookupResponse:
        for result in get_symbol_lookup_provider().search(query, normalized_market):
            registered = self.repo.get_by_symbol_market(result.symbol, result.market) is not None
```

검색 결과마다 "이미 등록했는지"를 DB에서 확인합니다. 결과가 20개면 쿼리 20번 — 여기도 N+1입니다.
`(symbol, market)` 쌍을 모아 한 번에 조회하는 메서드가 없어서 생긴 형태입니다.

## prices 조회 경로 — `GET /api/v1/stocks/{symbol}/prices`

### 엔드포인트

```python
def get_stock_price_series(
    symbol: str,
    market: Literal["KOSPI", "KOSDAQ", "NASDAQ", "NYSE"],
    price_range: Annotated[str, Query(alias="range")] = "3M",
    interval: str | None = None,
    adjusted: bool = True,
    db: Session = Depends(get_db),
)
```

인증 의존성이 없습니다. **시세는 공개 데이터**라는 판단입니다. 04단계의 모든 엔드포인트가
`current_user`를 요구했던 것과 대비됩니다.

`market`은 기본값이 없는 `Literal`이므로 **필수 쿼리 파라미터**가 됩니다. 04단계의
`Query(alias="range")`가 여기서도 쓰이는데, 이유는 같습니다(`range`가 파이썬 내장 함수).

`price_range`가 `Literal`이 아니라 `str`인 점은 일관성이 떨어지는 지점입니다. 그래서 검증이
FastAPI가 아니라 service의 `_validate_range`로 내려가고, 잘못된 값의 응답이 422가 아니라 400
(`INVALID_PRICE_RANGE`)이 됩니다.

### service — 읽기 요청이 쓰기를 유발한다

```python
_RANGE_COUNTS = {"1D": 78, "1W": 65, "1M": 22, "3M": 66, "6M": 132, "1Y": 252, "5Y": 260}
_RANGE_INTERVALS = {"1D": "5m", "1W": "30m", "1M": "1d", "3M": "1d", ...}
```

범위 → 개수·간격 매핑이 모듈 상수입니다. `1Y: 252`는 **미국 시장의 연간 거래일 수**라는 도메인
지식이 숫자로 굳어진 것이고, `1M: 22`도 월 거래일 수입니다. 달력 날짜가 아니라 거래일 기준으로
세는 것이 시세 도메인의 관행입니다.

```python
    def get_series(self, symbol, market, range_value="3M", interval=None, adjusted=True):
        ...
        provider = get_price_series_provider()
        generated_bars = provider.get_daily_bars(...)      # ① 외부에서 가져오고
        ...
        self.repo.upsert_many(generated_bars)              # ② DB에 쓰고
        bars = self.repo.list_recent(...)                  # ③ DB에서 다시 읽는다
        return self._to_response(...)
```

**GET 요청인데 DB에 쓰고 있습니다.** read-through 캐시 형태입니다. 의도는 "조회할 때마다 최신
데이터를 확보하고 저장해 두자"이지만, 대가가 큽니다.

- 매 조회가 외부 API를 호출하므로 응답이 느리고 rate limit에 노출됩니다.
- GET이 부작용을 갖게 되어 HTTP 의미론상 멱등하지 않습니다.
- 인증이 없는 엔드포인트라 외부에서 반복 호출하면 그대로 외부 API 비용이 됩니다.

②를 거쳐 ③으로 다시 읽는 이유는 있습니다. 세 가지입니다.

- **타입이 다릅니다.** ①은 어댑터의 `PriceBarResult`, ③은 ORM 모델 `StockPriceBar`입니다.
  `_to_response`가 `bar.updated_at`을 쓰는데 이 값은 DB가 채우므로 ② 이전에는 존재하지 않습니다.
- **이전에 모아둔 바와 합쳐집니다.** 외부 API는 이번 호출분만 주지만 DB에는 배치가 쌓아둔 것이
  있습니다. `upsert_bars`가 유니크 키(symbol·market·interval·timestamp)로 갱신·추가하므로
  ③에서는 합쳐진 전체가 나옵니다.
- **정렬·개수 제한이 SQL에 있습니다.** `list_recent`의 `order_by(...).limit(count)`가 응답 크기를
  결정합니다.

### 조회 경로가 수집 파이프라인을 우회한다

이 경로는 08단계에서 볼 **스케줄 수집**과 중복됩니다. 그런데 단순 중복이 아니라, 같은 테이블에
품질 보증이 다른 두 경로가 쓰고 있습니다.

```text
경로 A — 스케줄 수집 (worker/jobs/prices.py → PriceIngestionService)
  provider.get_daily_bars()
    → raw_price_service.save_raw()      원본 payload 보존
    → normalizer.canonicalize_*()       심볼·시장 정규화
    → validator.validate_bars()         이상치 제거 (dropped_count 집계)
    → price_repo.upsert_bars(valid_bars 만)
    → JobRunService 로 실행 이력 기록

경로 B — GET /{symbol}/prices (PriceSeriesService)
  provider.get_daily_bars()
    → price_repo.upsert_many(전부)      정규화·검증·원본 보존 없음
```

경로 A는 `prices/ingestion_service.py:57-80`에서 네 단계를 거칩니다. 경로 B는
`prices/service.py:84`에서 외부 응답을 그대로 넘깁니다. 결과적으로 **조회 요청 하나가 배치가
걸러낸 이상치를 다시 테이블에 넣을 수 있고**, `raw_price`에 원본이 남지 않아 값의 출처 추적도
끊깁니다.

`price_collection` 스케줄은 `10 22 * * 1-5`(평일 22:10) 하루 한 번인 반면, 조회는 인증 없이
(`prices.py:20-26`에 `get_current_user` 없음) 무제한으로 외부 API를 호출합니다.

개선 방향은 세 가지이고, 계약 변경 여부가 갈립니다.

| 안 | 내용 | 대가 |
| --- | --- | --- |
| 1 | 조회 경로에서 쓰기 제거, `list_recent`만 | 미수집 종목 첫 조회가 404로 바뀜 |
| 2 | `get_latest_close_date()`로 신선도 판단, 최신이면 외부 호출 생략 | 계약 유지. 검증 우회는 남음 |
| 3 | 쓰기가 필요하면 `PriceIngestionService` 경유 | 조회 지연 증가. 1·2와 조합 가능 |

결정이 필요해 이슈로 분리했습니다.

### 외부 실패를 502로 변환

```python
        try:
            provider = get_price_series_provider()
            ...
        except Exception as exc:
            raise AppException(502, "시세 제공자에서 가격 데이터를 가져오지 못했습니다.",
                               ErrorCode.MARKET_DATA_PROVIDER_ERROR) from exc
```

**시스템 경계에서만 예외를 처리한다**는 전역 원칙의 실제 사례입니다. 외부 호출은 통제 밖이므로
`except Exception`으로 넓게 잡고, 502(Bad Gateway — 상류 서버 문제)로 변환합니다. 이렇게 하지
않으면 1단계에서 본 미처리 500 경로로 빠져 CORS 헤더 없는 응답이 나갑니다.

DB 저장 실패는 `SQLAlchemyError`로 **좁게** 잡습니다. 통제 가능한 영역이라 예상되는 예외만
처리하는 것이 맞습니다.

### 응답 변환에서의 정밀도 처리

```python
def _decimal_to_wire(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
```

`Numeric(20, 4)` 컬럼은 `70000.0000`처럼 읽힙니다. `format(value, "f")`는 지수 표기(`7E+4`)를 막고,
`rstrip`으로 꼬리 0을 떼어 `70000`으로 만듭니다. `.rstrip("0")` 다음에 `.rstrip(".")`을 또 부르는
이유는 `70000.0000` → `70000.` → `70000` 두 단계가 필요하기 때문입니다.

04단계에서 본 "숫자를 문자열로 내보낸다"는 규칙이 여기서 구현됩니다. JSON 숫자로 보내면
JavaScript가 배정도 부동소수점으로 받아 정밀도가 깨집니다.

```python
            date=(bar.timestamp.date().isoformat() if interval in {"1d", "1wk"}
                  else bar.timestamp.isoformat()),
```

일봉·주봉은 `"2026-07-31"`, 분봉은 `"2026-07-31T09:30:00+00:00"`로 내보냅니다. 같은 필드가 간격에
따라 형식이 달라지므로, 프런트엔드가 이 규칙을 알고 있어야 하는 암묵적 계약입니다.

### repository — upsert의 실제 구현

```python
    def upsert_bars(self, bars: list[PriceBarResult]) -> int:
        for bar in bars:
            existing = self.get_by_unique_key(symbol=..., market=..., interval=..., timestamp=...)
            if existing is None:
                self.db.add(StockPriceBar(...))
                continue
            existing.open_price = bar.open_price
            ...
        self.db.commit()
        return len(bars)
```

**바 하나마다 SELECT를 한 번씩 던집니다.** 252개 바를 수집하면 SELECT 252번 + INSERT/UPDATE입니다.
PostgreSQL의 `INSERT ... ON CONFLICT DO UPDATE`(SQLAlchemy의 `postgresql.insert(...).on_conflict_do_update`)
를 쓰면 한 번에 끝나는 작업입니다. 이 프로젝트에서 가장 눈에 띄는 성능 개선 여지입니다.

반면 잘 되어 있는 부분도 있습니다. 루프 전체가 끝난 뒤 **한 번만 `commit()`** 하므로, 252개 바가
하나의 트랜잭션으로 처리됩니다. 03단계에서 말한 "repository가 커밋한다"의 한계를 이 메서드
안에서는 잘 다루고 있습니다.

`existing`의 필드를 직접 대입하면 SQLAlchemy의 **변경 추적(dirty tracking)** 이 자동으로 UPDATE
문을 만듭니다. 명시적인 `db.update()` 호출이 필요 없는 것이 ORM의 이점입니다.

```python
    def list_recent(self, symbol, market, interval, limit) -> list[StockPriceBar]:
        stmt = (select(StockPriceBar).where(...)
                .order_by(StockPriceBar.timestamp.desc())
                .limit(limit))
        return list(reversed(self.db.scalars(stmt).all()))
```

**내림차순으로 최신 N개를 뽑고 파이썬에서 뒤집습니다.** 차트는 과거 → 현재 순서로 그려야 하는데,
"최신 N개"를 SQL로 얻으려면 내림차순 정렬이 필요하기 때문입니다. `ORDER BY timestamp ASC LIMIT N`은
가장 오래된 N개를 주므로 틀립니다.

```python
        return [(timestamp.date(), close_price)
                for timestamp, close_price in self.db.execute(stmt).all()]
```

`get_daily_closes`는 `db.scalars`가 아니라 **`db.execute`** 를 씁니다. `select(A, B)`처럼 여러
컬럼을 뽑을 때는 행이 튜플로 오므로 `execute`가 맞습니다. `scalars`는 첫 컬럼만 꺼냅니다. 전체
ORM 객체가 필요 없을 때 **필요한 컬럼만 select하는 것**이 메모리와 속도에 유리합니다.

## 수집 경로 — 3단 파이프라인

`PriceIngestionService.collect_and_save`가 전체를 조립합니다.

```text
universe.resolve()          무엇을 수집할지 결정
  ↓ [(symbol, market), ...]
provider.get_daily_bars()   외부에서 가져오기
  ↓ list[PriceBarResult]
raw_price_service.save_raw()  원본 보관 (해시 중복 제거)
validator.validate_bars()     품질 검증 → 불량 바 제거
price_repo.upsert_bars()      정규화된 바 저장
  ↓
IngestionResult              집계 결과
```

### universe.py — 수집 대상 결정

```python
    def resolve(self) -> list[tuple[str, str]]:
        return self._deduplicate([*self.resolve_assets(), *self._benchmark_targets()])

    def _watchlist_targets(self) -> list[tuple[str, str]]:
        stmt = (select(Asset.symbol, Asset.market)
                .join(WatchlistItem, WatchlistItem.asset_id == Asset.id)
                .where(Asset.is_active.is_(True))
                .order_by(Asset.symbol, Asset.market))
```

**"모든 종목"이 아니라 "누군가 실제로 보고 있는 종목"만 수집합니다.** 관심목록에 담겼거나
포트폴리오에 보유 중인 종목, 그리고 비교용 섹터 ETF가 대상입니다. 외부 API 호출량이 사용자
활동에 비례하게 만드는 설계입니다.

`Asset.is_active.is_(True)`에서 `== True`가 아니라 `.is_(True)`를 쓴 것은 SQLAlchemy 관례입니다.
`== True`도 동작하지만 린터가 경고하고, `.is_()`가 SQL의 `IS TRUE`로 정확히 번역됩니다.

```python
    @staticmethod
    def _deduplicate(all_targets: list[tuple[str, str]]) -> list[tuple[str, str]]:
        targets: dict[tuple[str, str], None] = {}
        for symbol, market in all_targets:
            targets[(symbol.upper(), market.upper())] = None
        return list(targets)
```

`set`이 아니라 **값이 `None`인 dict**로 중복을 제거합니다. 파이썬 3.7+의 dict는 삽입 순서를
보존하므로 **중복 제거와 순서 유지를 동시에** 달성합니다. `set`을 쓰면 순서가 깨져 수집 순서가
매번 달라지고 로그를 비교하기 어려워집니다.

### raw_prices — 해시로 중복 저장 방지

```python
    def save_raw(self, symbol, market, payload, interval="1d", source="yfinance") -> RawPrice | None:
        payload_hash = hash_payload(payload)
        if self.repo.exists_by_hash(payload_hash):
            return None
        return self.repo.save(RawPriceCreate(..., payload_hash=payload_hash, ...))


def hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return sha256(encoded).hexdigest()
```

원본 응답 전체를 JSON 컬럼에 넣되, **내용 해시가 같으면 저장하지 않습니다.** 장 마감 후 같은
데이터를 여러 번 수집해도 원본 테이블이 부풀지 않습니다.

`json.dumps`의 세 옵션이 모두 해시 안정성을 위한 것입니다.

- `sort_keys=True` — 키 순서가 달라도 같은 해시가 나오게
- `separators=(",", ":")` — 공백 차이 제거
- `default=str` — `datetime`·`Decimal`처럼 JSON이 모르는 타입을 문자열로

`save_raw`가 저장을 건너뛰면 `None`을 돌려주고, 호출부는 이것으로 `raw_saved_count`와
`raw_skipped_count`를 구분합니다. **불린 대신 객체/None을 돌려주어 정보량을 늘린** 형태입니다.

```python
    processing_status: Mapped[str] = mapped_column(
        String(20), server_default=ProcessingStatus.FETCHED.value, nullable=False, index=True)
```

원본 행이 상태를 갖습니다. "가져왔지만 아직 처리 안 됨"을 표시해 두면 나중에 재처리 대상을
찾을 수 있습니다. `index=True`는 상태로 필터링하는 쿼리를 전제한 것입니다.

### validator.py — 외부 데이터 품질 검증

```python
_OUTLIER_THRESHOLD = Decimal("0.5")
_EXPECTED_CURRENCY_BY_MARKET = {"KOSPI": "KRW", "KOSDAQ": "KRW", "NASDAQ": "USD", "NYSE": "USD"}
```

```python
        for bar in sorted(bars, key=lambda item: item.timestamp):
            if _has_missing_required_price(bar):
                dropped_count += 1
                reasons.append(ValidationErrorReason.MISSING_REQUIRED_FIELD)
                continue
            if self.normalizer.normalize_timestamp(bar.timestamp).date() > today:
                ...
```

검증 규칙이 **외부 데이터가 실제로 어떻게 망가지는지**를 보여줍니다.

- OHLC 결측 → 버림
- 미래 날짜 → 버림 (타임존 오해로 흔히 발생)
- 전일 대비 50% 이상 변동 → 이상치 경고 (액면분할·데이터 오류)
- 시장과 통화 불일치 → 경고 (KOSPI 종목에 USD가 오는 경우)

**버리는 것(dropped)과 경고만 하는 것(warning)을 구분**한 점이 중요합니다. OHLC가 없으면 계산이
불가능하니 버리고, 급등락은 실제일 수도 있으니 기록만 남깁니다. 자동화가 데이터를 임의로
버리지 않게 하는 균형입니다.

`sorted(bars, key=...)`로 시간순 정렬 후 순회하는 이유는 **전일 종가 대비 변동률**을 계산하려면
순서가 보장돼야 하기 때문입니다.

### 결과 집계 — frozen dataclass 누적

```python
@dataclass(frozen=True)
class IngestionResult:
    target_count: int = 0
    success_count: int = 0
    ...

            return IngestionResult(
                target_count=result.target_count,
                success_count=result.success_count + 1,
                ...
            )
```

**불변 객체를 매번 새로 만들어 누적**합니다. `result.success_count += 1`로 변경하는 것보다
장황하지만, 중간 상태가 없어 추적이 쉽습니다. 대신 필드를 추가할 때마다 두 군데(성공 분기·실패
분기)의 생성자를 모두 고쳐야 하고, 빠뜨리면 값이 조용히 0으로 리셋됩니다. `dataclasses.replace`를
쓰면 이 위험이 사라집니다.

### 한 종목 실패가 전체를 멈추지 않는다

```python
        for symbol, market in targets:
            result = self._collect_target(provider, symbol, market, range_value, result)

    def _collect_target(self, ...):
        try:
            ...
        except Exception:
            logger.exception("Failed to collect price target",
                             extra={"symbol": normalized_symbol, "market": normalized_market})
            return IngestionResult(..., failure_count=result.failure_count + 1, ...)
```

**종목 단위로 예외를 격리**합니다. 100종목 수집 중 3번째가 실패해도 나머지 97개는 수집됩니다.
배치 작업의 기본 원칙이며, 실패는 `failure_count`로 집계되어 08단계의 `JobRun` 기록에 남습니다.

`logger.exception`은 `logger.error(..., exc_info=True)`와 같아 스택 트레이스를 함께 남깁니다.
`extra={"symbol": ...}`는 1단계의 `JsonFormatter` 화이트리스트에 없는 키라 JSON 출력에는 나오지
않습니다 — 화이트리스트에 추가하면 살아나는 부분입니다.

### 프로바이더에서 값을 꺼내는 방식

```python
def _provider_payload(provider, symbol, market, bars) -> dict[str, Any]:
    payload = getattr(provider, "last_payload", None)
    if isinstance(payload, dict):
        return payload
    return {...}   # 없으면 bars에서 재구성
```

`getattr(provider, "last_payload", None)`로 **선택적 속성**을 조회합니다. 실제 공급자는 원본 응답을
`last_payload`에 보관하고, mock은 그런 속성이 없으므로 바에서 payload를 재구성합니다.

인터페이스(`PriceSeriesProvider`)에 없는 속성을 `getattr`로 더듬는 것은 **덕 타이핑**이고, 타입
체커가 검증할 수 없습니다. 06단계에서 볼 어댑터 인터페이스에 이 속성을 정식으로 넣는 것이 더
안전한 방향입니다.

## 이 단계에서 확인한 프로젝트 규칙

1. 외부에서 오는 데이터는 **원본(raw) 테이블과 가공 테이블을 분리**한다. 원본은 내용 해시로 중복을
   막는다.
2. 수집 파이프라인은 `universe(대상 결정) → provider(수집) → raw 저장 → validator(검증) →
   repository(저장)` 순서를 따른다.
3. 배치는 대상 단위로 예외를 격리하고, 성공·실패·경고를 집계 객체로 반환한다.
4. 외부 호출 실패는 `except Exception` + 502(`MARKET_DATA_PROVIDER_ERROR`)로 변환한다. DB 실패는
   `SQLAlchemyError`로 좁게 잡는다.
5. 종목 식별자는 항상 `(symbol, market)` 쌍이고 대문자로 정규화한다.
6. 종목 등록은 외부 시장 데이터로 존재를 검증하고, **저장값은 사용자 입력이 아니라 외부 조회
   결과**를 쓴다.
7. 가격은 `Numeric(20, 4)`로 저장하고 응답에서는 꼬리 0을 제거한 문자열로 내보낸다.
8. 삭제는 `is_active=False` 소프트 삭제로 처리한다.

## 알아둘 만한 개선 지점

- `PriceSeriesService.get_series`가 GET 요청에서 외부 API를 호출하고 DB에 쓴다. 인증도 없어
  외부 호출량을 통제할 수 없다.
- `upsert_bars`가 바 하나마다 SELECT를 던진다. `ON CONFLICT DO UPDATE`로 한 번에 처리 가능하다.
- `AssetService.lookup`이 검색 결과마다 등록 여부를 단건 조회한다(N+1).
- `AssetRepository.list_all`과 `count_all`이 필터 조건을 각자 복제하고 있어 어긋날 수 있다.
- `_provider_payload`의 `getattr` 덕 타이핑은 어댑터 인터페이스에 정식 편입하는 것이 안전하다.

## 다음 단계로 이어지는 질문

- `get_market_provider()`와 `get_price_series_provider()`는 어떻게 mock과 real을 고르는가? (06단계)
- `PriceBarResult`, `SymbolLookupResult`는 어디에 정의된 무엇인가? (06단계)
- 외부 API 응답을 캐시하는 계층이 있는가? (06단계)
