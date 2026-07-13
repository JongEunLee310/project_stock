# Design — Issue 281: 5년 배수 히스토리 산출 — 중앙값·백분위 실파생

`valuation-metrics`에서 null로 남겨 둔 `five_year_median`·`percentile`을
실파생으로 전환한다. 실수집·실파생 로드맵의 4라운드로, 선행 #279(밸류에이션
스냅샷)·#280(분기 실적 수집)이 저장한 데이터와 `stock_price_bars`를
조합해 배수 시계열을 근사한다. **API 계약(`schema.py`·응답 구조·metric
7종 고정 순서)은 변경하지 않는다.**

## Scope Decision

- **산출 대상은 PER 1종으로 확정한다** (7종 전부가 아닌 부분집합).
  근거: 현재 수집 데이터로 시계열을 만들 수 있는 지표는
  일별 종가(`stock_price_bars`) ÷ TTM EPS(`earnings_reports`)로 근사
  가능한 PER뿐이다. PSR·PBR·EV_EBITDA는 주식수·장부가·EBITDA 히스토리,
  FORWARD_PER·PEG는 과거 추정치 히스토리가 필요해 미수집 상태다. 이들
  지표의 `five_year_median`·`percentile`은 null을 유지하고, 해당 원천이
  수집되는 라운드에서 확장한다.
- **조회 시 계산을 택한다** (사전 계산 테이블 아님). 근거: 입력이
  종목당 일별 종가 최대 약 1,250행 + 실적 8행이고 파생이 순수 산술이라
  요청 단위 계산 비용이 낮다. 테이블·마이그레이션·재계산 job이 없어져
  staleness 관리도 불필요하다. **이번 라운드에 alembic 마이그레이션은
  없다.**
- **가용 구간 원칙**: `five_year_median`은 "최대 5년, 계산 가능한
  구간"의 중앙값이다. yfinance 분기 재무가 최근 8분기만 제공하므로 초기
  가용 구간은 약 1년이며, 수집이 축적될수록 5년까지 늘어난다. 필드명은
  계약 유지를 위해 그대로 둔다 (FE 변경 없음).
- **가격 5년 백필 경로 추가**: 가격 수집의 range가 `"3M"` 하드코딩이라
  과거 이력을 채울 수 없다. range 파라미터를 job까지 관통시키고
  `"5Y"`를 지원해, 배포 후 1회 백필 실행으로 5년 종가를 적재한다
  (일상 스케줄 수집은 `"3M"` 기본값 유지 — 회귀 없음).

## 1. Price backfill — range 관통

- `app/adapters/market/yfinance.py` — `_range_to_period`에 `"5Y" → "5y"`
  추가.
- `app/adapters/market/mock.py` — 가격 mock의 range 처리에 `"5Y"` 지원
  (결정적, 기존 range 로직과 동일 패턴).
- `app/domains/prices/ingestion_service.py` —
  `collect_and_save(provider, targets, range_value: str = "3M")`로
  파라미터화 (`_collect_target`에 전달).
- `app/worker/jobs/prices.py` —
  `collect_prices_job(symbols, range_value: str = "3M")`. 스케줄러
  등록·기존 호출은 기본값으로 동작 불변.

## 2. Derivation — `app/domains/valuation/history.py` (신규)

순수 함수 모듈 (DB·네트워크 비의존, 단위 테스트 대상):

- `build_ttm_eps_series(reports) -> list[tuple[date, Decimal]]` —
  period_end 오름차순 정렬 후 연속 4행 슬라이딩 윈도로 TTM EPS 산출.
  윈도 안에 eps null이 있으면 그 윈도는 건너뛴다. 반환 키는 윈도 마지막
  period_end. (캘린더 갭 보정은 하지 않는 근사 — 저장 데이터가 yfinance
  연속 8분기라는 전제를 WHY 주석으로 남긴다.)
- `build_per_series(closes, ttm_eps_series) -> list[Decimal]` — 각
  종가일에 대해 period_end ≤ 종가일 중 가장 최근 TTM EPS를 매칭.
  TTM EPS가 없거나 0 이하인 날은 제외 (음수 PER은 의미 없음).
- `median_and_percentile(series) -> tuple[Decimal, int] | None` —
  관측치가 `_MIN_OBSERVATIONS`(= 20) 미만이면 None. 중앙값은 quantize
  0.01. 백분위는 **시계열 마지막 값**(파생 방법론 내부 일관성 —
  스냅샷 trailingPE와 방법론이 달라 섞지 않는다)의 순위 비율을
  0~100 int로 반올림 (`series ≤ 마지막 값` 비율 × 100).

## 3. Endpoint 전환 — `app/domains/valuation/service.py`

- `ValuationService`에 `PriceBarRepository`·`EarningsRepository` 주입.
- `get_metrics`: 스냅샷 조회(기존) 후 PER 히스토리 파생 —
  `get_daily_closes(symbol, market, start=오늘-5년)`과
  `get_recent(symbol, market, limit=8)`을 조회해 history.py 함수로
  중앙값·백분위 산출. **PER metric 행에만** `five_year_median`·
  `percentile`을 채우고 나머지 6종은 null 유지.
- 산출 불가(종가 없음·실적 없음·관측치 부족)면 PER도 null·null —
  기존 응답과 동일 (계약 유지, FE "-" 표시).
- 기준일: 종가 시계열의 마지막 거래일이 기준이므로 `datetime.now()`
  의존 없음 — 단, 5년 하한 컷은 `date.today() - 5년`으로 잡되 시계열이
  비어도 안전해야 한다 (벤치마크 #278 결정성 관례).

## Files

신규: `app/domains/valuation/history.py`,
`tests/test_valuation_history.py`.

갱신: `app/adapters/market/yfinance.py`(`_range_to_period`)·`mock.py`,
`app/domains/prices/ingestion_service.py`(range 파라미터),
`app/worker/jobs/prices.py`(range 파라미터),
`app/domains/valuation/service.py`, `tests/test_valuation.py`,
`tests/test_price_ingestion.py`(range 관통), 필요 시
`tests/test_api_contract.py`(five_year_median·percentile 타입 계약).

변경 불가: `app/domains/valuation/schema.py`·`model.py`(계약·테이블
불변), `app/domains/earnings/`·`app/domains/prices/repository.py`(기존
조회 재사용, 시그니처 변경 없음), 다른 도메인. 마이그레이션 없음.

## Test

- history.py 단위: TTM 슬라이딩 윈도(정상·null 포함 윈도 스킵),
  PER 매칭(period_end 이전 종가 제외·TTM 0 이하 제외), 중앙값 quantize,
  백분위 0·100 경계, 관측치 부족 None. 수치 단언은 픽스처 출처 주석.
- service: PER 행만 median·percentile 채움(나머지 6종 null 유지),
  종가·실적 부재 시 null, metric 7종 고정 순서·profile 로직 회귀 없음.
- ingestion: range_value가 provider 호출에 전달됨(기본 "3M" 불변),
  mock "5Y" 동작.
- id 리터럴 단언 금지.

## Out of Scope

- PER 외 6종의 히스토리 산출 (원천 미수집).
- 사전 계산 테이블·재계산 스케줄 (조회 시 계산으로 충분).
- 가격 백필 자동화 (배포 후 1회 수동 실행 — job 함수 직접 호출).
- 회계연도 분기 보정, FE 변경 (계약 불변).
- 과거 이벤트 이력 (#282).

## Open Questions

- 없음. PER 단독 산출·조회 시 계산·가용 구간 원칙·최소 관측치 20은
  이 문서로 확정한다.
