# Design — Issue 279: 밸류에이션 현재 지표 실수집

PR #277에서 mock으로 도입한 `valuation-metrics`의 현재 값(`value`)을
실수집 기반으로 전환한다. 실수집·실파생 로드맵의 2라운드로, 기존 수집
파이프라인 관례(provider 추상화 · ingestion service · worker job ·
job_runs)를 그대로 따른다. **API 계약(응답 구조·enum·metric 7종 고정
순서)은 변경하지 않는다.**

## Scope Decision

- **스냅샷 저장 방식**을 택한다 (요청 시 라이브 조회 아님). 근거:
  research-coverage VALUATION 축이 "확보 상태·마지막 갱신 시각"을
  저장 데이터에서 파생해야 하고, #281(5년 히스토리)의 백분위 산출도
  스냅샷 축적을 전제하기 때문이다.
- `five_year_median` · `percentile`은 **null 유지** (#281 범위).
- profile 판정은 이번 단계에서 산출 가능한 단순 규칙으로 확정한다
  (아래). HIGH_GROWTH·DIVIDEND 판정은 성장률·배당 데이터 미수집으로
  발생하지 않으며, 해당 데이터가 들어오는 라운드에서 확장한다.

## 1. Model — `app/domains/valuation/model.py` (신규)

`ValuationSnapshot` — 테이블 `valuation_snapshots`:

- `id` PK
- `symbol: String(20)` / `market: String(20)` — prices 관례와 동일 키
- `as_of: Date` — 스냅샷 기준일
- 지표 7종: `per` / `forward_per` / `psr` / `pbr` / `ev_ebitda` /
  `peg` / `fcf_yield` — 전부 `Numeric(20, 4) | None` (산출 불가 null)
- `source: String(30)`
- TimestampMixin. UniqueConstraint `(symbol, market, as_of)`.

alembic 마이그레이션 1개 신설 (단일 헤드 유지).

## 2. Adapter — `app/adapters/market/`

- `base.py` — `ValuationResult` dataclass(지표 7종 `Decimal | None` +
  `as_of: date` + `source: str`)와 `ValuationProvider(ABC)`:
  - `get_valuation(symbol: str, market: str) -> ValuationResult | None`
    — 조회 실패·상장폐지 등은 None.
- `yfinance.py` — `YFinanceValuationProvider`. `Ticker.info` 매핑:
  trailingPE→per, forwardPE→forward_per,
  priceToSalesTrailing12Months→psr, priceToBook→pbr,
  enterpriseToEbitda→ev_ebitda, trailingPegRatio→peg,
  fcf_yield = freeCashflow / marketCap × 100 (%; 어느 한쪽이라도
  없으면 null). 값 검증은 기존 `_to_decimal`·NaN 가드 관례 재사용.
- `mock.py` — 결정적 mock (symbol 해시 기반, 7종 채움 + 일부 null
  케이스 포함).
- `factory.py` — `get_valuation_provider()` (`MARKET_PROVIDER` 분기,
  기존 함수들과 동일 패턴).

## 3. Ingestion — `app/domains/valuation/ingestion_service.py` (신규)

- `ValuationIngestionService.collect_and_save(provider, targets) ->
  IngestionResult류` — 타깃별 `get_valuation` 호출 후
  `(symbol, market, as_of)` upsert. 실패 심볼은 건너뛰고 집계에 기록
  (prices ingestion 관례).
- 수집 유니버스: **자산 타깃만** (벤치마크 ETF 제외).
  `PriceUniverseResolver`에 자산 전용 메서드(`resolve_assets()` —
  기존 워치리스트·포트폴리오 합집합)를 분리하고, 기존 `resolve()`는
  벤치마크 포함 동작을 유지한다 (가격 job 회귀 없음).
- Repository: `app/domains/valuation/repository.py` — upsert와
  `get_latest(symbol, market)` 조회, coverage용 집계
  (`count`, `max(updated_at)`).

## 4. Worker job — `app/worker/jobs/valuation.py` (신규)

- `collect_valuation_job(symbols: list[str] | None)` —
  `app/worker/jobs/prices.py`와 동일 구조: job_type
  `valuation_collection`, universe 해소 → ingestion → job_runs
  start/succeed/fail.
- `app/api/v1/endpoints/worker.py` — `/jobs/valuation` enqueue 라우트
  추가 (기존 `/jobs/news` 패턴).

## 5. Endpoint 전환 — `app/domains/valuation/service.py`

- mock 템플릿(`_TEMPLATES` 로테이션) 제거.
- `get_metrics(asset_id)` — 자산 검증(기존) 후 asset의
  `symbol+market`으로 최신 스냅샷 조회:
  - 스냅샷 있음: metric 7종 고정 순서로 `value` 채움 (스냅샷 컬럼
    null이면 그대로 null), `five_year_median`·`percentile`은 null.
  - 스냅샷 없음: 7종 모두 `value`·`five_year_median`·`percentile`
    null (계약 유지 — FE는 "-" 표시).
- profile 판정 규칙 (이 문서로 확정):
  - `per`와 `forward_per`가 모두 null인 스냅샷 → `DEFICIT`
  - asset.sector가 `Financial Services` → `FINANCIAL`
  - 그 외(스냅샷 부재 포함) → `GENERAL`
  - 우선순위: FINANCIAL > DEFICIT > GENERAL (금융주는 PER 구조가 달라
    섹터 판정을 앞세운다).
- `highlighted_metrics` 매핑은 기존 profile별 상수를 유지한다
  (FINANCIAL → PBR·PER, DEFICIT → PSR·FCF_YIELD, GENERAL →
  PER·PBR·EV_EBITDA — mock의 기존 매핑과 다르면 기존 값을 따른다).

## 6. Coverage 연결 — `app/domains/research_coverage/service.py`

- VALUATION 축을 `valuation_snapshots` 기준 실파생으로 전환:
  asset의 `symbol+market`으로 `count`·`max(updated_at)` (PRICE 축과
  동일 패턴). EARNINGS·DISCLOSURE는 계속 `NOT_COLLECTED`.

## Files

신규: `app/domains/valuation/model.py`·`repository.py`·
`ingestion_service.py`, `app/worker/jobs/valuation.py`, alembic
마이그레이션, `tests/test_valuation_ingestion.py`.

갱신: `app/adapters/market/base.py`·`yfinance.py`·`mock.py`,
`app/adapters/factory.py`, `app/domains/valuation/service.py`,
`app/domains/prices/universe.py`(resolve_assets 분리),
`app/api/v1/endpoints/worker.py`,
`app/domains/research_coverage/service.py`, `tests/test_valuation.py`
재작성, `tests/test_research_coverage.py`·`tests/test_api_contract.py`·
`tests/test_price_ingestion.py` 갱신.

변경 불가: `app/domains/valuation/schema.py` (계약 불변), 다른 도메인,
가격·뉴스 수집 로직.

## Test

- ingestion: mock provider로 upsert(같은 as_of 재수집 시 갱신)·실패
  심볼 스킵·유니버스가 자산 타깃만 포함(벤치마크 제외).
- service: 스냅샷 기반 value 채움·부분 null·스냅샷 부재 시 전부 null,
  profile 규칙 3분기(FINANCIAL 우선·DEFICIT·GENERAL),
  highlighted_metrics 대응, 404·401, metric 7종 고정 순서 유지.
- coverage: 스냅샷 존재 시 VALUATION `COLLECTED`·count·last_updated_at,
  부재 시 `NOT_COLLECTED`.
- yfinance provider 단위 테스트는 네트워크 의존이라 제외 (기존 관례
  확인 후 동일하게) — 매핑 순수 함수가 분리돼 있으면 그 부분만 테스트.
- id 리터럴 단언 금지, 수치 단언은 픽스처 출처 주석.

## Out of Scope

- 5년 중앙값·백분위 (#281), 실적 수집 (#280), 수집 스케줄러 자동화.
- HIGH_GROWTH·DIVIDEND profile 판정 (데이터 미수집).
- FE 변경 (계약 불변).

## Open Questions

- 없음. 스냅샷 저장 방식과 profile 판정 규칙은 이 문서로 확정한다.
