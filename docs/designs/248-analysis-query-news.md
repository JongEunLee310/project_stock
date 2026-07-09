# Design: 분석 파이프라인 뉴스 수집 경로 교체 (#248)

**Status**: Draft  
**Source Issue**: #248

## Background

`get_news_adapter()`(`app/adapters/factory.py:75`)가 `RSSNewsAdapter([], ...)`로 RSS 어댑터를
생성해 피드 URL 목록이 항상 비어 있다. 분석 파이프라인
(`WatchlistAnalysisService._process_asset`, `app/domains/analysis/service.py:94`)은
`_RecordingNewsAdapter`로 어댑터를 감싸 `RawNewsService.collect_and_save`를 호출하는데,
이 경로는 `adapter.fetch(symbols)`(피드 목록 순회)를 사용하므로 `NEWS_PROVIDER=rss`에서는
구조적으로 수집이 0건이 된다.

반면 매시 `collect_news_job`(`app/worker/jobs/news.py`)은
`NewsIngestionService.collect_and_save(adapter, targets)`를 통해
`adapter.fetch_query(name, market)` 경로로 수집하며 정상 동작한다.
`MockNewsAdapter`와 `RSSNewsAdapter` 모두 `fetch_query`를 구현하고 있어 경로 정렬이 가능하다
(출처: `app/adapters/news/mock.py:23`, `app/adapters/news/rss.py:76`).

## Scope of Change

변경 대상 파일을 다음으로 한정한다.

- `app/domains/analysis/service.py` — `_process_asset` 수집 경로 교체, `_RecordingNewsAdapter` 제거
- `tests/test_analysis_flow.py` — 쿼리 기반 어댑터 픽스처 추가, 신규 케이스 추가

## Contract Decisions

### 1. 수집 경로

`_process_asset`은 `adapter.fetch_query(asset.name, asset.market.upper())`를 직접 호출하고,
각 결과를 `RawNewsService.save_with_symbol(result, symbol, market)`으로 저장한다.
`save_with_symbol`이 `None`을 반환하면 중복(스킵), 비-`None`이면 신규 저장이므로 신규
저장분의 `NewsAdapterResult`만 `_create_new_items`에 전달한다. 이것으로 기존 URL 중복 제거와
증분 동작이 유지된다.

**`NewsIngestionService` 재사용 불가**: `NewsIngestionService.collect_and_save`의 반환값
`IngestionResult`(`app/domains/raw_news/ingestion_service.py:14–23`)에는 `NewsAdapterResult`
목록이 없다. `_create_new_items`는 `list[NewsAdapterResult]`를 입력으로 받으므로, 저장
완료 후 원본 결과를 복원할 방법이 없다. 따라서 `RawNewsService.save_with_symbol`을 직접
호출하는 최소 확장 방식을 채택한다.

### 2. 쿼리 문자열

쿼리는 회사명(`Asset.name`) 기반이며 시장 로케일은 `asset.market.upper()`를 그대로 사용한다.
수집 잡과 동일한 규칙이다(출처: `app/domains/raw_news/ingestion_service.py:51`,
`adapter.fetch_query(name, normalized_market)`).

### 3. 신규 저장분 추적

`RawNewsService.save_with_symbol`(`app/domains/raw_news/service.py:30–47`)은 내부적으로
`RawNewsEventRepository.create_or_skip`을 호출하며, 중복이면 `None`, 신규이면
`RawNewsEvent` 인스턴스를 반환한다. 이 반환값으로 신규/스킵을 구분하고, 신규 저장분에
해당하는 `NewsAdapterResult`만 모아 `_create_new_items`에 전달한다. `_create_new_items` 내
`raw_news_repo.get_by_url` 단계는 이미 저장된 `RawNewsEvent`를 조회하므로 동작이 유지된다.

### 4. 실패 격리

`fetch_query` 호출에서 발생한 예외는 `_process_asset` 내에서 위로 전파되고, `run`의
종목 단위 `try/except`(`app/domains/analysis/service.py:79–83`)가 이를 잡아 `failures`에
기록한다. 기존 격리 경로가 변경 없이 그대로 적용된다.

### 5. `_RecordingNewsAdapter` 처리

`_RecordingNewsAdapter`(`app/domains/analysis/service.py:201–208`)는 제거한다. 새 경로에서는
`fetch_query` 결과를 직접 다루므로 래퍼가 필요 없다.

## Out of Scope

- `RSSNewsAdapter.fetch()` 및 피드 URL 설정 변경
- 시그널 룰·LLM 프롬프트 변경
- `collect_news_job`·스케줄 변경
- `NewsIngestionService` 인터페이스 확장
