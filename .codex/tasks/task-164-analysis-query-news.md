# Codex Handoff Task

## Source Issue

#248 — 분석 파이프라인 뉴스 수집을 쿼리 기반으로 정렬 (rss 프로바이더에서 수집 0건 해소)

설계 문서: `docs/designs/248-analysis-query-news.md`

## Task Summary

`WatchlistAnalysisService._process_asset`의 뉴스 수집 경로를 피드 순회(`adapter.fetch`)에서
쿼리 기반(`adapter.fetch_query`)으로 교체한다. `_RecordingNewsAdapter`를 제거하고,
`RawNewsService.save_with_symbol`로 신규 저장분을 직접 추적한 뒤 `_create_new_items`에
전달하는 구조로 바꾼다.

## Goal

- `NEWS_PROVIDER=rss`에서 분석 파이프라인이 실뉴스를 수집해 NewsItem·리포트·시그널을 생성한다.
- `NEWS_PROVIDER=mock`에서 기존 분석 플로우(뉴스→요약→리포트→시그널 룰)가 회귀 없이 동작한다.
- 이번 실행에서 새로 저장된 뉴스만 NewsItem으로 승격하는 증분 동작(URL 중복 제거 포함)이 유지된다.
- 수집 실패는 기존 종목 단위 실패 격리 규칙을 따른다.

## Background

`get_news_adapter()`(`app/adapters/factory.py:75`)가 `RSSNewsAdapter([], ...)`로 어댑터를
생성해 피드 목록이 항상 비어 있다. 분석 파이프라인은 피드 순회 경로(`adapter.fetch`)를 쓰므로
rss 프로바이더에서는 수집이 구조적으로 0건이다.

매시 수집 잡(`collect_news_job`)은 `adapter.fetch_query(name, market)` 경로로 정상 동작한다.
`MockNewsAdapter`·`RSSNewsAdapter` 모두 `fetch_query`를 구현하고 있다.

설계 결정의 상세는 `docs/designs/248-analysis-query-news.md`를 참조한다.

**`NewsIngestionService` 재사용 불가**: `NewsIngestionService.collect_and_save`의 반환값
`IngestionResult`에는 `NewsAdapterResult` 목록이 없어서 저장 후 원본 결과를 복원할 수 없다.
따라서 `RawNewsService.save_with_symbol`을 `_process_asset` 내에서 직접 호출하는 방식을
채택한다.

## Implementation Scope

다음 두 파일만 변경한다.

- `app/domains/analysis/service.py`
  - `_process_asset`: `_RecordingNewsAdapter` 사용 및 `RawNewsService.collect_and_save` 호출을
    제거하고, `adapter.fetch_query(asset.name, asset.market.upper())`를 호출한 뒤
    `RawNewsService.save_with_symbol`로 각 결과를 저장해 신규 저장분만 `_create_new_items`에
    전달하는 구조로 교체한다.
  - `_RecordingNewsAdapter` 클래스: 제거한다.
- `tests/test_analysis_flow.py`
  - `StaticNewsAdapter`: `fetch_query(query, market)`도 구현하도록 확장하거나, 쿼리 기반
    전용 픽스처 클래스를 추가한다.
  - `FailingNewsAdapter`: `fetch_query`에서 실패를 재현하도록 확장한다.
  - 기존 테스트: 쿼리 기반 경로를 통해 동일하게 통과하도록 픽스처를 조정한다.
  - 신규 테스트: 아래 Test Requirements 참조.

## Out of Scope

- `RSSNewsAdapter.fetch()` 및 피드 URL 설정 변경
- 시그널 룰·LLM 프롬프트 변경
- `collect_news_job`·스케줄 변경
- `NewsIngestionService` 인터페이스 확장
- `app/adapters/factory.py` 변경

## Protected Files

없음.

## Requirements

이슈 #248 요구 불릿을 수용 기준으로 번역한 것이다.

1. 분석 파이프라인의 종목별 뉴스 수집은 `adapter.fetch_query(asset.name, asset.market.upper())`
   경로를 사용해야 한다. 쿼리 문자열은 회사명(`Asset.name`) 기반이고 시장 로케일은
   `asset.market.upper()`를 그대로 사용한다(수집 잡과 동일한 규칙; 출처:
   `app/domains/raw_news/ingestion_service.py:51`).
2. 이번 실행에서 새로 저장된 뉴스만 NewsItem으로 승격해야 한다. URL 중복 제거는 기존과
   동일하게 동작해야 한다.
3. `NEWS_PROVIDER=mock`에서 분석 플로우(뉴스 수집→요약→리포트→시그널 룰)가 회귀 없이
   동작해야 한다.
4. 수집 실패(`fetch_query` 예외)는 `_process_asset` 예외로 전파되어 `run`의 종목 단위
   `try/except`가 `failures`에 기록하는 기존 격리 경로를 그대로 타야 한다.

## Test Requirements

다음 네 가지를 테스트로 보증한다.

1. **쿼리 기반 수집 승격**: `fetch_query`를 구현한 어댑터로 분석을 실행했을 때 NewsItem이
   생성되고 리포트·시그널로 이어지는 것을 검증한다.
2. **mock 회귀**: 기존 분석 플로우 테스트가 쿼리 기반 경로에서도 모두 통과해야 한다.
   픽스처는 `fetch_query` 경로를 실제로 관통해야 하며, `fetch()`만 구현한 어댑터를
   그대로 두어서는 안 된다.
3. **수집 실패 격리**: `fetch_query`에서 예외를 던지는 어댑터로 실행했을 때 해당 종목이
   `failures`에 기록되고 나머지 종목은 정상 처리되는 것을 검증한다.
4. **URL 중복 증분**: 동일 어댑터로 같은 watchlist를 두 번 실행했을 때 두 번째 실행에서
   NewsItem이 생성되지 않는 것을 검증한다.

테스트 픽스처의 계약 값(`url` 패턴·`source` 등)은 `MockNewsAdapter.fetch_query` 실제
구현(`app/adapters/news/mock.py:23–43`)을 그대로 따른다.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/knowledge/product-workflow.md` — "관심종목 분석 파이프라인" 섹션의 "뉴스 수집" 서술을
  쿼리 기반 경로(`fetch_query`, 회사명 쿼리)로 갱신한다.

## ADR Need

불필요. 기존 `fetch_query` 인터페이스를 활용하는 내부 경로 교체이며, 도메인 경계나 아키텍처
결정이 바뀌지 않는다(이슈 #248 "ADR 불요" 판단과 동일).

## Failure Record Need

불필요. 진단 완료된 구조적 결함의 경로 교체이며, 런타임 장애나 데이터 손상이 없다.

## Risk Level

Low. 변경 대상이 `app/domains/analysis/service.py`와 `tests/test_analysis_flow.py` 두 파일로
한정되고, 기존 도메인 경계·데이터 모델·외부 인터페이스가 바뀌지 않는다. `fetch_query`는
이미 `MockNewsAdapter`·`RSSNewsAdapter` 모두 구현하고 있어 어댑터 계층 변경이 없다.

## Expected Output

- `app/domains/analysis/service.py` 수정: `_RecordingNewsAdapter` 제거, `_process_asset`
  쿼리 기반 경로로 교체.
- `tests/test_analysis_flow.py` 수정: 쿼리 기반 픽스처 및 신규 테스트 케이스 추가.
- `docs/knowledge/product-workflow.md` 수정: 분석 파이프라인 뉴스 수집 서술 갱신.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 모두 통과.

## Rules

- 현재 브랜치(`fix/248-analysis-query-news`)를 유지한다. 새 브랜치를 만들지 않는다.
- 커밋하지 않는다. 파일 변경까지만 수행하고 커밋·push는 하지 않는다.
- 위 Implementation Scope 외 파일을 수정하지 않는다.
- 검증을 약화하지 않는다.
- 보호 파일을 수정하지 않는다.
- 가정이 있으면 구현 노트에 기록한다.
- 검증 결과를 완료 보고에 포함한다.
