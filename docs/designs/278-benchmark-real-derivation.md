# Design — Issue 278: 벤치마크 실수집·실파생

PR #277에서 mock으로 도입한 `benchmark-comparison`을 실가격 기반으로
전환한다. 기존 가격 수집 파이프라인(yfinance 프로바이더 ·
`stock_price_bars` · 가격 수집 job)을 그대로 재사용하고, 수집 유니버스
확장과 파생 로직 교체만 수행한다. **API 계약(응답 구조·enum·고정
순서)은 변경하지 않는다** — FE #148은 수정 없이 실데이터를 받는다.

## 1. 수집 유니버스 확장 — `app/domains/prices/universe.py`

- `PriceUniverseResolver.resolve()`에 `_benchmark_targets()`를 추가한다.
  - INDEX 벤치마크: `QQQ`(NASDAQ) 고정 1종.
  - 섹터 ETF: 현재 유니버스(워치리스트·포트폴리오 자산)의 `sector`에
    매핑되는 ETF만 포함 (불필요한 심볼 수집 방지).
  - 폴백 ETF: 매핑 불가 섹터(또는 sector null) 자산이 존재하면
    `SPY`(NYSE) 포함.
- 벤치마크 심볼은 Asset 행이 필요 없다 — resolver가 반환하는
  `(symbol, market)` 튜플에만 추가되며, 기존 가격 수집 job이 자동으로
  수집한다. yfinance 티커 변환은 기존 `_MARKET_SUFFIXES`(NASDAQ·NYSE
  suffix 없음)로 충분하다.

## 2. 섹터 → ETF 매핑 — `app/domains/benchmark/sector_map.py` (신규)

- 상수 매핑 (yfinance sector 명칭 기준): Technology→XLK,
  Financial Services→XLF, Healthcare→XLV, Energy→XLE,
  Consumer Cyclical→XLY, Consumer Defensive→XLP, Industrials→XLI,
  Communication Services→XLC, Utilities→XLU, Real Estate→XLRE,
  Basic Materials→XLB. 전부 market NYSE.
- `resolve_sector_etf(sector: str | None) -> tuple[symbol, market,
  label]` — 매핑 불가·null이면 `SPY` / `S&P 500` 폴백.
- universe(수집 대상)와 service(파생)가 같은 매핑을 공유한다.

## 3. 실파생 — `app/domains/benchmark/service.py` 재작성

mock 템플릿(`_END_DATE`·`_POINT_COUNTS`·결정적 생성)을 제거하고
`stock_price_bars`(interval `1d`) 기반 파생으로 교체한다.

- 시리즈 구성 (기존 고정 순서 유지):
  - ASSET — asset의 `symbol`+`market`, label은 asset.symbol (기존 동일).
  - INDEX — `QQQ`, label `NASDAQ 100` (기존 label 유지).
  - SECTOR_ETF — `resolve_sector_etf(asset.sector)`, label은 ETF 심볼
    (폴백이면 `S&P 500`).
- 파생 규칙:
  - **기준일 = 세 시리즈 공통 거래일의 최댓값** (오늘·`datetime.now()`
    의존 금지 — 테스트 결정성과 수집 지연 내성). 시작일 = 기준일 -
    range 델타(1M 31일 / 3M 92일 / 6M 183일 / 1Y 366일).
  - 날짜 축 = 시작일 이후 **세 시리즈 공통 거래일 오름차순** (계약의
    "날짜 축 일치" 유지).
  - `return_percent` = (close / 첫 공통일 close - 1) × 100,
    `Decimal` quantize 0.01. 첫 포인트 0 유지.
- 데이터 부족 폴백: 어느 시리즈든 bar가 없으면 **공통 날짜가 공집합이
  되므로 세 시리즈 모두 `points: []`** 로 반환한다 (구조·순서·label은
  유지). 계약상 points는 비어 있을 수 있음을 설계로 확정한다 — FE는
  빈 시리즈에서 라인을 그리지 않을 뿐 깨지지 않는다.
- 조회 헬퍼: `app/domains/prices/repository.py`에
  `get_daily_closes(symbol, market, start: date | None) ->
  list[tuple[date, Decimal]]` 시그니처를 추가한다 (interval `1d`,
  timestamp 오름차순). 벤치마크 서비스는 이 헬퍼만 사용한다.
- PR #277 리뷰 S1(`_POINT_COUNTS`의 str 키 타입)은 해당 상수가 range
  델타 매핑으로 대체되면서 `dict[BenchmarkRange, timedelta]`로
  정리한다.

## Files

**신규**

- `app/domains/benchmark/sector_map.py`

**갱신**

- `app/domains/prices/universe.py` — `_benchmark_targets()`
- `app/domains/prices/repository.py` — `get_daily_closes`
- `app/domains/benchmark/service.py` — 실파생 전환
- `tests/test_benchmark.py` — 픽스처 bars 기반 재작성
- `tests/test_price_ingestion.py` (universe 테스트 위치) — 벤치마크
  타깃 포함 검증
- `tests/test_api_contract.py` — 계약 스냅샷은 유지하되 픽스처 필요 시
  갱신

**변경 불가**

- `app/domains/benchmark/schema.py` (계약 불변), alembic (신규
  테이블 없음), yfinance 어댑터, 다른 도메인.

## Test

- 파생: 픽스처 bars(자산·QQQ·섹터 ETF, 고정 날짜)로 누적 수익률 계산
  검증 — 첫 포인트 0, 공통 날짜 교집합(한 시리즈에 빠진 날짜 제외),
  range 시작일 필터(기준일 상대), quantize 0.01. 수치 단언은 픽스처
  종가에서 손계산한 기대값을 주석으로 출처 명시.
- 폴백: 벤치마크 bars 없음 → 세 시리즈 points 빈 배열·구조 유지.
  sector 매핑 불가 → SPY/`S&P 500`.
- 유니버스: 워치리스트 자산 섹터에 대응하는 ETF·QQQ 포함, 매핑 불가
  섹터 존재 시 SPY 포함, 중복 제거.
- 기존 계약 검증(3개 시리즈 고정 순서·range 422·404·401·기본 3M) 유지.
- id 리터럴 단언 금지.

## Out of Scope

- 밸류에이션·실적 실수집 (#279·#280), 5년 히스토리 (#281).
- 벤치마크 심볼의 Asset 등록·표시명 다국어화.
- 수집 스케줄·트리거 변경 (기존 가격 job 그대로).

## Open Questions

- 없음. INDEX=QQQ 고정·SPY 폴백·빈 points 허용은 이 문서로 확정한다.
