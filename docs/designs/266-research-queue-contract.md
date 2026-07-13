# BE 설계: 리서치 목록(큐) 계약 — 이슈 #266

상태: **확정** — 2026-07-10 초안(Sonnet/VFF), 2026-07-13 개정. FE 에픽 project_stock_frontend#152, FE 소비 이슈 #143.

개정 요지: 초안 이후 머지된 실데이터 라운드(#279–#282)로 earnings·valuation
테이블과 `research_coverage` 도메인(4축 커버리지)이 생겨, 완성도 축을 뉴스·가격·
재무·밸류에이션 4축으로 정렬하고 `earnings_upcoming` 필터를 `earnings_events`
DB 조회로 확정한다. Open Questions는 모두 해소했다.

## 배경

`GET /api/v1/research-summary/{asset_id}` 단건 API만 존재하여 FE가 리서치 목록을
구성하려면 자산 수만큼 N번 호출해야 합니다. 리서치 상태(데이터 준비도) 개념이 없어
"추가 확인 필요"·"데이터 부족" 같은 큐 운영 지표도 파생이 불가능한 상태입니다.

이 설계는 AI 판단(stance)과 리서치 상태(데이터 확보 수준)를 별개 필드로 분리한 뒤,
자산별 리서치 메타데이터를 한 번에 반환하는 목록 API와 요약 카운트·필터를 정의합니다.
신규 테이블은 없으며 기존 테이블의 집계·조인으로 모든 필드를 파생합니다.

---

## 1. 기존 데이터 지형 (탐사 결과)

### 1.1 AI 판단 소스

`app/domains/research_summary/service.py`의 `ResearchSummaryService.get_summary`는
`asset.id % 2` 인덱스로 `_SUMMARY_TEMPLATES`를 로테이션합니다. 반환 필드는
`stance` (`BUY_CANDIDATE` | `WATCH`), `stance_confidence`, `headline`, `key_risks`입니다.
현재는 결정적 mock이며 실 LLM 전환은 별도 로드맵에서 처리하므로, 이 설계는 소스를
재사용하되 구현을 바꾸지 않습니다.

### 1.2 리서치 상태 판정 소스

| 데이터 축 | 테이블 / 도메인 | 가용 필드 |
| --- | --- | --- |
| 뉴스 | `news_items` | `asset_id`, `created_at` (TimestampMixin), `published_at` |
| 리포트 | `research_reports` | `asset_id`, `created_at` (TimestampMixin) |
| 가격(정규화) | `stock_price_bars` | `symbol`, `market`, `interval`, `timestamp` |
| 시그널 | `signals` | `asset_id`, `signal_type`, `expires_at`, `created_at` |
| 시그널 스냅샷 | `asset_signal_snapshots` | `asset_id`, `snapshot_date`, `signal_type`, `captured_at` |
| 자산 | `assets` | `id`, `symbol`, `market`, `is_active` |
| 재무(실적) | `earnings_reports` | `symbol`, `market`, `period_end`, `updated_at` |
| 실적 이벤트 | `earnings_events` | `symbol`, `market`, `event_date` (미래 일정 포함) |
| 밸류에이션 | `valuation_snapshots` | `symbol`, `market`, `updated_at` |

재무(earnings)·밸류에이션(valuation)은 실데이터 라운드(#279–#282)에서 수집이
시작되어 완성도 축에 포함합니다. 공시(disclosure)는 아직 수집 테이블이 없어
제외하며, 추가될 때 완성도 분모를 확장합니다.

### 1.3 기존 유사 개념과의 관계

- `WatchlistSummaryResponse.risk_increasing_count` — watchlist 단위 카운트로, 이번 설계의
  자산 단위 `research_status`와 목적이 다릅니다. 중복이 아니며 별도 유지합니다.
- `WatchlistEvaluationsResponse.needs_research_count` — LLM 호출 결과(`news_risk: HIGH`
  또는 `ai_judgment: RISK_INCREASING`)를 집계한 값입니다. 리서치 큐의 `NEEDS_ATTENTION`
  판정 기준과 의미가 겹치지만 소스가 다릅니다(LLM 평가 vs. 시그널·데이터 확보 여부). 이번
  설계는 시그널·데이터 기반 결정적 파생 규칙을 사용하므로 별개로 정의합니다.
- `llm_analysis` 도메인 — 사용자 단위 LLM 분석 실행 이력만 관리하며 자산별 stance는
  포함하지 않습니다.
- `research_coverage` 도메인 — 자산 단건에 대해 NEWS·PRICE·EARNINGS·VALUATION 4축의
  수집 여부·건수·최근 갱신 시각을 반환하는 단건 API가 이미 있습니다. 이번 설계의
  완성도 축은 이 4축 정의(레코드 1건 이상 = 확보)와 동일하게 맞추되, 목록 전체에
  단건 서비스를 반복 호출하면 N+1이 되므로 배치 집계 쿼리로 별도 구현합니다.
  단건 상세는 `research_coverage`, 목록 완성도는 `research_queue`가 담당합니다.

### 1.4 실적 예정일 가용성

`earnings_events.event_date`가 미래 실적 일정을 포함하므로 `earnings_upcoming`
필터는 라이브 시장 어댑터 호출 없이 DB 조회로 판정합니다(§4.5). 초안에서 검토했던
어댑터 배치 호출·graceful degradation은 필요 없어졌습니다.

---

## 2. 신규 테이블 필요 여부

**신규 테이블 없음.** 모든 필드는 기존 테이블 집계·조인으로 파생할 수 있습니다.
완성도 계산, 상태 판정, 요약 카운트 모두 쿼리 시점에 계산하는 파생 projection입니다.

---

## 3. APIs

### 3.1 엔드포인트 선택

**신규 경로 `GET /api/v1/research-queue`를 추가합니다.**

기존 `GET /api/v1/assets` 확장을 검토했으나 거부합니다. 이유: assets 엔드포인트는 자산
목록 그 자체를 반환하는 계약이고, 리서치 큐는 watchlist 소속 자산에 대한 리서치 메타를
반환하는 용도가 다른 뷰입니다. 기존 경로를 오염시키지 않으면서 FE가 독립적으로 진화할 수
있도록 신규 경로로 분리합니다.

`/research-summary`와의 관계: 단건 조회(`/research-summary/{asset_id}`)는 그대로 유지하고,
목록 계약은 `/research-queue`가 담당합니다. 이후 실 LLM이 연결되면 stance 소스를 교체해도
이 계약의 외부 형태는 바뀌지 않습니다.

### 3.2 엔드포인트 명세

| Method · Path | 책임 | 페이지 meta |
| --- | --- | --- |
| `GET /api/v1/research-queue` | 인증된 사용자의 활성 자산 목록에 리서치 메타를 붙여 반환 | 있음 |

쿼리 파라미터:

| 파라미터 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `filter` | `str \| None` | `None` | `needs_research` / `risk_increasing` / `earnings_upcoming` / `recently_updated` |
| `page` | `int` | `1` | 공통 `PaginationParams` |
| `size` | `int` | `20` | 공통 `PaginationParams` |

인증 필수(`get_current_user`). 와이어 컨벤션은 기존 동일: snake_case, 공통 엔벨로프
`ApiResponse` + `meta: PageMeta` (§3.3). 금액은 Decimal 문자열, 시각은 `UtcDatetime`.

### 3.3 응답 Projection

**`ResearchQueueItemProjection`** (응답 배열의 각 항목):

| 필드 | 타입 | 출처 |
| --- | --- | --- |
| `asset_id` | `int` | `assets.id` |
| `symbol` | `str` | `assets.symbol` |
| `name` | `str` | `assets.name` |
| `market` | `str` | `assets.market` |
| `research_status` | `ResearchStatus` (enum str) | §4.1 판정 규칙 |
| `completeness_pct` | `int` (0–100) | §4.2 파생 규칙 |
| `stance` | `str \| None` | `ResearchSummaryService` stance 재사용 |
| `headline` | `str \| None` | `ResearchSummaryService` headline 재사용 |
| `key_issue` | `str \| None` | §4.3 파생 규칙 |
| `last_updated_at` | `UtcDatetime \| None` | §4.4 파생 규칙 |
| `signal_type` | `str \| None` | 현재 활성 시그널 중 우선순위 최상위 (출처: `signals.signal_type`) |

**`ResearchQueueSummaryProjection`** (응답 상단 요약):

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `total_research_count` | `int` | 조회 대상 활성 자산 수 |
| `needs_attention_count` | `int` | `research_status == NEEDS_ATTENTION` 인 자산 수 |
| `updated_today_count` | `int` | `last_updated_at`가 오늘(UTC)인 자산 수 |
| `insufficient_count` | `int` | `research_status == INSUFFICIENT` 인 자산 수 |

**`ResearchQueueData`** (엔벨로프 `data` 필드):

```
summary: ResearchQueueSummaryProjection
items: list[ResearchQueueItemProjection]  # 페이지네이션 적용
```

와이어 최상위는 공통 엔벨로프 `ApiResponse[ResearchQueueData]`를 사용하고,
페이지 정보는 기존 관례대로 `meta: PageMeta(page, size, total)`에 담습니다.
`total`은 필터 적용 후 전체 건수입니다(페이지 절단 전). `summary`는 필터와
무관한 전체 기준입니다(OQ-4).

---

## 4. Services

### 4.1 `ResearchStatus` enum 판정 규칙

```
class ResearchStatus(str, Enum):
    ANALYZED         = "ANALYZED"
    NEEDS_ATTENTION  = "NEEDS_ATTENTION"
    COLLECTING       = "COLLECTING"
    INSUFFICIENT     = "INSUFFICIENT"
    STALE            = "STALE"
```

한국어 라벨(`분석 완료` 등)은 FE 소관으로 BE는 반환하지 않습니다.

판정 우선순위 (위에서 아래로 — 먼저 매칭되는 규칙 적용):

| 조건 | 상태 |
| --- | --- |
| 활성 시그널에 `RISK_ALERT` 또는 `THESIS_BROKEN`이 있음 | `NEEDS_ATTENTION` |
| `completeness_pct < 30` | `INSUFFICIENT` |
| `completeness_pct < 70` | `COLLECTING` |
| `last_updated_at`가 30일 이전 | `STALE` |
| 나머지 (`completeness_pct >= 70`, 최신 데이터 있음) | `ANALYZED` |

출처 — 30% / 70% 임계값은 4축 배점(1축 = 25%)에서 "0~1축 확보 = INSUFFICIENT,
2축 = COLLECTING, 3축 이상 = 충분"으로 매핑되는 값입니다. 30일 staleness 기준과
함께 고정 초기값으로 확정하며(OQ-2 해소), 운영에서 조정 필요가 확인되면 설정값으로
추출합니다.

### 4.2 완성도(`completeness_pct`) 파생 규칙

`research_coverage`의 4축 정의와 정렬합니다. 공시(disclosure)는 미수집이므로
제외하고, 추가 시 분모를 확장합니다.

| 데이터 축 | 확보 판정 기준 | 배점 |
| --- | --- | --- |
| 뉴스 (NEWS) | `news_items`에 해당 `asset_id` 레코드 1건 이상 | 25 |
| 가격 (PRICE) | `stock_price_bars`에 해당 `symbol + market` 레코드 1건 이상 | 25 |
| 재무 (EARNINGS) | `earnings_reports`에 해당 `symbol + market` 레코드 1건 이상 | 25 |
| 밸류에이션 (VALUATION) | `valuation_snapshots`에 해당 `symbol + market` 레코드 1건 이상 | 25 |
| (확장) 공시 | 미수집 — 추후 축 추가 시 분모 조정 | — |

`completeness_pct = sum(확보된 축의 배점)`. 4축 모두 확보 시 100.

출처: `stock_price_bars.symbol/market`은 `assets.symbol/market`과 대응합니다
(`app/domains/prices/model.py:StockPriceBar` + `app/domains/assets/model.py:Asset` 확인).

### 4.3 `key_issue` 파생 규칙

우선순위:

1. 활성 시그널 중 우선순위 최상위(`SIGNAL_TYPE_CATEGORY` RISK 카테고리 우선)의 `reason` 첫
   문장
2. 없으면 `research_reports`의 최신 레코드 `negative_factors` 첫 항목
3. 없으면 `None`

### 4.4 `last_updated_at` 파생 규칙

다음 세 시각 중 가장 최신값을 반환합니다:

1. `news_items.created_at` — 해당 asset 최신값
2. `research_reports.created_at` — 해당 asset 최신값
3. `signals.created_at` — 해당 asset 최신값

세 테이블 모두 레코드가 없으면 `None`.

### 4.5 필터 매핑

| filter 값 | 매핑 조건 |
| --- | --- |
| `needs_research` | `research_status IN (NEEDS_ATTENTION, INSUFFICIENT, COLLECTING)` |
| `risk_increasing` | 활성 시그널에 `RISK_ALERT` 또는 `THESIS_BROKEN` 포함 |
| `earnings_upcoming` | `earnings_events`에 해당 `symbol + market`의 `event_date`가 오늘(UTC)부터 30일 이내인 레코드 존재 |
| `recently_updated` | `last_updated_at >= 오늘 UTC 00:00:00` |

### 4.6 서비스 시그니처

```python
class ResearchQueueService:
    def __init__(self, db: Session) -> None: ...

    def list_queue(
        self,
        filter: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ResearchQueueItemProjection], ResearchQueueSummaryProjection, int]:
        # 책임: 활성 자산 목록 조회, 각 자산에 대해 리서치 메타 파생, 필터 적용, 요약 카운트 반환

    def _derive_status(
        self,
        completeness_pct: int,
        active_signal_types: set[str],
        last_updated_at: datetime | None,
    ) -> ResearchStatus:
        # 책임: §4.1 판정 규칙을 적용하여 ResearchStatus 반환

    def _derive_completeness(
        self,
        has_news: bool,
        has_price: bool,
        has_earnings: bool,
        has_valuation: bool,
    ) -> int:
        # 책임: §4.2 규칙으로 0-100 정수 반환

    def _derive_key_issue(
        self,
        top_signal_reason: str | None,
        latest_report_negative_factors: str | None,
    ) -> str | None:
        # 책임: §4.3 규칙으로 핵심 이슈 문자열 반환

    def _derive_last_updated_at(
        self,
        news_at: datetime | None,
        report_at: datetime | None,
        signal_at: datetime | None,
    ) -> datetime | None:
        # 책임: §4.4 규칙으로 최신 갱신 시각 반환
```

### 4.7 Repository 시그니처 (신규)

```python
class ResearchQueueRepository:
    def __init__(self, db: Session) -> None: ...

    def list_active_assets(self) -> list[Asset]:
        # 책임: assets.is_active == True인 자산 목록 반환
        #       (symbol·market이 가격·재무·밸류에이션 축 병합에 필요)

    def get_data_presence_by_assets(
        self,
        assets: list[Asset],
    ) -> dict[int, ResearchDataPresence]:
        # 책임: asset별 뉴스·가격·재무·밸류에이션 축 확보 여부와 최신 갱신 시각·
        #       최신 리포트 시각을 한 번에 반환
        # N+1 회피: 테이블별 집계 쿼리(뉴스·리포트는 GROUP BY asset_id,
        #           가격·재무·밸류에이션은 GROUP BY symbol, market)를 배치 실행 후
        #           Python에서 asset_id 기준으로 병합

    def get_earnings_upcoming_assets(
        self,
        assets: list[Asset],
        horizon_days: int = 30,
    ) -> set[int]:
        # 책임: earnings_events.event_date가 오늘(UTC)~horizon_days 이내인
        #       (symbol, market) 보유 asset_id 집합 반환 (§4.5 earnings_upcoming)

    def get_active_signal_types_by_assets(
        self,
        asset_ids: list[int],
    ) -> dict[int, set[str]]:
        # 책임: asset_id별 만료되지 않은 활성 signal_type 집합 반환
        # 출처: SignalRepository.active_signal_types_by_asset 패턴 재사용
        #       (app/domains/watchlists/evaluations_service.py:116)

    def get_top_signal_reason_by_assets(
        self,
        asset_ids: list[int],
    ) -> dict[int, str | None]:
        # 책임: asset_id별 우선순위 최상위 활성 시그널의 reason 반환

    def get_latest_report_negative_factors(
        self,
        asset_ids: list[int],
    ) -> dict[int, str | None]:
        # 책임: asset_id별 최신 research_reports.negative_factors 반환
```

**`ResearchDataPresence`** (내부 NamedTuple 또는 dataclass):

```python
@dataclass
class ResearchDataPresence:
    has_news: bool
    has_price: bool
    has_earnings: bool
    has_valuation: bool
    latest_news_at: datetime | None
    latest_report_at: datetime | None
    latest_signal_at: datetime | None
```

리포트(`research_reports`)는 완성도 축에서 제외되지만 `last_updated_at`(§4.4)과
`key_issue`(§4.3)의 소스로는 계속 사용합니다.

---

## 5. 페이지네이션 및 N+1 회피

`list_queue`는 다음 순서로 실행합니다:

1. `list_active_assets()` — 전체 활성 자산 목록 (1회 쿼리)
2. `get_data_presence_by_assets(assets)` — 뉴스·가격·재무·밸류에이션 확보 여부 + 최신 시각·최신 리포트 시각 (테이블별 집계 쿼리 배치)
3. `get_active_signal_types_by_assets(asset_ids)` — 활성 시그널 타입 집합 (1회 쿼리)
4. `get_top_signal_reason_by_assets(asset_ids)` — 최상위 시그널 reason (1회 쿼리)
5. `get_latest_report_negative_factors(asset_ids)` — 최신 리포트 negative_factors (1회 쿼리)
6. `earnings_upcoming` 필터 요청 시 `get_earnings_upcoming_assets(assets)` (1회 쿼리)
7. `ResearchSummaryService`에서 stance·headline 파생 — 현재는 계산만, 네트워크 없음

각 단계는 자산 목록(id 또는 symbol·market)을 IN 절에 전달하는 배치 쿼리로 처리합니다.
필터링은 Python 레이어에서 전체 파생 완료 후 적용합니다. 페이지네이션(offset/limit)은
필터링 후 결과에 적용합니다. 라이브 시장 어댑터 호출은 없습니다.

---

## 6. 의존 도메인

| 도메인 | 사용 이유 |
| --- | --- |
| `assets` | 활성 자산 목록 |
| `signals` | 활성 시그널 타입·reason·최신 created_at |
| `news` | 뉴스 데이터 확보 여부·최신 created_at |
| `reports` | 최신 리포트 created_at·negative_factors (완성도 축 아님) |
| `prices` (`stock_price_bars`) | 가격 데이터 확보 여부 |
| `earnings` (`earnings_reports`·`earnings_events`) | 재무 확보 여부·실적 예정일 필터 |
| `valuation` (`valuation_snapshots`) | 밸류에이션 확보 여부 |
| `research_summary` | stance·headline (mock 재사용) |

---

## 7. Out of Scope

- 실 LLM stance 전환 (별도 로드맵)
- 공시(disclosure) 데이터 축 완성도 포함 (데이터 미수집)
- 사용자별 watchlist 필터링 (현재 활성 자산 전체 대상)
- 시그널 생성·리포트 생성 자동화 트리거
- 마이그레이션 (신규 테이블 없음)
- FE 화면 구현

---

## 8. Open Questions — 해소 (2026-07-13 개정)

| # | 질문 | 확정 |
| --- | --- | --- |
| OQ-1 | `earnings_upcoming` 필터 구현 방식 | `earnings_events.event_date` DB 조회로 판정 — 실데이터 라운드(#282)로 테이블이 생겨 어댑터 호출·graceful degradation 불필요 |
| OQ-2 | 완성도 임계값(30% / 70%)·`STALE` 기준(30일) 조정 가능성 | 고정 초기값으로 확정, 운영에서 조정 필요가 확인되면 설정값으로 추출 |
| OQ-3 | 큐 대상 범위: 전체 활성 자산 vs. watchlist 소속 | 전체 활성 자산으로 확정 — 기존 research-summary도 자산 단위 API(`/assets/{id}/research-summary`)이고 FE 리서치 목록이 자산 목록 기반으로 구성되므로 동일 전제를 유지, 사용자별 제한은 후속에서 필요 시 도입 |
| OQ-4 | 요약 카운트의 기준 | 필터 적용 전 전체 기준으로 확정 — 상단 지표 역할 |
