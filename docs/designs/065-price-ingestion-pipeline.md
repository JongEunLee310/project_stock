# 065 · 실데이터 가격 수집 파이프라인 (Price Ingestion Pipeline)

Status: Draft
작성: Claude Code (orchestrator)
관련: BE #168(구현 이슈), Milestone 데이터 수집 파이프라인 — 백엔드(#5). LLM 하이브리드
아키텍처(Epic #141)의 데이터 선행. 설계 013(LLM 어댑터)·053~056(LLM provider/gateway)은
이 데이터의 소비처. 브리프: LLM 사전 데이터 파이프라인.

## 1. 배경

로컬 LLM을 실제로 테스트하려니 LLM에 넘길 실데이터가 필요했다. 현재 가격 데이터는
`MARKET_PROVIDER=mock`으로 전부 합성값이며, `prices` 테이블(OHLCV)은 존재하지만
읽기 경로(`PriceService.get_series`)만 있고 외부에서 실제 가격을 받아 적재하는 **쓰기
경로가 없다**.

LLM 앞단 파이프라인의 원칙은 "LLM은 원자료를 뒤지는 탐정이 아니라 백엔드가 정리한 증거
묶음을 읽는 분석가"다. 그 증거 묶음(Feature·Context)을 만들기 전에, 먼저 **실제 원본
데이터가 DB에 쌓여야** 한다. 본 설계는 그 첫 수직 슬라이스로 **일봉 가격의 실수집**만
다룬다. Feature 계산·Context Builder는 후속 슬라이스로 분리한다.

기존 provider 추상화(`app/adapters/market/base.py`)와 factory 분기, `raw_news` 원본저장
선례를 그대로 따른다. 수집 대상 시장은 미국·한국 둘 다이며, yfinance 단일 provider가
`.KS`/`.KQ` suffix로 양쪽을 커버하므로 provider는 1개로 수렴한다.

## 2. 범위

포함:

- yfinance 실 provider 1종(`PriceSeriesProvider` 구현) + factory 분기 + 설정.
- `raw_prices` 원본 아카이브 도메인(`raw_news` 레이아웃 미러).
- `prices` 쓰기 경로: upsert repository 메서드 + 수집·검증 서비스.
- universe 해석: 관심종목(watchlist) + 보유종목(portfolio) → 수집 대상 심볼 목록.
- worker job `collect_prices_job`(`collect_news_job` 패턴 미러, `JobRun` 추적).
- yfinance 의존성 추가.
- 테스트: provider 파싱, 검증 규칙, upsert 멱등성, raw 중복 스킵.

비포함(후속 분리):

- Feature 계층(return_1d/5d/20d, 이동평균, drawdown, volume_vs_20d_avg 등).
- Context Builder / `LLMContextBundle` / LLM 입력 패키징.
- 뉴스·공시/실적 실수집(현재 뉴스는 `rss.py` 별도 존재, 본 슬라이스 밖).
- 일봉 스케줄 실등록(하루 1회 크론). 본 슬라이스는 수동/on-demand 실행으로 검증하고
  스케줄 등록 지점만 명시한다.
- 분봉·실시간 시세, rate-limit·재시도 정책 고도화, 백필 범위 정책.
- LLM 호출·판단(데이터는 LLM 흐름에 관여하지 않는다 — LLM은 마지막 칸).

## 3. 데이터 흐름

```
universe(watchlist + portfolio) → (symbol, market) 목록
  → YFinancePriceProvider.get_daily_bars()
  → RawPriceService.save_raw(payload, hash)   # 원본 아카이브(정규화 전)
  → normalize(PriceBarResult) → validate      # 검증 통과분만 다음 단계
  → PriceRepository.upsert_bars()              # unique 제약으로 dedup
  → JobRun succeed / fail
```

`llm_gateway`는 이 흐름에 관여하지 않는다. 본 파이프라인의 산출물은 `prices`·`raw_prices`
적재까지이며, 이후 Feature/Context가 이 데이터를 읽어 LLM 입력을 만든다(후속).

## 4. 심볼 / 시장 매핑

`asset.market` 값으로 yfinance ticker suffix를 부여한다. 매핑은 provider 내부 상수 테이블.

| asset.market | yfinance ticker | 비고 |
| --- | --- | --- |
| KOSPI | `{symbol}.KS` | 한국 유가증권 |
| KOSDAQ | `{symbol}.KQ` | 한국 코스닥 |
| NASDAQ / NYSE | `{symbol}` | suffix 없음 |
| (미지) | — | fail-closed: 수집 제외 + 경고 로깅 |

미지 market은 조용히 통과시키지 않는다(잘못된 ticker로 엉뚱한 데이터를 받을 위험).

## 5. 컴포넌트

### 5.1 provider — `app/adapters/market/yfinance.py`

`YFinancePriceProvider(PriceSeriesProvider)`:

```
class YFinancePriceProvider(PriceSeriesProvider):
    def get_daily_bars(self, symbol: str, market: str, range: str) -> PriceBarResult
```

책임: (1) `(symbol, market)`을 §4 매핑으로 yfinance ticker로 변환, (2) yfinance로 일봉
조회, (3) 응답을 기존 `PriceBarResult`/`PriceBar` 형태로 변환해 반환. 원본 payload는
그대로 반환/노출해 상위 서비스가 아카이브할 수 있게 한다. 네트워크·파싱 오류는 시스템
경계 예외로 상위에 전달한다.

### 5.2 factory 분기 + 설정

- `app/adapters/factory.py`: `get_price_series_provider()`(및 필요 시 `get_market_provider`)에
  `MARKET_PROVIDER == "yfinance"` 분기 추가. 기존 `mock` 분기·기본값은 유지.
- `config`: `MARKET_PROVIDER`는 기존 설정 재사용(`Literal[..., "yfinance"]`로 확장). 기본값
  변경 없음(mock 유지) — 실수집은 명시적 설정으로만 켠다.

### 5.3 `raw_prices` 도메인 — `app/domains/raw_prices/`

`raw_news` 레이아웃(model/repository/schema/service)을 미러한다.

model `RawPrice` 필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| id | int PK | |
| symbol | str | 내부 심볼 |
| market | str | 시장 |
| interval | str | `1d` 고정(본 슬라이스) |
| source | str | `yfinance` |
| payload | JSON | provider 원본 응답 |
| payload_hash | str | payload 해시(중복 스킵 키) |
| fetched_at | datetime(tz) | 수집 시각 |

repository: `save(...)`, `exists_by_hash(payload_hash) -> bool`.
service `RawPriceService`: `save_raw(symbol, market, payload) -> RawPrice | None` — 해시
계산 후 기존 해시면 스킵(재저장 안 함).

### 5.4 `prices` 쓰기 경로

- `app/domains/prices/repository.py`: `upsert_bars(bars) -> int` — `UniqueConstraint(symbol,
  market, interval, timestamp)` 기반 upsert. 동일 바 재수집 시 갱신(멱등).
- `app/domains/prices/ingestion_service.py`(신규): `PriceIngestionService`.

```
class PriceIngestionService:
    def __init__(self, db: Session) -> None
    def collect_and_save(self, provider: PriceSeriesProvider,
                         targets: list[tuple[str, str]]) -> IngestionResult
```

`collect_and_save` 책임(대상별): provider 조회 → `RawPriceService.save_raw` →
`_normalize` → `_validate`(§6) → 통과분 `upsert_bars`. 대상 단위 실패는 건너뛰고 계속하며,
수집/스킵/실패 카운트를 `IngestionResult`로 집계해 반환한다. `RawNewsService.collect_and_save`
시그니처 감각을 미러한다.

### 5.5 universe resolver

관심종목(watchlist item)의 asset + 보유종목(portfolio position)의 asset을 합쳐 중복 제거한
`(symbol, market)` 목록을 산출한다. 기존 watchlist·portfolio repository를 재사용하며, 위치는
`app/domains/prices/`(또는 공용 헬퍼). 빈 universe면 job은 no-op 성공.

### 5.6 worker job — `app/worker/jobs/prices.py`

```
def collect_prices_job(symbols: list[str] | None = None) -> None
```

`collect_news_job` 패턴 미러: DB 세션 열고, `JobRunService.start` →
`PriceIngestionService.collect_and_save(get_price_series_provider(), targets)` →
succeed/fail. `symbols`가 None이면 universe resolver로 대상 산출, 주어지면 그 목록 사용.

## 6. 검증 규칙

검증 실패 바는 **drop + 로깅**하되 job은 계속한다(한 종목 이상치가 전체 수집을 막지 않게).

| 규칙 | 판정 | 처리 |
| --- | --- | --- |
| 결측 | `close`(또는 필수 OHLC) 없음 | drop |
| 미래 날짜 | `timestamp` > 오늘(장 기준) | drop |
| 이상치 | 전일 대비 수익률 절대값 > 임계(설정, 기본 예: 0.5) | 경고 로깅(수집은 유지, 판단은 상위 유보) |
| 통화/시장 정합 | provider 통화가 `asset.market` 기대와 불일치 | 경고 로깅 |
| 중복 | unique 제약 충돌 | upsert로 흡수 |

이상치 임계는 설정값으로 두되 기본은 관대하게(드롭하지 않고 경고). 데이터 신뢰도 등급·
자동 차단 정책은 본 슬라이스 밖(정책 확정 시 ADR).

## 7. 의존성

- `pyproject.toml` — `yfinance` 추가(`uv add yfinance`).
- `app/adapters/market/base.py`(`PriceSeriesProvider`·`PriceBarResult`·`PriceBar`) — 재사용.
- `app/adapters/factory.py` — 분기 추가.
- `app/domains/prices/model.py`(`StockPrice`, unique 제약) — 재사용, 컬럼 변경 없음.
- `app/domains/prices/repository.py`·(신규)`ingestion_service.py` — 쓰기 경로 추가.
- `app/domains/raw_prices/*`(신규) — 원본 아카이브.
- `app/domains/watchlists`·`app/domains/portfolios` repository — universe 재사용.
- `app/domains/jobs`(`JobRunService`) — 실행 추적 재사용.
- `app/worker/jobs/prices.py`(신규) — 수집 job.
- 마이그레이션 — `raw_prices` 테이블 신규(설계 039 구조 준수).

## 8. 테스트

- **provider 파싱**: 고정 fixture(yfinance 응답 형태)로 파싱→`PriceBarResult` 변환, 네트워크
  미접속. 심볼/시장 매핑(KOSPI→`.KS`, KOSDAQ→`.KQ`, NASDAQ→suffix 없음, 미지→제외) 단언.
- **검증 규칙**: 결측·미래 날짜 바는 drop, 이상치·통화 불일치는 경고하되 유지, 정상 바는
  통과. 검증 결과 카운트 단언.
- **upsert 멱등성**: 동일 바 2회 수집 시 `prices` 1행 유지(중복 무증가).
- **raw 중복 스킵**: 동일 payload 재수집 시 `payload_hash` 일치로 재저장 스킵.
- **universe resolver**: watchlist+portfolio 합집합·중복 제거, 빈 universe no-op.
- **job**: `collect_prices_job`이 `JobRun`을 start→succeed로 남기고, 대상 단위 실패 시에도
  전체 job은 실패로 끝나지 않는지(또는 정책상 fail 처리) 단언.
- 기존 CI 3종(ruff+mypy+pytest) 통과.

## 9. 비범위 / 후속

- **Feature 계층**(다음 슬라이스): `prices`/`raw_prices`를 읽어 return_1d/5d/20d, 이동평균,
  drawdown, volume_vs_20d_avg 등 파생 지표 계산.
- **Context Builder / LLMContextBundle**: Feature + 뉴스 + 포트폴리오 + decision-log를 LLM
  입력 패키지로 조립(브리프 3장). 실데이터·Feature 확보 후 착수.
- **뉴스·공시 실수집**: 뉴스 provider 실연동(rss 확장), DART/SEC 공시.
- **스케줄 실등록**: 일봉 하루 1회 크론(설계 044 스케줄러 스켈레톤 활용).
- **수집 정책 고도화**: rate-limit·재시도·백필 범위·데이터 신뢰도 등급(정책 확정 시 ADR).

## ADR 판단

불필요. 기존 provider/factory 패턴과 `raw_news` 원본저장 선례를 따르는 데이터 적재이며 신규
아키텍처 결정이 없다. 데이터 신뢰도 등급·자동 차단·스케줄 주기 확정 등 정책이 도입될 때
별도 ADR로 다룬다.
