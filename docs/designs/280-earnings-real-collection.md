# Design — Issue 280: 실적 실수집 — 분기 재무·컨센서스

PR #277에서 mock으로 도입한 `earnings-summary`를 분기 재무 실수집
기반으로 전환한다. 실수집·실파생 로드맵의 3라운드로, #279(밸류에이션
스냅샷)와 같은 구성(모델·provider·ingestion·worker job·coverage 연결)을
반복한다. **API 계약(응답 구조·필드)은 변경하지 않는다.**

## Scope Decision

- **분기 원본 저장 + 조회 시 파생**: 매출·영업이익·EPS·컨센서스 EPS는
  저장하고, 마진·YoY·surprise는 조회 시 계산한다 (저장 중복 방지,
  YoY는 저장된 전년 동기 행에서 파생).
- `guidance`·`segments`는 yfinance 미제공 — **null·빈 배열로
  전환**한다 (계약 필드는 유지). 공시·IR·LLM 추출 소스가 생기는
  라운드에서 다시 채운다. mock의 한국어 가이던스 문장은 제거된다.
- period 라벨(`2025Q3`)은 **분기 종료일에서 캘린더 분기로 근사
  파생**한다 (회계연도가 어긋나는 종목은 후속 — 현 유니버스는 캘린더
  분기와 대체로 일치).
- 데이터 부재 시 `quarters`는 빈 배열을 허용한다 (FE는 행 없음 렌더).

## 1. Model — `app/domains/earnings/model.py` (신규)

`EarningsReport` — 테이블 `earnings_reports`:

- `id` PK
- `symbol: String(20)` / `market: String(20)`
- `period: String(10)` — 예 `2025Q3` (period_end에서 파생 저장)
- `period_end: Date` — 분기 종료일 (정렬·전년 동기 매칭 키)
- `revenue: Numeric(20, 4) | None`
- `operating_income: Numeric(20, 4) | None`
- `eps: Numeric(20, 4) | None`
- `eps_estimate: Numeric(20, 4) | None` — 컨센서스 (없으면 null)
- `source: String(30)`
- TimestampMixin. UniqueConstraint `(symbol, market, period)`.

alembic 마이그레이션 1개 신설 (단일 헤드 유지).

## 2. Adapter — `app/adapters/market/`

- `base.py` — `EarningsReportResult` dataclass(period_end · revenue ·
  operating_income · eps · eps_estimate, 전부 nullable 허용 + source)와
  `EarningsProvider(ABC)`:
  - `get_quarterly_earnings(symbol: str, market: str) ->
    list[EarningsReportResult]` — 최근 최대 8분기. 실패 시 빈 리스트.
- `yfinance.py` — `YFinanceEarningsProvider`:
  - `Ticker.quarterly_income_stmt`에서 Total Revenue → revenue,
    Operating Income → operating_income, Diluted EPS → eps (행 부재
    시 null). 열 인덱스(분기 종료일) → period_end.
  - `Ticker.earnings_dates`에서 EPS Estimate를 period_end와 가장 가까운
    발표일 기준으로 매칭 → eps_estimate (매칭 실패 null).
  - DataFrame 접근·값 변환은 순수 함수로 분리해 그 부분만 테스트한다
    (#279 관례).
- `mock.py` — 결정적 mock (8분기, surprise 양·음 혼재, estimate null
  1개 포함).
- `factory.py` — `get_earnings_provider()` (`MARKET_PROVIDER` 분기).

## 3. Ingestion — `app/domains/earnings/ingestion_service.py` (신규)

- `EarningsIngestionService.collect_and_save(provider, targets)` —
  `(symbol, market, period)` upsert, 실패 심볼 스킵·집계 (#279 관례).
- 유니버스: `PriceUniverseResolver.resolve_assets()` 재사용.
- Repository: `app/domains/earnings/repository.py` — upsert,
  `get_recent(symbol, market, limit)` (period_end 내림차순),
  전년 동기 조회용은 최근 8분기를 한 번에 가져와 서비스에서 매칭
  (추가 쿼리 없음), coverage용 집계(`count`, `max(updated_at)`).

## 4. Worker job — `app/worker/jobs/earnings.py` (신규)

- `collect_earnings_job(symbols)` — job_type `earnings_collection`,
  prices·valuation job과 동일 구조.
- `app/api/v1/endpoints/worker.py` — `/jobs/earnings` enqueue 라우트.

## 5. Endpoint 전환 — `app/domains/earnings/service.py`

- mock `_TEMPLATES` 제거.
- `get_summary(asset_id)` — 자산 검증 후 최근 8분기 조회, 최신 4분기를
  오름차순으로 응답:
  - `revenue_yoy_percent` = 전년 동기(period 연도-1, 같은 분기) 행이
    있으면 (revenue/전년 - 1)×100 quantize 0.01, 없거나 어느 한쪽
    revenue null이면 null.
  - `operating_margin_percent` = operating_income/revenue×100
    quantize 0.01. revenue null·0 또는 operating_income null이면 해당
    분기를 응답에서 제외하지 말고 — 계약상 이 필드는 non-nullable이므로
    **revenue·operating_income·eps 중 하나라도 null인 분기는 응답에서
    제외**한다 (불완전 행 노출 방지, 설계 확정).
  - `eps_surprise_percent` = estimate 있으면
    (eps-estimate)/|estimate|×100 quantize 0.01, 없으면 null.
  - `guidance` = null, `segments` = 빈 배열.
- 스키마의 non-nullable 필드(revenue 등) 계약을 지키기 위한 제외
  규칙이므로 schema.py는 변경하지 않는다.

## 6. Coverage 연결 — `app/domains/research_coverage/service.py`

- EARNINGS 축을 `earnings_reports` 집계로 전환 (VALUATION 축 패턴).
  DISCLOSURE만 `NOT_COLLECTED`로 남는다.

## Files

신규: `app/domains/earnings/model.py`·`repository.py`·
`ingestion_service.py`, `app/worker/jobs/earnings.py`, alembic
마이그레이션, `tests/test_earnings_ingestion.py`.

갱신: `app/adapters/market/base.py`·`yfinance.py`·`mock.py`,
`app/adapters/factory.py`, `app/domains/earnings/service.py`,
`app/api/v1/endpoints/worker.py`,
`app/domains/research_coverage/service.py`, `app/db/models.py`,
`tests/test_earnings.py` 재작성, `tests/test_research_coverage.py`·
`tests/test_api_contract.py` 갱신.

변경 불가: `app/domains/earnings/schema.py` (계약 불변), 다른 도메인,
가격·뉴스·밸류에이션 수집 로직.

## Test

- ingestion: upsert(같은 period 재수집 갱신), 실패 심볼 스킵, 유니버스
  자산 타깃.
- service: 4분기 오름차순, YoY(전년 동기 있음/없음), 마진 계산,
  surprise 양·음·estimate null, 불완전 행 제외 규칙, 데이터 부재 시
  빈 quarters·guidance null·segments 빈 배열, 404·401.
- yfinance 순수 매핑 함수 단위 테스트 (DataFrame 픽스처, 네트워크
  비의존): 행 부재 null·estimate 매칭·period 라벨 파생.
- coverage: EARNINGS 축 COLLECTED/NOT_COLLECTED.
- 수치 단언 출처 주석, id 리터럴 단언 금지.

## Out of Scope

- guidance·segments 실데이터 (후속 소스), 5년 히스토리 (#281), 과거
  이벤트 계약 (#282 — earnings_dates의 발표일 저장은 #282에서 재사용
  가능하나 이번엔 estimate 매칭에만 사용).
- 회계연도 분기 보정, FE 변경 (계약 불변).

## Open Questions

- 없음. 불완전 행 제외·캘린더 분기 근사·guidance null 전환은 이 문서로
  확정한다.
