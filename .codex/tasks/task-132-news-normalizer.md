# Codex Handoff Task

## Source Issue

BE #181(LLM 파이프라인 3단계 · News Normalizer 수집 잡 연결). 상위 Epic #174. 설계
`docs/designs/069-news-normalizer.md`. 기준 문서 `docs/knowledge/llm-data-pipeline.md`
(6.3·3단계·§7). Milestone: 데이터 수집 파이프라인 — 백엔드(#5). 선행 2단계 #179(processing_status
컬럼) 머지 완료.

## Task Summary

현재 분석 도메인(`analysis/service.py._create_new_items`)에 묶여 있고 어댑터를 재조회하는 뉴스
정규화를, `domains/news/`의 명시적 `NewsNormalizer`로 끌어와 뉴스 수집 잡
(`collect_news_job` → `NewsIngestionService`)에 인라인 배선한다. 정규화 성공 시 raw 행의
`processing_status`(2단계 컬럼)를 `normalized`로 전이시킨다. 가격 인라인 정규화 canonicalization은
명시적 `PriceNormalizer`로 추출(behavior-preserving)한다. 검증(`failed` 전이)은 4단계 몫이며 본
task 범위가 아니다.

## Goal

완료 시 참이어야 할 것:

- `app/domains/news/normalizer.py`에 `NewsNormalizer`가 있고, `RawNewsEvent`를
  `NewsItemCreate`로 매핑하며 symbol·market·URL·`published_at`을 canonicalize 한다.
- 뉴스 수집 잡 경로가 raw 저장 직후 정규화를 수행해 `NewsItem`을 만들고, 성공한 raw 행의
  `processing_status`가 `normalized`가 된다.
- asset을 해소하지 못한 raw 이벤트는 `NewsItem`을 만들지 않고 `fetched`로 남는다.
- `app/domains/prices/normalizer.py`에 `PriceNormalizer`가 있고, `prices/ingestion_service.py`가
  이를 사용한다(behavior-preserving).
- ruff·mypy·pytest 전부 통과.

## Background

- **가격 인라인 패턴(대칭 기준)**: `app/domains/prices/ingestion_service.py`가 raw 저장
  (`raw_price_service.save_raw`) 직후 `_validate_bars` → `price_repo.upsert_bars`로 정규화·검증을
  인라인 수행한다. 뉴스도 같은 방식으로 raw 저장 직후 정규화를 인라인 배선한다.
- **현재 뉴스 정규화 위치**: `app/domains/analysis/service.py._create_new_items`가
  `NewsAdapterResult`에서 `NewsItem`을 만든다(어댑터 재조회, URL로 `raw_news_event_id` 연결).
  본 task는 이 메서드를 **변경하지 않는다**(Scope B, Decision K). 새 정규화 경로는 수집 잡에만
  배선한다.
- **NewsItem 모델**: `app/domains/news/model.py`. `asset_id`는 not-null FK(`assets.id`),
  `raw_news_event_id`는 nullable FK, summary·sentiment·impact_level 등 LLM 파생 필드는 nullable.
  정규화 단계에서는 LLM 파생 필드를 채우지 않는다(후속 분석 단계 담당).
- **NewsItemCreate**: `app/domains/news/schema.py`. 매핑 대상 projection. `raw_news_event_id`,
  `asset_id`, `title`, `url`, `source`, `published_at`까지 채운다.
- **asset 해소**: `AssetRepository.get_by_symbol_market(symbol, market)`
  (`app/domains/assets/repository.py`). `assets`는 `(symbol, market)` unique. market은 거래소
  코드(`NASDAQ`/`KOSPI` 등)로 저장되므로 canonicalize에서 국가코드로 접지 않는다(Decision I).
- **processing_status 관례**: 2단계에서 `raw_news_events`에 `processing_status` 컬럼 추가 완료
  (String(20), server_default `fetched`, index). 값 도메인은
  `app/domains/ingestion/schema.ProcessingStatus`(`fetched`/`normalized`/`failed`/
  `skipped_duplicate`)를 **재사용**한다. 새 enum을 만들지 않는다. 정규화 성공 시 `normalized`로
  세팅한다(이 컬럼의 첫 writer).
- **URL dedup**: `NewsItemRepository.exists_by_url`이 이미 있다. 정규화 시 재사용한다.
- **timezone 관례**: `prices/ingestion_service.py._as_utc`가 tz-naive → UTC 보정 예시.
  `NewsNormalizer.normalize_published_at`도 동일 관례를 따른다.

## Implementation Scope

- `app/domains/news/normalizer.py`(신규): `NewsNormalizer`. `canonicalize_symbol`·
  `canonicalize_market`·`canonicalize_url`·`normalize_published_at`·`to_news_item_create`.
  순수·무상태(DB·세션 의존 없음).
- `domains/news/` 정규화 서비스 경로: raw 이벤트 → asset 해소 → URL dedup → `NewsItem` 생성 →
  raw 행 `processing_status='normalized'`. 신규 `NewsNormalizationService`(권장) 또는 기존 news
  서비스 확장 중 하나로 두되, 정규화·상태 전이 부수효과는 여기에 응집한다.
- `app/domains/raw_news/repository.py`: raw 행 상태 전이 메서드(`mark_normalized(event_id)` 류)
  추가.
- `app/domains/raw_news/ingestion_service.py`: `_collect_target`이 `save_with_symbol` 성공 직후
  정규화를 호출. `IngestionResult`에 `normalized_count` 추가.
- `app/domains/prices/normalizer.py`(신규): `PriceNormalizer`(`canonicalize_symbol`·
  `canonicalize_market`·`normalize_timestamp`). `prices/ingestion_service.py`가 이를 사용하도록
  위임 변경(behavior-preserving, 로직 이동만).
- 테스트(아래 Test Requirements).

## Out of Scope

- 뉴스 검증·`DataQualityStatus`·`ValidationErrorReason`·`failed` 세팅(4단계).
- `analysis/service.py._create_new_items` 수렴·리팩터(Decision K, 미변경).
- 기존 fetched `raw_news_events` 소급 정규화 배치 잡·스케줄러 신규 잡(v0.1 미포함).
- 가격 검증(`_validate_bars`) 이동·변경(4단계 정합 대상).
- market 국가코드 축약(US/KR)(Decision I).
- Feature·ContextBuilder·Gateway 로직, route·API 노출.
- `NewsItem`의 summary/sentiment 등 LLM 파생 필드 채우기.
- 신규 alembic revision(컬럼 추가 없음, 단일 head `c3d4e5f60058` 유지).

## Protected Files

`app/domains/analysis/*`(Decision K, 미변경), `app/domains/ingestion/*`(1단계 계약,
`ProcessingStatus`는 재사용만·수정 금지), `app/adapters/llm/*`, `app/domains/llm_context/*`,
`app/domains/llm_analysis/*`, `app/domains/decision_logs/*`, `app/domains/raw_prices/*`는
변경하지 않는다. Implementation Scope 밖 파일은 변경하지 않는다.

## Requirements

- `processing_status` 값 도메인은 `ProcessingStatus` enum을 따른다. 새 enum을 만들지 않는다.
- `NewsNormalizer` 순수 부분은 DB·세션·외부 API 의존 없이 동작한다.
- 정규화 성공 시에만 `normalized` 전이. asset 미해소 시 `NewsItem` 미생성·`fetched` 유지(Decision
  J), `failed` 세팅 금지.
- `PriceNormalizer` 추출은 behavior-preserving(기존 가격 테스트가 그대로 통과).
- 신규 코드는 타입 주석을 완전히 채워 mypy `no-untyped-def`를 피한다.
- 마이그레이션을 추가하지 않는다.

## Test Requirements

- News raw payload(`RawNewsEvent`)를 `NewsItem`으로 정규화할 수 있다(asset 해소·필드 매핑).
- canonicalization 단위 테스트: symbol 접미사·접두사 제거·대문자, market 대문자·trim, URL
  fragment·trailing slash 제거, `published_at` tz-naive → UTC.
- 뉴스 수집 잡(또는 `NewsIngestionService`) 경유 시 raw 저장 + `NewsItem` 생성 + raw 행
  `processing_status='normalized'` 전이(회귀).
- asset 미해소 raw 이벤트는 `NewsItem`을 만들지 않고 `fetched`로 남는다.
- URL 중복 시 `NewsItem`을 중복 생성하지 않는다(멱등).
- 기존 가격 수집·정규화 테스트와 분석 플로우 테스트가 계속 통과한다(회귀).

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

설계 `docs/designs/069-news-normalizer.md`가 근거다. 문서를 새로 쓰지 않는다. knowledge/도메인
문서 반영 여부는 orchestrator가 리뷰 시 판단한다.

## ADR Need

불필요. 지침 §7이 정의한 3단계 배선을 기존 도메인 관례 안에서 구현한다. Codex는 ADR을 작성하지
않는다.

## Failure Record Need

불필요.

## Risk Level

Medium. 기존 뉴스 수집 잡 경로에 정규화·상태 전이를 더한다. 주의점은 (1) 분석 플로우
(`_create_new_items`)를 건드리지 않기(Decision K, protected), (2) `ProcessingStatus` enum 재사용
(신설 금지), (3) asset 미해소 분기에서 `NewsItem` 미생성·`fetched` 유지(`failed` 금지), (4)
`PriceNormalizer` 추출을 behavior-preserving으로 유지(기존 가격 테스트 불변), (5) 검증 로직
(`failed`/`DataQualityStatus`)을 넣지 않기(4단계 범위), (6) 마이그레이션 미추가·단일 head 유지다.

## Expected Output

- 위 scope의 `NewsNormalizer`·정규화 서비스 경로·수집 잡 배선·상태 전이·`PriceNormalizer` 추출·
  테스트.
- 검증 3종(ruff·mypy·pytest) 통과 로그와 `alembic heads` 단일 head(`c3d4e5f60058`) 확인.
- 가정(canonicalization 규칙·asset 미해소 처리)과 검증 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files (특히 `app/domains/analysis/*`, `app/domains/ingestion/*`의
  `ProcessingStatus`).
- Do not add validation logic (`failed`/`DataQualityStatus`) or 4~7단계 로직.
- `ProcessingStatus` enum을 재사용하고 병렬 enum을 만들지 않는다.
- Do not add an alembic migration.
- Report assumptions and verification results.

## Stop Conditions

- `NewsItem.asset_id` not-null 제약과 asset 미해소 케이스가 기존 테스트 픽스처와 충돌하면 멈추고
  보고한다.
- 수집 잡 배선이 분석 플로우 테스트를 깨면(`_create_new_items` 미변경 원칙과 충돌) 멈추고 보고한다.
- `PriceNormalizer` 추출이 기존 가격 정규화 동작을 바꾸면 멈추고 보고한다.
