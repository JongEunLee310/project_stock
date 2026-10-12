# Codex Handoff Task

## Source Issue

#441 — [BE] RAG 1차: 뉴스 청킹·임베딩 job(`embed_documents`) (에픽 #438)

## Task Summary

`raw_news_events`를 임베딩 입력 텍스트로 만들고, 문자 수 기준으로 청킹하고, `Embedder`로
임베딩해 `VectorStore`에 적재하는 인덱서와 워커 job을 만든다. 매시 수집 뒤 실행하도록 스케줄에
등록하고, 기존 문서 backfill용 스크립트를 둔다.

## Goal

완료 시 다음이 참이어야 한다.

- `embed_documents_job()`이 임베딩이 필요한 문서만 골라 청크를 적재하고 `job_runs`에 결과를 남긴다.
- 같은 문서를 다시 실행하면 아무것도 바꾸지 않는다(멱등). 임베딩 입력이 바뀐 문서만 다시 적재한다.
- 임베딩 엔드포인트가 실패하면 job은 실패로 기록하고 예외를 다시 던지지 않는다. 다음 실행에서
  같은 문서가 다시 대상이 된다.
- 스케줄러에 `embed_documents`가 `"20 * * * *"`로 등록된다.
- `scripts/backfill_rag_embeddings.py`로 남은 문서를 반복 처리할 수 있다.

## Background

- 설계 정본: `docs/designs/438-rag-research-qa.md` §2.1(원본은 `raw_news_events`), §3(인덱싱),
  §6(모듈 경계). 반드시 먼저 읽는다.
- 경계 규칙(ADR-018 R1·R2): rag는 다른 도메인 테이블을 직접 쿼리하지 않는다. `raw_news`와 `news`의
  repository에 읽기 함수를 추가해 그것을 호출한다. rag 청크 조회와 쓰기는 `VectorStore`를 거친다.
- #440·#450(머지됨)이 만든 것
  - `get_embedder()`, `get_vector_store(db)`(`app/adapters/factory.py`)
  - `VectorStore`(`upsert`, `delete_by_source`, `search`)와 `PgVectorStore`, `InMemoryVectorStore`
  - `ChunkRecord`, `ChunkFilter`, `ChunkHit`(`app/adapters/vector/types.py`)
  - `EmbeddingError`(`app/adapters/embedding/exceptions.py`)
  - 실제 임베딩은 로컬 Ollama `bge-m3`(CPU에서 1,500자 청크당 약 2.8초)
- 종목 매핑: 원문 1건이 `news_items` 여러 행(종목별)으로 나뉜다. `news_items.raw_news_event_id`로
  연결된 행의 `asset_id`를 모아 `asset_ids`로 쓴다(`app/domains/news/model.py:13-16`).
- job 관례: `app/worker/jobs/news.py`의 `collect_news_job`(`SessionLocal`, `JobRunService.start`,
  `succeed`, `fail`, `finally: db.close()`). `JobRunService.succeed(job_run_id)`는 결과 인자를 받지
  않으므로, 처리 통계는 `start`의 metadata가 아니라 로그로 남기고 필요하면 job 함수 반환값으로 둔다.
- 스케줄 등록 관례: `app/scheduler/registry.py`의 `ScheduleDefinition`과 `FunctionSchedulerJob`
- backfill 스크립트 관례: `scripts/backfill_news_categories.py`
- 의존성 추가는 없다. `uv add`, `uv sync`, 네트워크, `git fetch`, docker 명령을 하지 않는다.

## Implementation Scope

1. **임베딩 입력 규칙**(`app/domains/rag/indexing.py`, 순수 함수)
   - `compose_embedding_text(title, body, summary) -> tuple[str, ChunkContentQuality]`

     | 조건 | 입력 텍스트 | quality |
     |---|---|---|
     | `body`(공백 제거) 길이가 `MIN_FULL_BODY_CHARS`(200, 가정) 이상 | `title` + 빈 줄 + `body` | `FULL` |
     | 위가 아니고 `summary`가 있음 | `title` + `body`(있으면) + `summary`를 빈 줄로 연결 | `SUMMARY` |
     | 그 밖 | `title` + `body`(있으면) | `TITLE_ONLY` |

     세 번째 행은 "제목 수준의 정보만 있는 문서"를 뜻한다. 설계 §3 표의 "둘 다 없음"을 짧은 본문까지
     포함하도록 구체화한 것이다.
   - `chunk_text(text, size=CHUNK_SIZE_CHARS, overlap=CHUNK_OVERLAP_CHARS) -> list[str]`: 문자 수 기준,
     기본 1,500자와 겹침 150자(가정). 빈 텍스트는 빈 목록이다. 마지막 조각이 겹침보다 짧아 앞 청크에
     완전히 포함되면 만들지 않는다.
   - `embedding_input_hash(text) -> str`: sha256 hex
2. **`VectorStore` 확장**(`app/adapters/vector/`)
   - ABC에 `get_content_hashes(source_type, source_ids: list[int], embedding_model) -> dict[int, str]`을
     추가한다. 원문별 `content_hash`를 돌려주며 청크가 없는 원문은 키가 없다. 한 원문의 청크는 같은
     해시를 가지므로 아무 청크의 값을 써도 된다.
   - `PgVectorStore`와 `InMemoryVectorStore`에 구현하고, #440의 공용 시나리오 테스트에 이 메서드를
     추가한다. 저장소 중립성을 유지하려고 rag repository가 아닌 `VectorStore`에 둔다(나중에 전용
     vector DB로 옮기면 해시도 그쪽 payload에 있다).
3. **다른 도메인 repository 읽기 함수**
   - `RawNewsRepository.list_after_id(after_id: int, limit: int) -> list[RawNewsEvent]`: `id` 오름차순
   - `NewsItemRepository.list_by_raw_event_ids(raw_event_ids: list[int]) -> list[NewsItem]`
     (클래스 이름은 실제 파일의 이름을 따른다)
4. **인덱서**(`app/domains/rag/indexing_service.py`)
   - `EmbeddingIndexer(db, embedder, vector_store)`
   - `run(max_documents: int = 100, scan_page_size: int = 500) -> IndexingResult`
     - `raw_news_events`를 `id` 오름차순으로 페이지 단위로 훑는다. 각 원문의 입력 텍스트와 해시를
       계산하고 `get_content_hashes` 결과와 비교한다. 같으면 건너뛴다.
     - 해시가 다르거나 없는 원문을 `max_documents`개까지 모은다. 끝까지 훑었거나 개수를 채우면 멈춘다.
     - 모은 원문의 청크 텍스트를 한 번의 `embedder.embed` 호출로 임베딩한다.
     - 원문마다 `delete_by_source` 후 `upsert`하고, 전체를 한 번 `commit`한다.
     - `published_at`은 원문 `published_at`, 없으면 `collected_at`을 쓴다.
     - `asset_ids`는 연결된 `news_items`의 `asset_id`를 중복 없이 오름차순으로 넣는다.
   - `IndexingResult`(dataclass): `scanned`, `embedded_documents`, `chunks_written`, `unchanged`,
     `has_more`(`max_documents`를 채워 멈췄는지)
   - 모든 원문을 매번 훑는 방식은 현재 규모(수천 건)에서 충분하다고 가정한다. 성능이 문제가 되면
     워터마크로 바꾼다(이번 범위 아님).
5. **워커 job**(`app/worker/jobs/rag.py`)
   - `embed_documents_job(max_documents: int = 100) -> IndexingResult | None`
   - `JobRunService.start("embed_documents", {"max_documents": ...})`
   - `EmbeddingError`이면 rollback 후 `fail(job_run_id, 메시지)`를 기록하고 `None`을 반환한다(다시
     던지지 않음). 그 밖의 예외는 기존 관례대로 `fail` 후 다시 던진다.
   - 성공하면 `succeed` 후 결과를 로그로 남기고 반환한다.
6. **스케줄 등록**: `app/scheduler/registry.py`에 `embed_documents`, cron `"20 * * * *"`(가정, 수집
   job `"0 * * * *"` 뒤), `enabled=True`
7. **backfill 스크립트**: `scripts/backfill_rag_embeddings.py`. 인덱서를 `has_more`가 거짓이 될 때까지
   반복 실행하고 회차마다 처리 건수를 출력한다. `--max-documents` 인자(기본 100)를 받는다.
8. **PR #451 리뷰 S1 정리**: `tests/rag/test_embedding_migration.py`의
   `test_embedding_migration_head_and_model_dimension`에서 `get_heads()` 비교를 지우고, revision의
   `down_revision`과 모델 차원이 `EMBEDDING_DIMENSIONS`와 일치하는지만 검증한다. `== 1024` 리터럴도
   지운다.

## Out of Scope

- Q&A 서비스·API(#442), Obsidian(#443)
- 마이그레이션 추가
- `raw_news`·`news` 도메인의 기존 함수 동작 변경(읽기 함수 추가만 허용)
- 워터마크·병렬 처리 같은 성능 최적화

## Protected Files

없음.

## Requirements

- rag 코드에서 `RawNewsEvent`·`NewsItem`을 직접 `select`하지 않는다. 각 도메인 repository 함수를
  쓴다(ADR-018 R2). 모델 타입을 import해 타입 주석에 쓰는 것은 허용한다.
- 임베딩 호출 전에는 DB 쓰기를 하지 않는다. 임베딩이 실패하면 아무것도 바뀌지 않아야 한다.
- 모든 공개 함수에 타입 주석을 단다.
- 주석은 이유가 분명하지 않은 곳에만 최소한으로 쓴다.

## Test Requirements

- 단위(`indexing.py`)
  - `compose_embedding_text`: 200자 경계(199·200), summary 보강, 짧은 본문과 summary 없음, 본문
    없음과 summary 없음
  - `chunk_text`: 빈 텍스트, 한 청크, 경계 길이(1,500·1,501), 겹침 내용 일치, 꼬리 조각 처리
- 인덱서 통합(SQLite + `InMemoryVectorStore` + `MockEmbedder`)
  - 신규 적재: 청크 수, `asset_ids`(여러 종목, 연결 없음), `content_quality`, `published_at` fallback
  - 재실행 멱등: 두 번째 실행에서 `embedded_documents == 0`, 청크 변화 없음
  - 입력 변경: `body`를 바꾸면 해당 원문만 다시 적재되고 이전 청크가 남지 않음
  - `max_documents` 제한과 `has_more`
  - 임베딩 실패: `embed`가 `EmbeddingError`를 던지는 가짜 임베더로 DB와 저장소가 바뀌지 않음
- job: 성공 시 `job_runs` 성공 기록, `EmbeddingError` 시 실패 기록과 예외 미전파, 그 밖의 예외는
  실패 기록과 예외 전파(`tests/test_worker_jobs.py`의 기존 news job 테스트 방식을 따른다)
- 실제 경로 관통(`quality-process-policy.md` Real-Contract Fixtures): 최소 한 테스트는
  `raw_news_events`와 `news_items`를 실제 repository나 기존 생성 경로로 만들고, 인덱서와
  `search`까지 이어서 해당 종목 필터로 원문이 검색되는지 확인한다.
- `postgres` 마커: `PgVectorStore.get_content_hashes` 검증을 공용 시나리오에 포함한다.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

- 로컬에 pgvector Postgres가 있으면 `TEST_POSTGRES_URL=... uv run pytest -m postgres`도 실행한다.
  없으면 실행하지 못했다고 결과에 명시한다.

## Documentation Impact

설계 438 §3에 위 1번 표(짧은 본문 처리)와 `get_content_hashes`, 전체 스캔 가정을 반영한다. 이
문서는 protected가 아니다.

## ADR Need

불필요. ADR-018의 적용이다.

## Failure Record Need

불필요.

## Risk Level

Medium — 기존 job·repository 패턴을 따르는 신규 job과 읽기 함수 추가다. 스키마, 의존성, CI 변경은
없다.

## Expected Output

- 현재 브랜치 `feat/441-embed-documents-job`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋 상태로 두고 보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, 가정, 검증 명령별 결과, 실행하지 못한 검증

## Stop Conditions

- 설계·이 핸드오프와 다르게 구현해야 하는 상황
- 의존성 추가나 마이그레이션이 필요한 상황
- 기존 테스트가 이 변경과 무관한 이유로 실패하는 상황
- 샌드박스 권한 부족

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
