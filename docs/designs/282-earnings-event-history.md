# Design — Issue 282: 과거 이벤트 이력 계약 — 실적 발표 이력

FE 차트 이벤트 마커(FE #163)의 데이터 소스로, 과거 실적 발표 이력을
수집·저장하고 조회 계약을 신설한다. 실수집·실파생 로드맵의 5라운드로,
yfinance `earnings_dates`(#280에서 estimate 매칭에만 사용)를 발표 이벤트
원천으로 재사용한다.

## Scope Decision

- **계약 신설을 택한다** (catalysts 확장 아님). 근거: catalysts(#269)는
  미래 이벤트 mock 계약으로 FE 촉매 타임라인이 이미 소비 중이다. 실데이터
  과거 이벤트를 같은 계약에 섞으면 기존 소비처 회귀 위험이 있고, 차트
  마커(FE #163)는 어차피 신규 소비자다. catalysts는 변경하지 않는다.
- **발표일 단위 저장**: `earnings_dates`가 반환하는 행을 과거·미래 구분
  없이 모두 저장한다 (미래 발표 행은 후속 catalysts 실데이터 전환에서
  재사용 가능). 조회 계약은 **과거(오늘 이하)만** 반환한다.
- **수집은 기존 `earnings_collection` job에 편입**한다 — 신규 job·enqueue
  라우트 없음. 실적 리포트와 발표 이벤트는 같은 원천(Ticker)·같은 주기라
  분리할 이유가 없다.
- **surprise는 조회 시 파생** (eps_actual·eps_estimate만 저장 — #280
  파생 관례와 동일).
- 응답 projection에 title(문구)은 두지 않는다 — 마커 라벨은 FE가 수치로
  구성한다 (BE 고정 문구 결합 방지).

## 1. Model — `app/domains/earnings/model.py`에 추가

`EarningsEvent` — 테이블 `earnings_events`:

- `id` PK
- `symbol: String(20)` / `market: String(20)`
- `event_date: Date` — 발표일
- `eps_actual: Numeric(20, 4) | None`
- `eps_estimate: Numeric(20, 4) | None`
- `source: String(30)`
- TimestampMixin. UniqueConstraint `(symbol, market, event_date)`.

alembic 마이그레이션 1개 신설 (단일 헤드 유지). `app/db/models.py` 등록.

## 2. Adapter — `app/adapters/market/`

- `base.py` — `EarningsEventResult` dataclass(event_date · eps_actual ·
  eps_estimate · source)와 기존 `EarningsProvider(ABC)`에 메서드 추가:
  - `get_earnings_events(symbol: str, market: str) ->
    list[EarningsEventResult]` — 실패 시 빈 리스트.
- `yfinance.py` — `Ticker.earnings_dates` 행 매핑: 인덱스 → event_date,
  `Reported EPS` → eps_actual, `EPS Estimate` → eps_estimate (부재
  null). 같은 날짜 중복 행은 첫 행만. DataFrame 접근은 순수 함수 분리
  (#280 관례 — 기존 `_earnings_estimates` 인접 배치, 재사용 가능하면
  재사용).
- `mock.py` — 결정적 mock: 과거 분기 발표 8건 + 미래 발표 1건,
  actual·estimate null 케이스 각 1개 포함.

## 3. Ingestion — `app/domains/earnings/ingestion_service.py` 확장

- `collect_and_save`가 리포트 upsert 후 같은 타깃의
  `get_earnings_events` 결과를 `(symbol, market, event_date)` upsert.
  이벤트 수집 실패도 기존 실패 집계 관례를 따른다.
- Repository 추가: `upsert_event`,
  `get_events(symbol, market, start, end)` (event_date 오름차순).
- job·worker 라우트·universe 변경 없음.

## 4. Contract — `app/domains/asset_events/` (신규 도메인)

`GET /assets/{asset_id}/events?range=3M` (assets.py에 라우트 추가,
인증 필수 — 기존 자산 엔드포인트 관례):

- `schema.py`:
  - `AssetEventRange(str, Enum)` — `1M / 3M / 6M / 1Y` (기본 `3M`).
    benchmark와 값은 같지만 도메인 간 import를 피해 별도 enum.
  - `AssetEventType(str, Enum)` — `EARNINGS` (후속 라운드에서 공시 등
    확장).
  - `AssetEventProjection` — `event_date: date` ·
    `event_type: AssetEventType` · `eps_actual: Decimal | None` ·
    `eps_estimate: Decimal | None` ·
    `eps_surprise_percent: Decimal | None`
  - `AssetEventHistoryResponse` — `asset_id` · `range` ·
    `events: list[AssetEventProjection]` (event_date 오름차순)
- `service.py` — `AssetEventService.get_history(asset_id, range)`:
  - 자산 검증(404) 후 `end = date.today()`,
    `start = end - delta` (benchmark `_RANGE_DELTAS`와 동일 일수 매핑을
    자체 상수로 둔다).
  - `EarningsRepository.get_events`로 조회, 미래 발표 제외(end 이하),
    surprise = (actual - estimate) / |estimate| × 100 quantize 0.01
    (어느 한쪽 null 또는 estimate 0이면 null — earnings service 파생
    관례).
  - 데이터 부재 시 빈 events.

## Files

신규: `app/domains/asset_events/schema.py`·`service.py`, alembic
마이그레이션, `tests/test_asset_events.py`.

갱신: `app/domains/earnings/model.py`·`repository.py`·
`ingestion_service.py`, `app/adapters/market/base.py`·`yfinance.py`·
`mock.py`, `app/api/v1/endpoints/assets.py`, `app/db/models.py`,
`tests/test_earnings_ingestion.py`·`tests/test_providers.py`·
`tests/test_api_contract.py` 갱신.

변경 불가: `app/domains/catalysts/`(계약·mock 유지),
`app/domains/earnings/schema.py`·`service.py`(earnings-summary 불변),
worker job·라우트, 다른 도메인.

## Test

- ingestion: 이벤트 upsert(같은 event_date 재수집 갱신), 리포트와 이벤트
  동시 수집, 실패 심볼 스킵 유지.
- service: range 4종 필터 경계, 미래 발표 제외, surprise 양·음·estimate
  null·estimate 0 가드, event_date 오름차순, 빈 events, 404·401.
- yfinance 순수 매핑: 행 → EarningsEventResult(null 처리·중복 날짜
  dedup), 네트워크 비의존 DataFrame 픽스처.
- api contract: `/assets/{id}/events` 응답 구조·enum 직렬화.
- 수치 단언 출처 주석, id 리터럴 단언 금지.

## Out of Scope

- FE 마커 렌더 (FE #163), catalysts 실데이터 전환, 공시 이벤트 타입.
- 발표 시각(장전·장후) 구분, 수집 스케줄 변경.

## Open Questions

- 없음. 계약 신설·발표일 저장(미래 포함)·기존 job 편입·title 미포함은
  이 문서로 확정한다.
