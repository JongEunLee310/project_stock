# Codex Handoff Task

## Source Issue

BE #168(실데이터 가격 수집 파이프라인). 설계 `docs/designs/065-price-ingestion-pipeline.md`.
LLM 하이브리드 아키텍처(Epic #141)의 데이터 선행 — LLM에 넘길 실데이터가 필요해 가격 일봉을
실제 수집하는 첫 수직 슬라이스. Milestone: 데이터 수집 파이프라인 — 백엔드(#5).

## Task Summary

`MARKET_PROVIDER=yfinance` 실 provider로 관심종목+보유종목 universe의 일봉 가격을 실제
수집해 원본 아카이브(`raw_prices`) → 검증 → `prices` upsert까지 적재하는 파이프라인을
구축한다. yfinance 단일 provider가 `.KS`/`.KQ` suffix로 미국·한국을 모두 커버한다.
Feature 계산·Context Builder·LLM 호출은 범위 밖.

## Goal

완료 시 참이어야 할 것:

- `MARKET_PROVIDER=yfinance`일 때 `get_price_series_provider()`가 실 provider를 반환하고,
  `collect_prices_job()` 실행 시 universe 종목의 일봉이 `prices`·`raw_prices`에 적재된다.
- `(symbol, market)` → yfinance ticker 매핑이 정확하다: KOSPI→`.KS`, KOSDAQ→`.KQ`,
  NASDAQ/NYSE→suffix 없음, 미지 market→수집 제외 + 경고(fail-closed).
- 동일 바 재수집은 `prices` 행을 늘리지 않는다(unique 제약 upsert 멱등). 동일 원본 재수집은
  `raw_prices`에 `payload_hash` 일치로 재저장하지 않는다.
- 검증: 결측·미래 날짜 바는 drop, 이상치·통화 불일치는 경고하되 유지, 대상 단위 실패는
  건너뛰고 job은 계속한다.
- `collect_prices_job`이 `JobRun`을 start→succeed/fail로 기록한다.
- 기본 설정(`MARKET_PROVIDER=mock`)과 기존 읽기 경로·mock 동작은 변경되지 않는다.
- ruff·mypy·pytest 전부 통과한다.

## Background

- provider 추상화: `app/adapters/market/base.py`의 `PriceSeriesProvider.get_daily_bars(
  symbol, market, range)` → `PriceBarResult`/`PriceBar`. 실 provider는 이 인터페이스를 구현한다.
- factory: `app/adapters/factory.py`의 `get_price_series_provider()`가 `settings.MARKET_PROVIDER
  == "mock"`이면 `MockPriceSeriesProvider()` 반환. 여기에 `"yfinance"` 분기를 추가한다.
  기존 mock 분기·기본값은 유지.
- `prices` 도메인: `app/domains/prices/model.py`의 `StockPrice`(OHLCV, `source`, tz timestamp)에
  `UniqueConstraint(symbol, market, interval, timestamp)` 존재 → upsert dedup 가능.
  현재 `service.py`는 읽기(`get_series`)만 있고 쓰기 경로가 없다.
- 원본저장 선례: `app/domains/raw_news/`(model/repository/schema/service). `raw_prices`는 이
  레이아웃을 그대로 미러한다(payload JSON + payload_hash 중복 스킵 포함).
- 수집 job 선례: `app/worker/jobs/news.py`의 `collect_news_job(symbols)` →
  세션 열고 `RawNewsService(db).collect_and_save(get_news_adapter(), symbols)`.
  `collect_prices_job`은 이 패턴을 미러하되 `JobRunService`(`app/domains/jobs/service.py`의
  start/succeed/fail)로 실행을 감싼다.
- universe: 관심종목은 watchlist item, 보유종목은 portfolio position에서 asset을 얻는다.
  기존 watchlist·portfolio repository를 재사용해 `(symbol, market)` 합집합(중복 제거)을 만든다.
- 마이그레이션 구조는 설계 `docs/designs/039-db-migration-structure.md`를 따른다.

## Implementation Scope

- `pyproject.toml` — `yfinance` 의존성 추가(`uv add yfinance`).
- `app/adapters/market/yfinance.py`(신규) — `YFinancePriceProvider(PriceSeriesProvider)`:
  - `get_daily_bars(self, symbol, market, range) -> PriceBarResult`.
  - `(symbol, market)`을 내부 상수 매핑으로 yfinance ticker로 변환(§Goal 매핑), 일봉 조회 후
    `PriceBarResult`/`PriceBar`로 변환. 원본 payload를 상위가 아카이브할 수 있게 노출.
  - 네트워크·파싱 오류는 시스템 경계 예외로 상위에 전달(대상 단위로 상위 서비스가 처리).
- `app/adapters/factory.py` — `get_price_series_provider()`에 `"yfinance"` 분기 추가.
- `app/core/config.py`(또는 해당 settings) — `MARKET_PROVIDER` Literal에 `"yfinance"` 추가.
  기본값 변경 없음(mock 유지).
- `app/domains/raw_prices/`(신규, `raw_news` 미러):
  - `model.py` `RawPrice`: `id, symbol, market, interval, source, payload(JSON),
    payload_hash, fetched_at(tz)`.
  - `repository.py`: `save(...)`, `exists_by_hash(payload_hash) -> bool`.
  - `service.py` `RawPriceService.save_raw(symbol, market, payload) -> RawPrice | None`:
    해시 계산 후 기존 해시면 스킵.
  - `schema.py`: 필요한 최소 스키마.
- `app/domains/prices/repository.py` — `upsert_bars(bars) -> int`(unique 제약 기반 멱등 upsert).
- `app/domains/prices/ingestion_service.py`(신규) — `PriceIngestionService`:
  - `collect_and_save(self, provider, targets: list[tuple[str, str]]) -> IngestionResult`.
  - 대상별: provider 조회 → `RawPriceService.save_raw` → normalize → validate(§검증) →
    통과분 `upsert_bars`. 대상 단위 실패는 건너뛰고 계속, 수집/스킵/실패 카운트 집계.
- universe resolver(`app/domains/prices/` 내 헬퍼 또는 서비스) — watchlist+portfolio asset을
  합쳐 중복 제거한 `(symbol, market)` 목록 산출. 빈 목록이면 no-op.
- `app/worker/jobs/prices.py`(신규) — `collect_prices_job(symbols: list[str] | None = None)`:
  세션 + `JobRunService.start` → `PriceIngestionService.collect_and_save(
  get_price_series_provider(), targets)` → succeed/fail. `symbols=None`이면 universe 사용.
- 마이그레이션 — `raw_prices` 테이블 신규(설계 039 구조).
- 테스트(아래 Test Requirements).

## Out of Scope

- Feature 계층(return_1d/5d/20d, 이동평균, drawdown, volume_vs_20d_avg 등) — 다음 슬라이스.
- Context Builder / `LLMContextBundle` / LLM 입력 패키징 / LLM 호출.
- 뉴스·공시/실적 실수집, 분봉·실시간 시세.
- 일봉 스케줄 실등록(크론). 본 task는 수동/on-demand 실행으로 검증. 스케줄 등록 지점만 설계에 명시.
- rate-limit·재시도·백필 범위 정책 고도화, 데이터 신뢰도 등급·자동 차단.
- 기존 `MARKET_PROVIDER=mock` 동작·`PriceService.get_series` 읽기 경로 변경.
- FE 변경.

## Protected Files

없음. 위 Implementation Scope 밖 파일은 변경하지 않는다. 특히 기존 mock provider·prices 읽기
경로·factory의 mock 분기 동작은 건드리지 않는다.

## Requirements

- yfinance 단일 provider로 미국·한국을 모두 커버(`.KS`/`.KQ` suffix). 미지 market은 fail-closed.
- 원본은 정규화 전에 `raw_prices`에 아카이브하고, 정규화 데이터는 `prices`에 분리 저장한다.
- LLM은 이 흐름에 관여하지 않는다(데이터 적재까지가 산출물).
- 실수집은 명시적 설정(`MARKET_PROVIDER=yfinance`)으로만 켜지고, 기본은 mock 유지.
- 대상 단위 오류가 전체 job을 중단시키지 않는다.

## Test Requirements

- provider 파싱: 고정 fixture로 파싱→`PriceBarResult` 변환(네트워크 미접속). 심볼/시장 매핑
  4종(KOSPI/KOSDAQ/NASDAQ/미지) 단언.
- 검증: 결측·미래 날짜 drop, 이상치·통화 불일치는 경고하되 유지, 정상 바 통과, 카운트 단언.
- upsert 멱등성: 동일 바 2회 수집 시 `prices` 1행 유지.
- raw 중복 스킵: 동일 payload 재수집 시 `payload_hash` 일치로 재저장 안 함.
- universe resolver: watchlist+portfolio 합집합·중복 제거, 빈 universe no-op.
- job: `collect_prices_job`이 `JobRun`을 start→succeed로 남기고, 대상 단위 실패 시에도 전체
  job이 실패로 끝나지 않음(정책상 성공 처리) 단언.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

설계 `docs/designs/065-price-ingestion-pipeline.md`가 근거. 신규 설정(`MARKET_PROVIDER=yfinance`)·
`raw_prices` 테이블은 마이그레이션·설정 문서에 반영 여부를 orchestrator가 리뷰 시 판단한다.

## ADR Need

불필요. 기존 provider/factory 패턴과 `raw_news` 원본저장 선례를 따르는 데이터 적재이며 신규
아키텍처 결정이 없다. 데이터 신뢰도 등급·자동 차단·스케줄 주기 확정 등 정책 도입 시 별도 ADR.

## Failure Record Need

불필요.

## Risk Level

Medium. 외부 네트워크 의존(yfinance) 신규 도입과 신규 테이블·쓰기 경로가 포함된다. 다만
provider/factory·raw_news·수집 job 선례가 있어 구조 리스크는 낮다. 주의점은 심볼/시장 매핑
정확성, upsert 멱등성, raw 해시 중복 스킵, 대상 단위 오류 격리, 기본 mock 동작 불변이다.

## Expected Output

- 위 scope의 provider·factory·설정·`raw_prices`·prices 쓰기 경로·universe·job·마이그레이션·
  테스트 변경.
- 검증 3종(ruff·mypy·pytest) 통과 로그.
- 가정(yfinance ticker 매핑·검증 처리·멱등성)과 검증 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files or existing mock/read behavior.
- Do not change the default `MARKET_PROVIDER` (keep mock).
- Report assumptions and verification results.

## Stop Conditions

- yfinance가 한국 종목(`.KS`/`.KQ`)에 대해 일봉을 반환하지 않아 미국·한국 동시 커버가
  불가하면 멈추고 보고한다(대안 provider 판단 필요).
- `StockPrice` unique 제약으로 멱등 upsert를 구현할 수 없으면 멈추고 보고한다.
- universe에 필요한 watchlist/portfolio repository 접근이 불가하면 멈추고 보고한다.
