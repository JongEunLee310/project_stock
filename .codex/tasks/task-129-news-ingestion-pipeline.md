# Codex Handoff Task

## Source Issue

BE #170(실데이터 뉴스 수집 파이프라인). 설계 `docs/designs/066-news-ingestion-pipeline.md`.
가격 실수집(설계 065·PR #169)의 후속 수집 슬라이스 — LLM에 넘길 실데이터로 뉴스를 실제
수집한다. Milestone: 데이터 수집 파이프라인 — 백엔드(#5).

## Task Summary

`NEWS_PROVIDER=rss` 실 어댑터로 관심종목+보유종목 universe의 뉴스를 회사명 쿼리 기반으로 실제
수집해 `(symbol, market)` 태깅과 함께 `raw_news_events`에 적재하는 파이프라인을 구축한다.
회사명 쿼리 per-company RSS로 미국·한국을 모두 커버한다. 정규화(`news_items`)·LLM 요약은
기존 분석 파이프라인에 그대로 두고 건드리지 않는다. 범위는 원본 수집·태깅까지다.

## Goal

완료 시 참이어야 할 것:

- `NEWS_PROVIDER=rss`일 때 `get_news_adapter()`가 실 `RSSNewsAdapter`를 반환하고,
  `collect_news_job()` 실행 시 universe 종목의 뉴스가 `(symbol, market)` 태깅과 함께
  `raw_news_events`에 적재된다.
- 매칭은 회사명(`asset.name`) 쿼리 기반이다. market별 locale이 적용된다:
  KOSPI/KOSDAQ→`ko`/`KR`, NASDAQ/NYSE→`en-US`/`US`. 한국 종목도 수집된다.
- `raw_news_events`에 `symbol`·`market`(nullable) 컬럼이 추가되고, 수집 잡 경로는 이를 채운다.
  기존 분석 파이프라인 경로는 null로 저장돼 동작이 변하지 않는다.
- 동일 `url` 재수집은 `raw_news_events` 행을 늘리지 않는다(기존 url unique dedup 유지).
- 대상(종목) 단위 실패는 건너뛰고 job은 계속한다. `collect_news_job`이 `JobRun`을
  start→succeed/fail로 기록한다.
- 기본 설정(`NEWS_PROVIDER=mock`)·기존 mock 동작·분석 파이프라인·`collect_news_job` 호출부
  하위호환이 변하지 않는다.
- ruff·mypy·pytest 전부 통과한다.

## Background

- 어댑터 추상화: `app/adapters/news/base.py`의 `NewsAdapter.fetch(symbols) -> list[
  NewsAdapterResult]`. `RSSNewsAdapter`(`rss.py`, feedparser 기반)는 이미 존재하나 factory에
  배선되지 않은 고아 상태다. `MockNewsAdapter`(`mock.py`)도 있다.
- factory: `app/adapters/factory.py`의 `get_news_adapter()`가 `NEWS_PROVIDER == "mock"`이면
  `MockNewsAdapter()`, `real`이면 `NotImplementedError`. 여기에 `"rss"` 분기를 추가한다.
- 원본저장: `app/domains/raw_news/`(model/repository/schema/service). `RawNewsEvent`는
  `url` unique로 dedup한다. `RawNewsService.collect_and_save(adapter, symbols)`는 분석
  파이프라인이 사용하므로 유지한다.
- 정규화: `news_items`(`app/domains/news/`) 생성·LLM 요약은 분석 파이프라인
  (`app/domains/analysis/service.py`)이 담당한다. 본 task는 여기를 건드리지 않는다.
- 수집 job 선례: `app/worker/jobs/prices.py`의 `collect_prices_job(symbols=None)` +
  `PriceIngestionService` + `PriceUniverseResolver`. 뉴스는 이 구조를 미러한다.
- universe 선례: `app/domains/prices/universe.py`의 `PriceUniverseResolver.resolve()`는
  watchlist+portfolio를 조인해 `(symbol, market)`을 산출한다. 뉴스는 `name`까지 포함한다.
- `collect_news_job` 호출부: `app/api/v1/endpoints/worker.py`가 `queue.enqueue(
  collect_news_job, payload.symbols)`로 리스트를 넘긴다 → 시그니처를 `| None = None`으로
  확장해도 하위호환된다.
- 마이그레이션 구조는 `docs/designs/039-db-migration-structure.md`를 따른다.

## Implementation Scope

- `app/adapters/news/base.py` — `NewsAdapter` ABC에 `fetch_query(query: str, market: str)
  -> list[NewsAdapterResult]` 추가.
- `app/adapters/news/rss.py` — `RSSNewsAdapter.fetch_query` 구현:
  - `query`(회사명)와 `market` locale로 쿼리 RSS URL 생성(템플릿 주입, market별 locale은
    §Goal 매핑), 해당 피드를 파싱해 엔트리를 `NewsAdapterResult`로 변환, 필터 없이 반환.
  - 기존 `fetch(symbols)`는 유지(변경 금지).
  - 네트워크·파싱 오류는 시스템 경계 예외로 상위에 전달(대상 단위 격리는 서비스가 처리).
- `app/adapters/news/mock.py` — `MockNewsAdapter.fetch_query` 구현(질의별 합성 결과).
- `app/adapters/factory.py` — `get_news_adapter()`에 `"rss"` 분기(쿼리 템플릿 주입).
- `app/core/config.py` — `NEWS_PROVIDER` Literal에 `"rss"` 추가(기본 `mock` 유지). 쿼리 URL
  템플릿 설정 추가(기본값 제공).
- `app/domains/raw_news/model.py` — `RawNewsEvent`에 `symbol: str | None`, `market: str | None`
  컬럼 추가(nullable). `url` unique 제약 유지.
- `app/domains/raw_news/schema.py` — `RawNewsEventCreate`에 `symbol`·`market`(optional) 추가.
- `app/domains/raw_news/service.py` — `RawNewsService`에 `save_with_symbol(result, symbol,
  market) -> RawNewsEvent | None` 추가(`url` 중복 스킵). 기존 `collect_and_save`는 유지.
- `app/domains/raw_news/ingestion_service.py`(신규) — `NewsIngestionService`:
  - `collect_and_save(self, adapter, targets: list[tuple[str, str, str]]) -> IngestionResult`.
  - 대상별: `adapter.fetch_query(name, market)` → 엔트리에 `(symbol, market)` 태깅 →
    `RawNewsService.save_with_symbol` → 저장/스킵 카운트. 대상 단위 실패는 건너뛰고 계속,
    수집/저장/스킵/실패 카운트 집계.
- `app/domains/raw_news/universe.py`(신규) — `NewsUniverseResolver.resolve(symbols=None)
  -> list[tuple[str, str, str]]`: `None`이면 watchlist+portfolio asset 합집합(중복 제거,
  `(symbol, market, name)`), 명시 심볼이면 assets에서 `(market, name)` 조회·미존재 스킵.
- `app/worker/jobs/news.py` — `collect_news_job(symbols: list[str] | None = None)`:
  `JobRunService.start` → `NewsUniverseResolver(db).resolve(symbols)` →
  `NewsIngestionService.collect_and_save(get_news_adapter(), targets)` → succeed/fail.
- 마이그레이션 — `raw_news_events`에 `symbol`·`market` 컬럼 추가(설계 039 구조).
- 테스트(아래 Test Requirements).

## Out of Scope

- 정규화(`raw_news_events` → `news_items`)·LLM 요약 분리 — 기존 분석 파이프라인 유지, 변경 금지.
- 공시(disclosure)·실적 실수집, 감성/영향도 분류, 중복 기사 클러스터링.
- 뉴스 스케줄 실등록(크론). 본 task는 수동/on-demand 실행으로 검증.
- 멀티종목 기사 다중 귀속(현재 url unique로 first-writer-wins), rate-limit·재시도 고도화.
- LLM 호출·판단. FE 변경.
- 기존 `NEWS_PROVIDER=mock` 동작·`RawNewsService.collect_and_save`(분석 경로)·`news_items` 변경.

## Protected Files

`app/domains/analysis/service.py`, `app/domains/news/*`는 변경하지 않는다. 그 외 Implementation
Scope 밖 파일도 변경하지 않는다. 특히 기존 mock 어댑터·`RawNewsService.collect_and_save`
(분석 파이프라인 경로)·factory의 mock 분기 동작은 건드리지 않는다.

## Requirements

- 회사명 쿼리 per-company RSS로 미국·한국을 모두 커버(market별 locale). 미지 market은
  기본 locale + 경고(fail-open: 수집은 시도).
- 원본은 `raw_news_events`에 `(symbol, market)` 태깅과 함께 적재한다. dedup은 기존 `url`
  unique 유지.
- LLM은 이 흐름에 관여하지 않는다(원본 적재까지가 산출물).
- 실수집은 명시적 설정(`NEWS_PROVIDER=rss`)으로만 켜지고, 기본은 mock 유지.
- 대상 단위 오류가 전체 job을 중단시키지 않는다.

## Test Requirements

- `fetch_query` 파싱: 고정 fixture(RSS 응답 형태)로 파싱→`NewsAdapterResult` 변환(네트워크
  미접속). market별 locale 반영 단언.
- 태깅·저장: `NewsIngestionService`가 대상별 엔트리에 `(symbol, market)` 태깅 저장, `url`
  중복 스킵, 대상 단위 실패 시 다음 대상 계속·카운트 단언.
- universe resolver: `symbols=None` 합집합·중복 제거·name 포함, 명시 심볼 assets 조회·미존재
  스킵, 빈 universe no-op.
- job: `collect_news_job`이 `JobRun`을 start→succeed로 남기고, 대상 단위 실패 시에도 전체 job이
  실패로 끝나지 않음 단언. 기존 mock 경로·시그니처 하위호환 단언.
- 기존 분석 파이프라인 경로(`RawNewsService.collect_and_save`) 회귀 없음.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

설계 `docs/designs/066-news-ingestion-pipeline.md`가 근거. 신규 설정(`NEWS_PROVIDER=rss`·쿼리
템플릿)·`raw_news_events` 컬럼 추가는 마이그레이션·설정·knowledge 문서 반영 여부를 orchestrator가
리뷰 시 판단한다.

## ADR Need

불필요. 기존 provider/factory 패턴과 가격 수집(설계 065) 선례를 따르는 데이터 적재이며 신규
아키텍처 결정이 없다. 소스 신뢰도 등급·자동 차단·스케줄 주기 확정 등 정책 도입 시 별도 ADR.

## Failure Record Need

불필요.

## Risk Level

Medium. 외부 네트워크 의존(RSS 쿼리 엔드포인트)과 기존 `raw_news_events` 테이블 스키마 변경
(컬럼 추가 + 마이그레이션)이 포함된다. 다만 가격 수집(065)·raw_news·수집 job 선례가 있어 구조
리스크는 낮다. 주의점은 회사명 쿼리 URL·locale 정확성, `(symbol, market)` 태깅, url dedup 유지,
대상 단위 오류 격리, 기존 mock·분석 파이프라인 동작 불변, `collect_news_job` 호출부 하위호환이다.

## Expected Output

- 위 scope의 어댑터(`fetch_query`)·factory·설정·`raw_news_events` 컬럼·마이그레이션·
  `NewsIngestionService`·universe·job·테스트 변경.
- 검증 3종(ruff·mypy·pytest) 통과 로그.
- 가정(쿼리 URL 템플릿·locale 매핑·태깅·dedup)과 검증 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files or existing mock/분석 파이프라인 behavior.
- Do not change the default `NEWS_PROVIDER` (keep mock).
- Report assumptions and verification results.

## Stop Conditions

- 쿼리 RSS 엔드포인트가 한국 회사명에 대해 뉴스를 반환하지 않아 미국·한국 동시 커버가
  불가하면 멈추고 보고한다(대안 소스 판단 필요).
- `raw_news_events` 컬럼 추가 마이그레이션이 기존 분석 파이프라인 경로를 깨뜨리면 멈추고 보고한다.
- universe에 필요한 watchlist/portfolio/assets repository 접근이 불가하면 멈추고 보고한다.
