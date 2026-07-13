# Design — Issue 230: yfinance 실데이터 전환 — quote/index/fx provider와 시세 캐시

`MARKET_PROVIDER`는 market 계열 전역 스위치인데 yfinance 구현이 가격
시계열·lookup·밸류에이션·실적뿐이라, `yfinance` 전환 시 시세·지수·환율
경로가 factory `NotImplementedError`로 깨진다. 남은 3개 provider를
구현하고 Redis TTL 캐시를 얹어 전역 전환을 성립시킨다.
**API 계약·FE 변경 없음. 마이그레이션 없음.**

## Scope Decision

- **QuoteResult 채움 범위**: 필수 필드(price · previous_close ·
  change · change_percent · currency · as_of · name)와 `fast_info`가
  제공하는 optional(market_cap · fifty_two_week_low/high)만 채운다.
  per · peg · next_earnings_date · target_price ·
  target_upside_percent는 **null 유지** — `Ticker.info` 전체 조회는
  심볼당 지연이 크고, 해당 값들은 밸류에이션 스냅샷(#279)이 이미
  담당한다.
- **quote의 시장 판별 휴리스틱**: `MarketDataProvider.get_quote`
  시그니처가 `symbols: list[str]`뿐이라 market 정보가 없다 (호출처
  9곳 변경은 스코프 초과). 어댑터 내부에서 **전부 숫자인 심볼(KRX
  6자리) → `.KS` 접미사, 그 외 → 그대로** 휴리스틱으로 yfinance
  티커를 만든다 (WHY 주석 필수). 시그니처 확장은 후속 이슈로 남긴다.
- **실패 심볼은 건너뛴다**: 심볼 단위 조회 실패는 로그 후 스킵하고
  나머지를 반환한다 (mock은 항상 전량 반환하지만 소비 서비스들은
  dict 매칭이라 부분 결과를 허용). provider 전체 실패 예외는 기존
  서비스 경계에서 `MARKET_DATA_PROVIDER_ERROR`로 변환된다 — 변환
  로직 변경 없음.
- **Redis TTL 캐시는 yfinance 분기에만** 적용한다 (mock은 비캐시).
  TTL: quote 60초 · index 60초 · fx 300초 (이슈 예시값, 코드 상수).
  요청마다 yfinance 실호출을 피하는 rate limit 대응으로 사실상
  필수다. Redis 장애 시 캐시를 건너뛰고 원 provider를 직접 호출한다
  (캐시가 가용성을 낮추면 안 됨).

## 1. yfinance providers — `app/adapters/market/yfinance.py`

- `YFinanceMarketDataProvider(MarketDataProvider)` —
  `get_quote(symbols)`: 심볼별 `Ticker.fast_info`에서
  last_price · previous_close · currency 추출, change/
  change_percent 파생(quantize 0.01), name은 fast_info에 없으므로
  심볼 그대로(소비처는 자체 asset name을 우선 사용). as_of는 조회
  시각(UTC). 값 변환·파생은 순수 함수로 분리해 그 부분만 테스트.
- `YFinanceIndexQuoteProvider(IndexQuoteProvider)` —
  내부 심볼 ↔ yfinance 심볼 매핑 상수:
  `SPX→^GSPC, IXIC→^IXIC, KOSPI→^KS11, VIX→^VIX`.
  결과의 `symbol`·`name`은 **내부 심볼·기존 mock name**을 유지한다
  (API 응답 계약 유지). 매핑에 없는 심볼은 스킵.
- `YFinanceExchangeRateProvider(ExchangeRateProvider)` —
  pair 매핑 상수: `USD/KRW→KRW=X`. rate = last_price,
  change_percent = previous_close 대비 파생. 매핑에 없는 pair 스킵.
- 세 provider 모두 개별 심볼 실패는 로그 후 스킵, 빈 결과 허용.

## 2. Cache — `app/adapters/market/cache.py` (신규)

- `fetch_json_cached(key: str, ttl_seconds: int, loader) -> Any` —
  Redis(`get_redis_connection()`)에서 key 조회, miss면 loader 실행
  후 `setex`. 값은 JSON 문자열 (Decimal→str, datetime→isoformat
  인코딩·역디코딩 헬퍼 포함). Redis 예외 시 loader 직접 호출 (WHY
  주석).
- 캐시 래퍼 3종 (같은 파일): `CachedMarketDataProvider` ·
  `CachedIndexQuoteProvider` · `CachedExchangeRateProvider` — 각
  ABC를 구현하고 내부 provider를 감싼다. 키는
  `market:quote:{정렬된 심볼 join}` 형식 (index·fx 동일 패턴).
  dataclass ↔ dict 변환 헬퍼로 직렬화.

## 3. Factory — `app/adapters/factory.py`

- `get_market_provider` · `get_index_quote_provider` ·
  `get_exchange_rate_provider`에 `yfinance` 분기 추가 — yfinance
  provider를 캐시 래퍼로 감싸 반환. TTL 상수는 cache.py에 둔다.
  mock 분기·`NotImplementedError` 폴백은 유지.

## Files

신규: `app/adapters/market/cache.py`, `tests/test_market_cache.py`.

갱신: `app/adapters/market/yfinance.py`, `app/adapters/factory.py`,
`tests/test_providers.py`(yfinance 순수 함수·매핑),
`tests/test_factory.py`(yfinance 분기 — 파일 없으면
test_providers.py에 포함).

변경 불가: `app/adapters/market/base.py`의 기존 시그니처(추가 없음),
`app/adapters/market/mock.py`, 소비 서비스 9곳(watchlists ·
portfolios · signals · dashboard · market 등), API 스키마, 다른
도메인.

## Test

- 순수 함수: fast_info 값 → QuoteResult 파생(change·change_percent
  quantize, currency 대문자), 숫자 심볼 `.KS` 휴리스틱, 지수·환율
  매핑(미지 심볼 스킵), previous_close 0·None 가드.
- 캐시: monkeypatch로 redis stub(in-memory dict) 주입 — miss 시
  loader 호출·hit 시 미호출, TTL 인자 전달, Redis 예외 시 loader
  폴백, dataclass 왕복 직렬화(Decimal·datetime 보존).
- factory: `MARKET_PROVIDER=yfinance`에서 3개 provider가 캐시 래퍼로
  반환, mock 분기 회귀 없음.
- 네트워크 호출 금지 — yfinance `Ticker`는 monkeypatch stub (codex
  샌드박스 네트워크 차단, 기존 관례).
- 수치 단언 출처 주석, id 리터럴 단언 금지.

## Out of Scope

- `get_quote` 시그니처의 market 인자 확장 (호출처 9곳 — 후속 이슈).
- per·target 등 optional 필드의 실데이터 채움, 시세 websocket·장중
  갱신, 배포 환경 `.env` 전환 (사용자 결정).
- intraday bars의 캐시 (기존 경로 유지).

## Open Questions

- 없음. fast_info 한정·시장 휴리스틱·TTL 값·Redis 폴백은 이 문서로
  확정한다.
