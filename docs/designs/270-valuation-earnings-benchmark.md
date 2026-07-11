# Design — Issue 270: 밸류에이션·실적 계약 + 벤치마크 비교 시계열

리서치 상세 2차의 밸류에이션·실적 탭(FE #149)과 차트 벤치마크
오버레이(FE #148)에 필요한 계약입니다. 이슈 #271에서 후속 분리한
벤치마크 비교 시계열을 이 라운드에 묶습니다 (같은 데이터 소스 검토
묶음 — PR #275 Scope Decision 참조).

## Scope Decision

**계약 선행 — 세 엔드포인트 모두 결정적 mock으로 시작합니다** (#267 ·
#268·#269 선례). 실수집·실파생은 후속 라운드로 분리합니다.

데이터 소스 검토 결과 (yfinance 기준, 실수집 라운드의 입력):

- 현재 밸류에이션 배수(PER·Forward PER·PSR·PBR·EV/EBITDA·PEG)와 분기
  재무(매출·영업이익·EPS), 컨센서스 EPS 대비 실제, 벤치마크(지수·ETF)
  가격 시계열은 yfinance로 확보 가능.
- **5년 배수 히스토리(중앙값·백분위)는 yfinance가 직접 제공하지 않음**
  — 가격 히스토리와 분기 재무로 자체 산출이 필요해 실수집 라운드에서
  파생 로직을 설계합니다.
- 사업부문별 성장률·가이던스는 yfinance 미제공 — 공시·IR 소스 또는
  LLM 추출 후속 과제로 남깁니다. 계약에는 필드를 두되 mock 단계에서만
  채웁니다.
- 벤치마크 실수집은 수집 유니버스 확장(지수·섹터 ETF 심볼)이 필요
  합니다 (`PriceUniverseResolver`는 현재 워치리스트·포트폴리오 자산만
  해소).

벤치마크 응답의 ASSET 시리즈도 이번 단계에서는 mock입니다 — 실가격과
mock 벤치마크를 한 응답에 섞으면 비교선이 왜곡되므로, 실파생 전환은
벤치마크 실수집과 함께 일괄 수행합니다.

## Endpoint 1 — `GET /assets/{asset_id}/valuation-metrics`

응답: `ValuationMetricsResponse`

- `asset_id: int`
- `profile: str` — 종목 성격 enum: `FINANCIAL` / `HIGH_GROWTH` /
  `DEFICIT` / `DIVIDEND` / `GENERAL`. 이슈의 "종목 성격별 지표
  우선순위" 메타는 **제공하는 것으로 확정**합니다.
- `highlighted_metrics: list[str]` — profile별 우선 지표 이름 목록
  (FE 강조 표시용, 아래 metric enum 값).
- `metrics: list[ValuationMetric]` — 항상 7개, 고정 순서: `PER`,
  `FORWARD_PER`, `PSR`, `PBR`, `EV_EBITDA`, `PEG`, `FCF_YIELD`.

`ValuationMetric`:

- `metric: str` — 위 enum 7값
- `value: Decimal | None` — 현재 값. 산출 불가(적자 등)면 null.
- `five_year_median: Decimal | None` — 최근 5년 중앙값.
- `percentile: int | None` — 5년 히스토리 내 현재 위치 (0~100, 낮을수록
  역사적 저평가 구간).

mock: research_summary와 같은 결정적 템플릿 로테이션(`asset.id % N`).
profile별로 highlighted_metrics가 달라지는 템플릿을 2~3개 둡니다
(예: HIGH_GROWTH → FORWARD_PER·PSR·PEG, GENERAL → PER·PBR·EV_EBITDA).
DEFICIT 템플릿에서는 PER류 value가 null이어야 합니다 (null 계약 검증).

## Endpoint 2 — `GET /assets/{asset_id}/earnings-summary`

응답: `EarningsSummaryResponse`

- `asset_id: int`
- `quarters: list[EarningsQuarter]` — 최근 4분기, 오래된 분기부터
  오름차순.
- `guidance: str | None` — 다음 분기·연간 가이던스 요약 문장 (한국어).
- `segments: list[SegmentGrowth]` — 사업부문별 성장률. 빈 배열 허용.

`EarningsQuarter`:

- `period: str` — 예: `2025Q4`
- `revenue: Decimal` / `operating_income: Decimal` / `eps: Decimal`
- `revenue_yoy_percent: Decimal | None` — 전년 동기 대비 성장률
- `operating_margin_percent: Decimal`
- `eps_estimate: Decimal | None` — 컨센서스. 없으면 null.
- `eps_surprise_percent: Decimal | None` — (실제-컨센서스)/|컨센서스|.
  estimate가 null이면 null.

`SegmentGrowth`:

- `name: str` (한국어 부문명) / `revenue_share_percent: Decimal` /
  `yoy_growth_percent: Decimal`

mock: 결정적 로테이션. surprise 부호가 양·음 섞인 분기를 포함해 FE가
비트(beat)·미스(miss) 표시를 검증할 수 있게 합니다.

## Endpoint 3 — `GET /assets/{asset_id}/benchmark-comparison`

쿼리: `range` — `1M` / `3M` / `6M` / `1Y` (기본 `3M`). 가격 차트
기간칩과 정합하되 `1D`는 벤치마크 비교 의미가 약해 제외합니다.

응답: `BenchmarkComparisonResponse`

- `asset_id: int`
- `range: str`
- `series: list[BenchmarkSeries]` — 항상 3개, 고정 순서: `ASSET`,
  `INDEX`, `SECTOR_ETF`.

`BenchmarkSeries`:

- `kind: str` — enum 3값
- `label: str` — 표시명 (예: 자산 심볼, `NASDAQ 100`, 섹터 ETF 심볼)
- `points: list[BenchmarkPoint]` — 같은 range 안에서 세 시리즈의 날짜
  축이 일치해야 합니다 (오버레이 전제).

`BenchmarkPoint`:

- `date: date`
- `return_percent: Decimal` — **기간 시작일 대비 누적 수익률 %** (첫
  포인트 0). 정규화를 BE가 책임져 FE 오버레이 부담을 없앱니다.

mock: 결정적 생성 (asset.id·range 시드). 포인트 수는 range별 고정
(예: 1M 21 / 3M 63 / 6M 126 / 1Y 252 영업일 근사 — 구현 단순화를 위해
주 단위 축소 허용, 세 시리즈 동일 개수만 보장).

## 공통 동작

- 인증 필수. 자산 미존재 404 `ASSET_NOT_FOUND` (기존 라우트와 동일).
- alembic 변경 없음 (신규 테이블·컬럼 없음).

## Files

**신규**

- `app/domains/valuation/__init__.py` · `schema.py` · `service.py`
  - `ValuationService.get_metrics(asset_id: int) ->
    ValuationMetricsResponse` — 자산 존재 검증 후 결정적 mock 생성
- `app/domains/earnings/__init__.py` · `schema.py` · `service.py`
  - `EarningsService.get_summary(asset_id: int) ->
    EarningsSummaryResponse`
- `app/domains/benchmark/__init__.py` · `schema.py` · `service.py`
  - `BenchmarkService.get_comparison(asset_id: int, range_: str) ->
    BenchmarkComparisonResponse`
- `tests/test_valuation.py` · `tests/test_earnings.py` ·
  `tests/test_benchmark.py`

**갱신**

- `app/api/v1/endpoints/assets.py` — 라우트 3개 추가 (기존
  research-coverage·catalysts 패턴)
- `tests/test_api_contract.py` — 계약 스냅샷 추가

**변경 불가**

- alembic, 수집 파이프라인, 다른 도메인.

## Test

- 각 엔드포인트: 결정성(같은 asset_id 반복 호출 동일 응답), 404·401.
- valuation: 7개 metric 고정 순서, DEFICIT 템플릿의 null 처리,
  highlighted_metrics가 metric enum 값만 포함.
- earnings: 분기 오름차순, surprise 양·음 혼재, estimate null 케이스.
- benchmark: range 검증(허용 외 422), 시리즈 3개 고정 순서, 세 시리즈
  날짜 축 일치·첫 포인트 0, range별 포인트 수 결정성.
- 템플릿 전수 순회는 `len(_TEMPLATES)` 연동 (PR #275 S2 선례).
- id 리터럴 단언 금지 (PR #273 B1 선례).

## Out of Scope

- 실수집·실파생 (yfinance 어댑터, 5년 배수 히스토리 산출, 벤치마크
  수집 유니버스 확장) — 후속 이슈로 분리.
- 섹터→ETF 매핑 테이블의 실데이터화 (mock 단계에서는 템플릿 고정).
- FE 표시 (#148/#149).

## Open Questions

- 없음. 벤치마크 `1D` 제외와 profile 메타 제공은 이 문서로 확정한다.
