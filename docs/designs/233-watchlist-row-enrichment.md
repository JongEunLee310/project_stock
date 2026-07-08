# Design: 관심종목 행 보강 계약 — 상태 배지·마지막 갱신·1D 스파크라인 (#233)

## Status

Implemented

## Context

FE 관심종목 페이지(project_stock_frontend#117) Phase 2에서 테이블 행에 종목별 상태 배지,
마지막 갱신 시각, 변화(1D) 미니 스파크라인이 필요하다. 현재 확장 조회 응답
(`WatchlistItemExpandedResponse` + `AssetBriefResponse`)에는 해당 필드가 없다.

## Verified Facts (origin/dev, 2026-07-08 확인)

- `app/domains/signals/types.py:4` — `SignalType(str, Enum)` 값 전체 대문자:
  `WATCH`, `RISK_ALERT`, `THESIS_BROKEN`, `BUY_CANDIDATE`, `SELL_REVIEW`, `OVERHEATED`.
- `app/domains/signals/types.py:13` — `WATCHLIST_STATUS_NORMAL = "NORMAL"`.
- `app/domains/signals/types.py:24` — `resolve_watchlist_status(active_types: set[str]) -> str`
  — `WATCHLIST_STATUS_PRIORITY` 순으로 활성 타입을 확인해 첫 일치 `.value`를 반환, 없으면 `"NORMAL"`.
- `app/domains/signals/repository.py:96` — `SignalRepository.active_signal_types_by_asset(asset_ids: list[int]) -> dict[int, set[str]]`
  — 배치 쿼리로 활성 시그널 타입 집합을 반환. `list_items_expanded`의 `asset_ids`와 직접 결합 가능.
- `app/domains/watchlists/service.py:27` — `WatchlistService.__init__`에 `self.signal_repo = SignalRepository(db)` 이미 주입됨.
- `app/domains/watchlists/service.py:125` — `list_items_expanded`에서 `asset_ids` 리스트가
  이미 구성되어 있으며, 현재 시그널 조회는 하지 않는다.
- `app/adapters/market/base.py:8` — `QuoteResult` frozen dataclass에 `as_of: datetime` 존재.
- `app/adapters/market/base.py:67` — `IndexQuoteResult.reference_at: datetime` — 시장 도메인
  표기 규칙. `AssetBriefResponse`에 추가할 필드명을 `reference_at`으로 통일한다.
- `app/domains/watchlists/schema.py:40` — `AssetBriefResponse(symbol, market, name, price,
  change_percent, sector, currency: str | None)`. `reference_at` 없음.
- `app/domains/watchlists/schema.py:50` — `WatchlistItemExpandedResponse`에 `status` 없음.
- `app/domains/prices/service.py:14` — 지원 interval `"1d"` 전용, 지원 range `"1M"`, `"3M"`,
  `"6M"`, `"1Y"`. 인트라데이 없음.
- `app/domains/watchlists/trend_service.py:16` — trends 시리즈 키: `watchlist_total`,
  `risk_increasing` — 일별 항목 수 / RISK_ALERT 수. 가격 관련 데이터 없음.
- `app/domains/watchlists/schema.py:45` — `AssetBriefResponse.change_percent: str` —
  `QuoteResult.change_percent` 기반 일간 변화율로, FE가 이 값으로 전일 대비 델타 표시 가능.
- `app/api/v1/endpoints/watchlists.py:87` — `GET /watchlists/{id}/items?expand=asset`로
  expand 파라미터 제어하는 기존 패턴 존재. 별도 child endpoint 패턴도
  `/summary/trends` 선례가 있다.

## Design Decisions

### 1. 전일 대비 델타 — BE 변경 없음

`AssetBriefResponse.change_percent`는 이미 `QuoteResult.change_percent`(전일 종가 대비 등락률)를
전달하고 있다. `GET /watchlists/{id}/summary/trends`의 시리즈는 일별 항목 수와 RISK_ALERT 수이므로
가격 delta와 무관하다. FE는 기존 `change_percent` 필드로 전일 대비 델타를 직접 표시할 수 있어
**이 항목은 BE 변경 없음으로 결정**한다.

### 2. 스파크라인 — 별도 배치 엔드포인트

인트라데이 시세가 없으므로 최근 일봉 종가 시리즈로 제공한다. 두 가지 옵션을 검토했다.

- **Option A: `expand=sparkline` inline** — 기존 items 엔드포인트에 expand 파라미터 추가.
  Pagination 응답에 종목별 bars 배열이 중첩되어 응답 크기가 페이지 이동마다 증가하고, FE가
  페이지를 넘길 때마다 전체 스파크라인을 재조회해야 한다.
- **Option B: 별도 배치 엔드포인트 `GET /watchlists/{id}/sparklines`** — 관심종목 전체 종목의
  미니 시리즈를 한 번에 반환. FE가 한 번 호출 후 캐시 가능, pagination과 독립, `/summary/trends`
  선례와 동일한 child endpoint 패턴.

**결정: Option B.** 스파크라인은 pagination 단위가 아니라 관심종목 전체에 대한 배치 조회이므로
items 엔드포인트와 수명 주기가 다르다. 별도 엔드포인트가 두 관심사를 분리하고 FE 측 캐싱
및 재사용 편의를 높인다.

## Interfaces

### WatchlistItemExpandedResponse 변경 (`app/domains/watchlists/schema.py`)

추가 필드:
| 필드 | 타입 | 설명 |
|------|------|------|
| `status` | `str` | `"NORMAL"` 또는 활성 `SignalType.value` 중 우선순위 최상위 |

### AssetBriefResponse 변경 (`app/domains/watchlists/schema.py`)

추가 필드:
| 필드 | 타입 | 설명 |
|------|------|------|
| `reference_at` | `UtcDatetime \| None = None` | quote.as_of 기반 시세 기준 시각 |

### Sparkline schemas (신규, `app/domains/watchlists/schema.py`)

| 클래스 | 필드 |
|--------|------|
| `SparklineBar` | `date: str`, `close: str` |
| `AssetSparklineResponse` | `symbol: str`, `bars: list[SparklineBar]` |
| `WatchlistSparklineResponse` | `items: list[AssetSparklineResponse]` |

### WatchlistSparklineService (신규, `app/domains/watchlists/sparkline_service.py`)

```
class WatchlistSparklineService:
    def __init__(self, db: Session) -> None
    def get_sparklines(self, watchlist_id: int, user_id: int, range_value: str = "1M") -> WatchlistSparklineResponse
```

책임: 관심종목 소유 확인 → 항목의 asset 목록 조회 → `PriceSeriesService.get_series`로 종목별
일봉 bars 조회 → close 필드만 발췌해 반환. `range_value`는 `PriceSeriesService`가 허용하는
값만 전달 가능(기본 `"1M"`).

### WatchlistService.list_items_expanded 수정 (`app/domains/watchlists/service.py`)

```
def list_items_expanded(self, watchlist_id, user_id, offset, limit, sort) -> list[WatchlistItemExpandedResponse]
```

추가 책임:
- `self.signal_repo.active_signal_types_by_asset(asset_ids)` 배치 호출
- 각 item의 `asset_id`에 대해 `resolve_watchlist_status(types)` 호출
- `WatchlistItemExpandedResponse` 생성 시 `status` 전달
- `AssetBriefResponse` 생성 시 `reference_at=quote.as_of if quote else None` 전달

### API (신규)

```
GET /api/v1/watchlists/{watchlist_id}/sparklines
  Query: range: Literal["1M", "3M", "6M", "1Y"] = "1M"
  Response: ApiResponse[WatchlistSparklineResponse]
  Auth: 인증 필요, 소유자 확인
```

## Dependencies

- `app/domains/signals` — `resolve_watchlist_status`, `SignalRepository.active_signal_types_by_asset`
- `app/domains/prices` — `PriceSeriesService.get_series`
- `app/adapters/market/base` — `QuoteResult.as_of`

## Out of Scope

- 인트라데이 스파크라인 (일봉만 지원)
- `AssetDetailResponse` 등 다른 응답의 status·reference_at 처리
- FE 구현 (project_stock_frontend#117)
- 스파크라인 외부 데이터 소스 추가

## Test Strategy

- `list_items_expanded` 반환값에 `status` 포함, `asset.reference_at` 포함 테스트
- status 우선순위 검증: 활성 시그널 없음 → `"NORMAL"`, 복수 활성 시그널 → 우선순위 최상위 반환
- `GET /watchlists/{id}/sparklines` 엔드포인트 테스트: range 기본값·명시값, 빈 관심종목
- `WatchlistSparklineService` 단위 테스트
- 기존 확장 조회 테스트 약화 금지 (currency·change_percent 포함 테스트 등)
- 픽스처 `SignalType.value` 는 `app/domains/signals/types.py` 값에서 직접 인용
