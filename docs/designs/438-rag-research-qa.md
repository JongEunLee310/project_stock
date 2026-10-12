# BE 설계: RAG 리서치 에이전트 1차 — 종목 리서치 Q&A — 에픽 #438

상태: **설계 초안(Draft)** — 2026-10-12. 하위 이슈 #439~#444. FE 소비
`project_stock_frontend#308`. 배치·저장소 결정과 분리·전환 트리거는 ADR-018을 따른다.

이 문서는 1차 범위(pgvector 기반, 임베딩·벡터 어댑터, 뉴스 임베딩 job, Q&A API, Obsidian
쓰기, 평가 세트)의 모델·계약·책임을 스켈레톤 수준으로 확정한다. 실제 쿼리와 비즈니스
로직은 담지 않는다. 리터럴에는 출처(`파일:행` 또는 확인 명령)를 붙였고, 출처가 없는 값은
"가정"으로 표기했다. 가정 값은 구현 전에 생산자 코드나 외부 문서로 검증한다.

## 배경

리서치 상세에서 받은 질문에 수집된 근거를 인용해 답하는 기능을 만든다. 2~5차에서 공시,
투자 원칙, 개념, 논문을 지식으로 수집하므로(#445~#448), 1차는 그 확장을 받칠 수 있는
기반과 뉴스만으로 끝까지 동작하는 수직 슬라이스를 목표로 한다.

설계 중 확인한 코드 사실 가운데 범위에 영향을 주는 것은 다음과 같다.

| 사실 | 출처 | 설계 영향 |
|---|---|---|
| 테스트 DB는 SQLite 인메모리다 | `tests/conftest.py:33` | pgvector 타입을 SQLite에서 대체하고, pgvector 통합 테스트는 별도 CI 잡으로 돌린다(§7) |
| `source_documents` 적재 함수 `run_pipeline`은 호출처가 없다 | `app/domains/news_insights/pipeline.py:55`, `grep -rn "run_pipeline" app scripts` 결과 정의만 존재 | 코퍼스 원본을 `source_documents`가 아니라 `raw_news_events`로 잡는다(§2.1) |
| `news_collection` job이 매시 정각 실행된다 | `app/scheduler/registry.py:61-64`(`cron="0 * * * *"`) | 임베딩 job을 수집 뒤 시각에 둔다(§3) |
| `raw_news_events.body`는 nullable이다 | `app/domains/raw_news/model.py:20` | 제목만 있는 문서를 `TITLE_ONLY`로 다룬다 |
| 원문 1건이 종목별 `news_items` 여러 행으로 나뉜다 | `app/domains/news/model.py:13-16`(`raw_news_event_id`, `asset_id`) | 청크에 `asset_ids` 배열을 둔다 |
| `LLMGateway.complete_json(task_type, payload, schema, system_prompt)` | `app/adapters/llm/gateway.py:59-66` | 생성 경로에 재사용한다 |
| LLM 클라이언트는 `OPENAI_BASE_URL` 프록시를 쓸 수 있다 | `app/core/config.py:17-19` | 임베딩은 이 프록시를 쓰지 않고 로컬 Ollama로 만든다(§9 OQ1, #450) |

## 1. 인프라

- Postgres 이미지를 `postgres:16-alpine`(`docker-compose.yml:63`)에서 `pgvector/pgvector:pg16`으로
  바꾼다. 배포 compose는 이 repo에 없다(`ls docker-compose*` 결과 1개). 배포 환경에서의 교체는
  배포 설정을 관리하는 쪽에 후속으로 알린다.
- Alembic 마이그레이션에서 `vector` 확장을 활성화하고 §2.2 테이블을 만든다. 마이그레이션은
  단일 head를 유지한다.
- 의존성으로 `pgvector`(SQLAlchemy 타입)를 추가한다. 토큰 계산용 `tiktoken`은 추가하지 않고
  청킹은 문자 수 기준으로 한다(§3).

## 2. 데이터 모델

### 2.1 코퍼스 원본 — `raw_news_events`

1차 코퍼스의 원본은 `raw_news_events`다. 문서 1건이 행 1건이고(`url` unique), 매시 수집되어
실제로 채워져 있다. `source_documents`는 설계 397에서 뉴스 인텔리전스의 문서 단위 정본으로
정했지만 적재 경로가 스케줄되어 있지 않아 지금은 코퍼스로 쓸 수 없다. 나중에
`source_documents` 적재가 상시 운영되면 원본 전환 여부를 다시 판단한다(§9 OQ3).

종목 매핑은 `news_items.raw_news_event_id`로 원문에 연결된 행들의 `asset_id`를 모아 만든다.
rag는 두 테이블을 읽기만 하며, 다른 도메인의 repository 공개 함수를 거친다(ADR-018 R2).

### 2.2 `document_chunks` (신규, `app/domains/rag/model.py`)

| 필드 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `id` | int | PK | |
| `source_type` | str(20) | not null | `ChunkSourceType` 값. 1차는 `NEWS`만 |
| `source_id` | int | not null | 1차는 `raw_news_events.id` |
| `chunk_index` | int | not null | 문서 안 순번, 0부터 |
| `content` | text | not null | 청크 원문. 인용 발췌에 쓴다 |
| `content_quality` | str(20) | not null | `ChunkContentQuality` 값 |
| `embedding` | vector(1024) | not null | SQLite에서는 JSON variant(§7). #450에서 1536→1024 |
| `embedding_model` | str(100) | not null | 생성한 모델 식별자 |
| `asset_ids` | int[] | not null, 기본 빈 배열 | SQLite에서는 JSON variant |
| `published_at` | timestamptz | nullable | 원문 `published_at`, 없으면 `collected_at` |
| `content_hash` | str(64) | not null | 임베딩 입력 텍스트의 sha256. 변경 감지용 |
| `created_at` | timestamptz | not null | |

- unique: (`source_type`, `source_id`, `chunk_index`, `embedding_model`)
- 인덱스: `embedding` HNSW(`vector_cosine_ops`), `asset_ids` GIN, `published_at` btree,
  (`source_type`, `source_id`) btree. 앞의 두 인덱스는 Postgres 전용이다.
- `content_hash`는 청크 쪽에서 계산한다. `source_documents.content_hash`는 URL과 제목의
  해시라서(`app/domains/news_insights/ingestion.py:58-60`) 본문 변경을 감지하지 못한다.
- `vector` 차원 1024는 `bge-m3`의 출력 차원이다(실측: 2026-10-12 `ollama/ollama:0.40.3`의
  `/v1/embeddings` 응답 길이). 차원 상수는 `app/domains/rag/types.py`의 `EMBEDDING_DIMENSIONS`다.

### 2.3 enum (`app/domains/rag/types.py`)

| enum | 값 | 비고 |
|---|---|---|
| `ChunkSourceType` | `NEWS` | 2차 이후 `KNOWLEDGE` 추가 예정(#445) |
| `ChunkContentQuality` | `FULL`, `SUMMARY`, `TITLE_ONLY` | §3 본문 결정 규칙의 결과 |

## 3. 인덱싱 — `embed_documents` job

**대상 선정.** 현재 `EMBEDDING_MODEL` 기준으로 청크가 없는 `raw_news_events`를 고른다.
이미 청크가 있는 문서는 다시 계산한 `content_hash`가 다를 때만 재적재한다. 1회 배치 크기는
100건이다(가정).

**본문 결정 규칙.**

| 조건 | 임베딩 입력 | `content_quality` |
|---|---|---|
| `body` 길이가 200자 이상(가정) | `title` + `body` | `FULL` |
| `body`가 200자 미만이거나 없고, 연결된 `news_items.summary`가 있음 | `title` + `body`(있으면) + `summary` | `SUMMARY` |
| 둘 다 없음 | `title` | `TITLE_ONLY` |

**청킹.** 문자 수 기준으로 자른다. 청크 크기 1,500자, 겹침 150자(가정). 뉴스 대부분이
1~2청크가 될 것으로 본다(가정, #444 평가에서 분포를 기록한다).

**스케줄.** `app/scheduler/registry.py`에 `embed_documents`를 등록한다. cron은
`"20 * * * *"`(가정)로 둔다. 수집 job(`"0 * * * *"`) 뒤에 실행하기 위해서다. 실행 기록은 기존
`JobRunService`(`app/worker/jobs/news.py:3,10-25`의 사용 방식)를 따른다.

**갱신과 정리.**
- 해시가 바뀐 문서는 `delete_by_source` 후 다시 적재한다. 한 트랜잭션으로 처리한다.
- `EMBEDDING_MODEL`이 바뀌면 새 모델 기준으로 청크가 없는 상태가 되므로 같은 job이 전량을
  다시 적재한다. 이전 모델 청크 정리는 `purge_other_models` 수동 스크립트로 한다. 검색은 항상
  현재 모델의 청크만 대상으로 하므로 정리 전에도 결과가 섞이지 않는다.
- 임베딩 API가 실패한 배치는 기록만 하고 건너뛴다. 다음 실행에서 자연스럽게 다시 대상이 된다.

**backfill.** 기존 문서는 같은 job을 수동으로 반복 실행해 채운다. 별도 API는 만들지 않는다.

**예산.** 임베딩 호출은 `LLM_DAILY_CALL_LIMIT`(`app/core/config.py:22`) 집계에 넣지 않는다.
배치 job의 호출 수가 대화형 LLM 한도를 소진하지 않게 하기 위해서다. 비용 관측은 job 실행
기록의 처리 건수로 대신한다.

## 4. 어댑터

### 4.1 `Embedder` (`app/adapters/embedding/`)

- `Embedder` ABC
  - `model_name -> str` — 청크에 기록할 모델 식별자
  - `dimensions -> int`
  - `embed(texts: list[str]) -> list[list[float]]` — 입력 순서를 보존한 벡터 목록
- `OpenAIEmbedder` — OpenAI 호환 `/v1/embeddings` 호출. 1차 대상은 로컬 Ollama의 `bge-m3`다
  (ADR-018 §2a). 배치 상한은 100건(가정)이고, `dimensions` 인자를 보낸다(Ollama 지원 실측).
- `MockEmbedder` — 텍스트 해시로 만든 결정적 벡터. 같은 텍스트면 같은 벡터를 낸다.
- factory: `get_embedder()`. 설정 `EMBEDDING_PROVIDER: Literal["openai", "mock"]`(`openai`는
  OpenAI 호환 API를 뜻한다), `EMBEDDING_MODEL`(기본 `bge-m3`), `EMBEDDING_BASE_URL`(기본
  `http://localhost:11434/v1`, compose 안에서는 `http://ollama:11434/v1`), `EMBEDDING_API_KEY`.
  `OPENAI_BASE_URL`은 상속하지 않는다. API 키는 `EMBEDDING_API_KEY`, `OPENAI_API_KEY` 순으로
  쓰고, 둘 다 없으면서 base URL이 있으면 더미 키를 쓴다. `tests/conftest.py`의
  `_PROVIDER_SETTINGS`에 `EMBEDDING_PROVIDER`를 추가해 테스트에서 mock으로 고정한다.

### 4.2 `VectorStore` (`app/adapters/vector/`)

- `VectorStore` ABC
  - `upsert(chunks: list[ChunkRecord]) -> int` — unique 키 기준 삽입·갱신, 처리 건수 반환
  - `delete_by_source(source_type, source_id) -> int`
  - `search(query_vector, filters: ChunkFilter, k: int) -> list[ChunkHit]` — 코사인 유사도
    내림차순
- `ChunkFilter`(값 객체): `asset_id: int | None`, `source_types: tuple[ChunkSourceType, ...]`,
  `published_after: datetime | None`, `embedding_model: str`. SQL 표현을 담지 않는다(ADR-018 R4).
- `ChunkHit`: `chunk_id`, `source_type`, `source_id`, `chunk_index`, `content`,
  `content_quality`, `published_at`, `score`
- `PgVectorStore` — 실제 구현체
- `InMemoryVectorStore` — 테스트와 로컬 mock용 구현체. 필터를 Python으로 평가한다. SQLite
  테스트에서 서비스·API를 검증하는 데 쓰고, 인터페이스가 저장소 중립인지 확인하는 역할도 한다.
- factory: `get_vector_store(db)`. 설정 `VECTOR_STORE_PROVIDER: Literal["pgvector", "mock"]`.
  테스트에서는 `mock`으로 고정한다.

### 4.3 `ObsidianWriter` (`app/adapters/obsidian/writer.py`)

구현체가 하나라 ABC는 두지 않는다. 3차 읽기(#446)에서 필요하면 그때 분리한다.

- `write_research_note(note: ResearchNote) -> Path` — 새 파일을 만들고 경로를 반환한다.
  같은 이름이 있으면 `-2`, `-3` 접미사를 붙이며 기존 파일은 열지 않는다.
- 설정: `OBSIDIAN_VAULT_PATH: str | None`(미설정이면 비활성), `OBSIDIAN_EXPORT_DIR`(기본
  `stock-agent`)
- 경로: `{vault}/{export_dir}/research/{SYMBOL}/{YYYY-MM-DD}-{question-slug}.md`. slug는
  질문 앞부분 최대 40자(가정)를 파일명 안전 문자로 바꾼 것이다.
- 노트 구성: frontmatter(`symbol`, `question`, `generated_at`, `embedding_model`, `source_count`,
  `insufficient_evidence`, `tags: [stock-agent, research-qa]`), 본문(질문, 답변과 인용, 한계,
  근거 목록, `[[SYMBOL]]` wikilink)
- compose: 로컬 BE 서비스에만 vault 볼륨을 마운트한다. 경로는 환경변수로 받는다.

## 5. Q&A 서비스와 API

### 5.1 API

| Method · Path | request | response | Auth | 영속 |
|---|---|---|---|---|
| `POST /api/v1/assets/{asset_id}/research-qa` | `ResearchQARequest` | `ResearchAnswer` | Required | No(노트 저장 선택) |

경로는 기존 리서치 계열 관례(`app/api/v1/endpoints/assets.py`의 `/{asset_id}/research-coverage`
등)를 따른다. 응답은 공통 `ApiResponse` 형식이다.

`ResearchQARequest`
- `question: str` — 1~500자(가정)
- `lookback_days: int` — 기본 90, 범위 1~365(가정)
- `save_to_obsidian: bool` — 기본 false

`ResearchAnswer`
- `answer_points: list[AnswerPoint]` — `text: str`, `citations: list[int]`
- `limitations: str | None`
- `insufficient_evidence: bool`
- `evidence: list[EvidenceItem]` — `id: int`(인용 번호, 1부터), `source_type`, `source_id`,
  `title`, `source_name`, `source_url`, `published_at`, `excerpt`, `score`, `content_quality`
- `generated_at: datetime`
- `obsidian_note_path: str | None`

2차(#445)에서 `AnswerPoint.kind`와 인용 종류 구분이 추가될 예정이다. 1차 응답 필드는 그대로
두고 필드를 추가하는 방식으로 확장한다.

### 5.2 `ResearchQAService` (`app/domains/rag/service.py`)

- `ask(asset_id, user_id, request) -> ResearchAnswer` — asset 확인, 검색, 생성, 인용 검증,
  선택적 노트 저장을 묶는다.
- `_retrieve(asset_id, question, lookback_days) -> list[EvidenceItem]` — 질문 임베딩, 검색,
  후처리
- `_generate(asset, question, evidence) -> ResearchQAResult` — projection 구성과 게이트웨이 호출
- `_validate_citations(result, evidence) -> ResearchQAResult` — §5.4 규칙 적용

검색 후처리 규칙(모두 가정, #444 평가 결과로 조정한다)
- 후보 k=20을 가져온다.
- 유사도가 0.3 미만인 청크는 버린다.
- 원문 1건당 최대 2청크만 남긴다.
- `TITLE_ONLY` 청크 점수에 0.8을 곱한다.
- 최종 상위 8개를 근거로 쓴다.

### 5.3 LLM 배선

- `LLMTaskType.RESEARCH_QA`를 추가한다(`app/adapters/llm/types.py:8-19`).
- `LLM_TASK_ROUTES`에 `RESEARCH_QA: TaskRoute(launch="cloud", future_primary="cloud")`를
  추가한다(`app/adapters/llm/router.py:13`). 근거 종합과 인용 준수가 중요해 로컬 이관 1순위가
  아니라고 본다(가정).
- `ResearchQASnapshot(CloudSafePayload)`를 `app/adapters/llm/privacy.py`에 추가한다. 필드는
  `symbol`, `asset_name`, `question`, `evidence`(번호, 제목, 매체, 발행일, 발췌)로 한정한다.
  뉴스는 공개 데이터다. 질문은 사용자 자유 텍스트라 그대로 전송되며, 선례는
  `DecisionAssistSnapshot`(`privacy.py:53`)이다. 내부 식별자(`user_id`, `asset_id`, 청크 id)는
  싣지 않는다.
- LLM 결과 모델 `ResearchQAResult(BaseModel)`: `answer_points`, `limitations`,
  `insufficient_evidence`
- 프롬프트 `app/adapters/llm/prompts/research_qa.py`(`PROMPT_VERSION` 포함). 언어 지시는
  `prompts/language.py`를 재사용한다. 원칙은 다음과 같다.
  - 제공된 근거로만 답한다.
  - 주장마다 근거 번호를 붙인다.
  - 근거가 부족하면 부족하다고 답한다.
  - 매수·매도를 권유하거나 목표 가격을 제시하지 않는다.

### 5.4 근거 없는 생성 차단과 인용 검증

- 후처리 뒤 근거가 0건이면 LLM을 호출하지 않는다. `insufficient_evidence=true`, 빈
  `answer_points`, 사유를 담은 `limitations`로 응답한다.
- 근거 목록에 없는 인용 번호는 제거한다.
- 유효 인용이 하나도 없는 `answer_point`는 버린다.
- 모든 point가 버려지면 `insufficient_evidence=true`로 바꾼다.
- 버린 point 수를 로그로 남긴다(#444의 품질 지표).

### 5.5 실패 처리

| 상황 | 처리 | 출처 |
|---|---|---|
| asset 없음 | 404 `ASSET_NOT_FOUND` | `app/core/error_codes.py:12` |
| 입력 검증 실패 | 422(기존 검증 처리) | |
| 질문 임베딩 실패 | 503 `RAG_EMBEDDING_UNAVAILABLE`(신규 코드, 가정) | 검색 없이는 답할 수 없으므로 실패로 응답한다 |
| LLM 호출 실패 | 200, `insufficient_evidence=true`, 근거 목록은 채워서 반환, `limitations`에 생성 실패 명시 | `assist_service.py:49-55`의 안전 실패 관례를 따른다 |
| 노트 저장 실패 | 200, `obsidian_note_path=null`, 경고 로그 | 저장은 부가 기능이다 |

## 6. 모듈 경계 (ADR-018 R1~R5)

- rag 외부 노출은 API 라우터와 `ResearchQAService`, 임베딩 job 함수뿐이다.
- 의존 도메인과 사용 방식(읽기만)
  - `assets`: asset 조회(symbol, name)
  - `raw_news`: 임베딩 대상 원문 조회
  - `news`: 원문별 `asset_id`와 `summary` 조회
- 위 도메인 repository에 필요한 조회 함수가 없으면 해당 repository에 읽기 함수를 추가한다.
  rag 안에서 다른 도메인 모델을 직접 쿼리하지 않는다.
- LLM 호출은 `get_llm_gateway()`(`app/adapters/factory.py:151`)로만 한다.

## 7. 테스트 전략

**SQLite 호환.** `embedding`은 `Vector(EMBEDDING_DIMENSIONS).with_variant(JSON, "sqlite")`, `asset_ids`는
`ARRAY(Integer).with_variant(JSON, "sqlite")`로 선언한다. Postgres 전용 인덱스는 SQLite
`create_all`에서 무시되는지 #439에서 확인한다. 무시되지 않으면 dialect 조건으로 분리한다.

**pgvector 통합 테스트.** `PgVectorStore`와 마이그레이션 검증은 Postgres가 필요하다.
- pytest 마커 `postgres`를 등록한다.
- `TEST_POSTGRES_URL`이 없으면 해당 테스트를 skip한다.
- CI(`.github/workflows/ci.yml`)에 `pgvector/pgvector:pg16` 서비스 컨테이너를 붙인 별도 잡을
  추가해 마커 테스트만 실행한다. 기존 잡(ruff, mypy, pytest)은 그대로 둔다.

**테스트 목록**

| 대상 | 종류 | 핵심 검증 |
|---|---|---|
| 본문 결정·청킹 | 단위 | 200자 경계, summary 보강, 제목만, 청크 겹침 |
| `MockEmbedder` | 단위 | 결정성, 차원 |
| `InMemoryVectorStore` | 단위 | 필터 조합, 정렬 |
| `PgVectorStore` | 통합(`postgres`) | upsert 멱등성, `asset_ids` 포함 필터, 기간 필터, `delete_by_source` |
| 마이그레이션 | 통합(`postgres`) | upgrade/downgrade, 확장 생성 |
| `embed_documents` | 통합(SQLite + memory) | 신규 적재, 해시 변경 재적재, 재실행 멱등성, 임베딩 실패 시 건너뜀 |
| 인용 검증 | 단위 | 없는 번호 제거, 인용 없는 point 제거, 전부 제거 시 insufficient |
| Q&A API | API | 정상 응답, 근거 0건이면 LLM 호출 0회, 404, 422, LLM 실패 시 안전 응답 |
| `ObsidianWriter` | 단위(tmp_path) | 렌더링, 파일명 충돌 접미사, 기존 파일 미변경, 미설정 시 비활성 |

픽스처의 계약 값(enum, `content_quality` 판정 경계 등)은 생산자 코드에서 가져온다. 최소 한
개의 API 테스트는 `raw_news_events` 적재부터 job, 검색, 응답까지 실제 경로를 관통하게
작성한다(`quality-process-policy.md` Real-Contract Fixtures).

## 8. 평가 세트 (#444)

- `docs/experiments/rag-eval-set.md`에 질문 10~20개와 각 질문의 기대 근거(`raw_news_events.id`)를
  기록한다.
- 측정 지표는 recall@8, 근거 0건 비율, 인용 검증에서 버린 point 비율, 청크 수 분포다.
- 측정 스크립트는 `scripts/`에 두고 CI에는 넣지 않는다.
- 결과는 §5.2 가정 값(하한 0.3, k, 감점)을 조정하는 근거이자 ADR-018 V2·V4 판단의 기준선이다.

## 9. Open Questions

| ID | 질문 | 해소 시점 |
|---|---|---|
| OQ1 | **해소(2026-10-12).** 로컬 프록시는 ChatGPT 구독 기반이라 임베딩 API를 쓸 수 없다. 사용자 결정으로 로컬 Ollama `bge-m3`(1024차원)를 쓴다. 실측 처리 시간은 1,500자 청크 약 2.8초, 120자 청크 약 1.2초(CPU)다. ADR-018 §2a | #440·#450 |
| OQ2 | **해소(2026-10-12).** 기존 볼륨으로 기동은 되지만 텍스트 btree 인덱스가 손상된다. alpine(musl)에서 만든 `en_US.utf8` 인덱스를 debian(glibc 2.36)에서 읽기 때문이다. 볼륨 복제본에서 amcheck(`bt_index_check`) 결과 32개 중 2개(`uq_raw_news_events_url`, `ix_fund_flow_outlooks_analysis_version_sector`)가 손상됐고, `REINDEX DATABASE stock_db` 후 0개가 됐다. 이후 `alembic upgrade head`가 실데이터에 정상 적용됐다. 기존 볼륨 전환 절차는 §12를 따른다 | #439 |
| OQ3 | `source_documents` 적재가 상시 운영되면 코퍼스 원본을 그쪽으로 옮길 것인가 | 뉴스 인텔리전스 파이프라인 스케줄 확정 시 |
| OQ4 | `raw_news_events.body`의 실제 길이 분포. `SUMMARY`·`TITLE_ONLY` 비율이 높으면 근거 품질이 낮다 | #441 backfill 후 기록 |

## 10. 범위 밖

- 하이브리드 검색, 재랭킹, 질문 재작성, 다회 검색 루프(ADR-018 V2·T1)
- 대화 이력, 응답 캐시(ADR-011 deferred)
- 지식 수집과 다중 풀 검색, 인용 종류 구분(#445~#448)
- vault 읽기(#446)
- FE 질문 패널(`project_stock_frontend#308`)

## 11. ADR 필요 여부

신규 ADR은 필요 없다. 배치, 저장소, 경계 규칙은 ADR-018에서 결정했고, 클라우드 경계는
ADR-009를 적용한다(`ResearchQASnapshot`).

## 12. 기존 로컬 볼륨 전환 절차

이미지를 바꾼 뒤 기존 `postgres_data` 볼륨을 계속 쓰려면 앱보다 먼저 인덱스를 다시 만든다.
손상된 unique 인덱스를 그대로 두면 중복 행이 들어가거나 조회가 누락될 수 있다.

1. 앱·워커를 멈춘 상태에서 postgres 서비스만 새 이미지로 기동한다.
2. `REINDEX DATABASE stock_db`를 실행한다.
3. 필요하면 `amcheck` 확장의 `bt_index_check`로 텍스트 btree 인덱스를 검사한다.
4. `alembic upgrade head`로 `document_chunks`를 만든다.
5. 앱·워커를 기동한다.

`ALTER DATABASE ... REFRESH COLLATION VERSION`은 alpine에서 collation 버전이 기록되지 않아
오류가 나므로 실행하지 않는다. 배포 환경도 같은 이미지 교체를 하면 같은 절차가 필요하다.

## 13. Ollama 준비 절차

임베딩 모델은 compose `ollama` 서비스에서 한 번만 받아 두면 된다. 모델 파일은 `ollama_data`
볼륨에 남는다.

1. `docker compose up -d ollama`
2. `docker compose exec ollama ollama pull bge-m3`
3. 확인: `/v1/embeddings`에 `bge-m3`로 요청해 1024차원 벡터가 오는지 본다.

호스트에서 uvicorn을 직접 실행할 때는 `EMBEDDING_BASE_URL` 기본값(`http://localhost:11434/v1`)이
compose의 Ollama 포트를 가리킨다.

