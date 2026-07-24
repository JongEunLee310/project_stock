# Codex Handoff Task

## Source Issue

#397 — 뉴스 인텔리전스 파이프라인 1: 수집(source_documents 적재). 트래킹 #391의 1단계.

## Task Summary

이미 쌓인 `raw_news_events`(약 2,622건)를 `news_insights.source_documents`로 적재하는 경로를 신규 구현한다. 현재 이 테이블은 `seed.py`로만 채워진다. 재실행이 안전한 멱등 적재여야 한다.

## Goal

- `source_documents`에 `raw_news_events` 원천에서 파생한 실데이터가 적재된다.
- 같은 입력으로 두 번 실행해도 중복 행이 생기지 않는다(멱등).
- 스키마·모델·마이그레이션 변경이 없다.

## Background

**착수 전 `docs/designs/397-collection-source-documents.md`를 읽어라.** 정본 선택·필드 매핑·NOT NULL 충돌 처리가 모두 확정돼 있다. 요지는 다음과 같다.

- 정본은 `raw_news_events`다(`app/domains/raw_news/model.py`). `news_items`는 asset별 파생 뷰라 문서 단위 중복이 생겨 제외한다.
- 이번 범위는 `NEWS`만이다. 공시(`DISCLOSURE`)는 저장 경로가 없어 제외한다.
- 이번 단계는 **방향 A(단순 적재)**다. `source_name`은 원천 값 그대로, `source_reliability`는 전건 중립 `0.5`(미평가)로 둔다. 실매체명 추출·정규화와 신뢰도 티어링은 후속 #403이며 **이 작업의 범위가 아니다.**

## Implementation Scope

- 신규 적재 로직 — 위치는 재량이나 도메인 안이어야 한다(예: `app/domains/news_insights/ingestion.py`, 또는 `NewsInsightsRepository`에 메서드 추가). 기존 도메인 구조와 일관되게 둔다.
  - `raw_news_events` 조회 → `source_documents` 매핑 → 멱등 적재를 조율하는 진입 함수.
  - 단건 매핑 함수. `body`가 없는 원천은 `None`을 반환해 적재에서 제외한다.
  - 적재·스킵(body 없음)·중복(이미 존재) 건수를 담는 결과 projection.
- `content_hash` 산식: 정규화된 `source_url` + `title`의 SHA-256 hex(64자). URL 정규화는 `app/domains/news/normalizer.py`의 `NewsNormalizer.canonicalize_url`을 재사용한다.
- 수동 실행 진입점(관리 함수 또는 테스트에서 호출 가능한 형태). 스케줄러·주기 실행은 이번 범위가 아니다.

## Out of Scope

- 스키마·모델·마이그레이션 변경. `source_documents` 모델은 그대로 쓴다.
- `raw_news_events`·`news_items` 수정 — `processing_status` 포함 어떤 컬럼도 건드리지 않는다.
- 실매체명 추출·`source_name` 정규화·신뢰도 티어링(#403).
- 공시(`DISCLOSURE`), 추출·군집·해석 등 이후 단계(#398~).
- `source_reliability`를 `0.5` 외의 값으로 채우는 로직.
- 스케줄러·워커 주기 실행 연결.

## Protected Files

없음.

## Requirements

매핑은 설계 §3 표를 따른다. 핵심을 다시 적는다.

- `document_type` = `NEWS` 고정. `source_name` = `raw.source`. `source_url` = `raw.url`. `title` = `raw.title`. `collected_at` = `raw.collected_at`.
- `external_id` = `raw.id`의 문자열화(nullable 필드지만 재적재 추적용으로 채운다).
- `raw_content` = `raw.body`. `body`가 `None`이면 **그 원천은 적재하지 않는다.** `title`로 대체하지 않는다.
- `normalized_content` = `None`(정규화는 추출 단계 책임).
- `language` = `"ko"` 고정.
- `published_at` = `raw.published_at`. `None`이면 `raw.collected_at`으로 대체한다.
- `content_hash` = 위 산식. `unique` 제약이 멱등 키다. **이미 같은 해시가 있으면 재적재하지 않는다.**
- `source_reliability` = `0.5`.
- `processing_status` = `PENDING`.
- 결과로 적재·스킵·중복 건수를 집계해 반환한다.
- 파생 뷰(projection) 타입 이름에 `DTO`를 쓰지 않는다(도메인 관례).

## Test Requirements

- 매핑 정확성 — 각 필드가 규칙대로 채워지는지 값으로 단언한다(존재만 확인하지 않는다).
- `body`가 `None`인 원천은 적재에서 제외되고 스킵 건수에 잡힌다.
- `published_at`이 `None`인 원천은 `collected_at`으로 대체된다.
- **멱등** — 같은 원천으로 적재를 두 번 실행해도 `source_documents` 행 수가 늘지 않는다. 이번 작업의 핵심이므로 회귀 자리를 반드시 둔다.
- `content_hash` 충돌(같은 정규화 URL+title) 시 중복으로 스킵된다.
- 원천이 하나도 없으면 0건 적재로 끝난다.
- 테스트는 기존 `tests/test_news_insights.py`의 인메모리 세션 픽스처 패턴을 따른다. 실제 DB 기동은 필요 없다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

`docs/designs/397-collection-source-documents.md`는 이미 작성돼 있다. **고치지 않는다.** 다른 문서 변경은 없다.

## ADR Need

불요. 기존 고정 계약·모델에 데이터를 채우는 작업이고 스키마 변경이 없다.

## Failure Record Need

불요. 실패한 접근을 대체하는 것이 아니라 부재하던 생산 경로를 만드는 작업이다.

## Risk Level

Low~Medium — 신규 적재 경로이나 스키마 변경이 없고, 멱등·NOT NULL 처리가 설계에 확정돼 있다.

## Expected Output

- 현재 브랜치(`feat/397-collection-source-documents`) 위에 쌓는 커밋(한국어 메시지). push·PR은 하지 않는다.
- 검증 3종 결과 보고.
- 테스트 픽스처 기준으로 적재·스킵·중복 건수가 규칙대로 나오는지 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치(`feat/397-collection-source-documents`)를 유지한다. 자체 브랜치 생성·push·PR을 하지 않는다.
