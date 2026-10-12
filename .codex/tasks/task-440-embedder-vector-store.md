# Codex Handoff Task

## Source Issue

#440 — [BE] RAG 1차: Embedder·VectorStore 어댑터 (에픽 #438)

## Task Summary

임베딩 생성과 벡터 저장소 접근을 어댑터로 분리한다. `Embedder`(OpenAI, Mock)와
`VectorStore`(pgvector, 인메모리 mock)를 ABC 뒤에 두고, factory와 설정으로 고른다. 이 작업은
어댑터 계층만 만든다. 이를 쓰는 임베딩 job과 Q&A 서비스는 #441·#442에서 만든다.

## Goal

완료 시 다음이 참이어야 한다.

- `app/adapters/embedding/`에 `Embedder` ABC, `OpenAIEmbedder`, `MockEmbedder`가 있다.
- `app/adapters/vector/`에 `VectorStore` ABC, 값 객체(`ChunkRecord`, `ChunkFilter`, `ChunkHit`),
  `PgVectorStore`, `InMemoryVectorStore`가 있다.
- `app/adapters/factory.py`에 `get_embedder()`, `get_vector_store(db)`가 있고 설정으로 구현체를
  고른다.
- 테스트에서는 두 provider가 모두 mock으로 고정되고, 실제 OpenAI를 호출하지 않는다.
- `PgVectorStore` 통합 테스트가 `postgres` 마커로 CI `Verify pgvector` 잡에서 실행된다.

## Background

- 설계 정본: `docs/designs/438-rag-research-qa.md` §4.1, §4.2, §6, §7. 반드시 먼저 읽는다.
- 결정: ADR-018 §2(pgvector, `VectorStore` ABC, factory 선택), R4(필터는 저장소 중립 값으로 정의,
  SQL 표현을 시그니처에 드러내지 않음).
- #439(PR #449, 머지됨)가 만든 것: `app/domains/rag/model.py`의 `DocumentChunk`,
  `app/domains/rag/types.py`의 `ChunkSourceType`·`ChunkContentQuality`, pytest 마커 `postgres`,
  `tests/rag/conftest.py`의 `postgres_db` fixture, CI `Verify pgvector` 잡.
- provider 선택 관례: `app/adapters/factory.py`의 `get_llm_client`(130행 부근)처럼 설정 값으로
  분기하고, 미구현 값은 `NotImplementedError`를 던진다.
- 테스트는 `tests/conftest.py`의 `_PROVIDER_SETTINGS`(12~18행)에 있는 설정을 모두 `"mock"`으로
  고정한다. 새 설정 두 개도 여기에 추가하므로, **두 설정 모두 `"mock"` 값을 받아야 한다.**
- 설정 파싱 관례: `app/core/config.py`의 `Literal` 타입과, 빈 문자열을 `None`으로 바꾸는
  `field_validator`(`parse_optional_string`, 57행 부근).
- **임베딩 엔드포인트는 LLM과 분리한다.** 로컬 `OPENAI_BASE_URL`은 ChatGPT 구독 기반 프록시라
  임베딩 API를 지원하지 않을 가능성이 높다(설계 §9 OQ1). 그래서 임베딩은 `OPENAI_BASE_URL`을
  상속하지 않는다. API 키만 `OPENAI_API_KEY`로 fallback한다.
- 의존성 추가는 없다. `openai`와 `pgvector`는 이미 설치되어 있다. `uv add`, `uv sync`, 네트워크,
  `git fetch`를 하지 않는다.
- 로컬에 Docker가 없으면 `postgres` 마커 테스트는 skip되는 것이 정상이다.

## Implementation Scope

1. 설정(`app/core/config.py`)
   - `EMBEDDING_PROVIDER: Literal["openai", "mock"] = "openai"`
   - `EMBEDDING_MODEL: str = "text-embedding-3-small"`
   - `EMBEDDING_BASE_URL: str | None = None` — 빈 문자열은 `None`(기존 validator 대상에 추가)
   - `EMBEDDING_API_KEY: str | None = None`
   - `VECTOR_STORE_PROVIDER: Literal["pgvector", "mock"] = "pgvector"`
2. `app/adapters/embedding/`
   - `base.py`: `Embedder` ABC
     - `model_name -> str`(property): 청크에 기록할 모델 식별자
     - `dimensions -> int`(property)
     - `embed(texts: list[str]) -> list[list[float]]`: 입력 순서를 보존한다. 빈 목록이면 빈 목록을
       반환하고 외부 호출을 하지 않는다.
   - `openai.py`: `OpenAIEmbedder`. 생성자에서 `api_key`, `model`, `base_url`, `dimensions`를 받는다.
     입력을 배치로 나눠 호출한다(배치 상한 100건, 가정). 응답의 `index`로 순서를 맞춘다. 반환 벡터
     길이가 `dimensions`와 다르면 `EmbeddingDimensionError`를 던진다.
   - `mock.py`: `MockEmbedder`. 텍스트의 sha256으로 시드를 만들어 결정적 벡터를 낸다. 같은 텍스트면
     같은 벡터, 다른 텍스트면 다른 벡터이며 L2 정규화한다. 차원은 생성자 인자(기본 1536)다.
   - `exceptions.py`: `EmbeddingError`(기반), `EmbeddingDimensionError`. 외부 API 오류는
     `EmbeddingError`로 감싼다(시스템 경계).
3. `app/adapters/vector/`
   - `types.py`: frozen dataclass 값 객체
     - `ChunkRecord`: `source_type`, `source_id`, `chunk_index`, `content`, `content_quality`,
       `embedding`, `embedding_model`, `asset_ids`, `published_at`, `content_hash`
     - `ChunkFilter`: `embedding_model: str`, `asset_id: int | None = None`,
       `source_types: tuple[ChunkSourceType, ...] = ()`(빈 튜플이면 전체),
       `published_after: datetime | None = None`
     - `ChunkHit`: `chunk_id`, `source_type`, `source_id`, `chunk_index`, `content`,
       `content_quality`, `published_at`, `score`(코사인 유사도 = 1 - 코사인 거리)
   - `base.py`: `VectorStore` ABC
     - `upsert(records: list[ChunkRecord]) -> int`: unique 키(`source_type`, `source_id`,
       `chunk_index`, `embedding_model`) 기준으로 삽입하거나 갱신하고 처리 건수를 반환한다.
     - `delete_by_source(source_type: ChunkSourceType, source_id: int) -> int`: 모든 모델의 해당
       원문 청크를 지우고 삭제 건수를 반환한다.
     - `search(query_vector: list[float], filters: ChunkFilter, k: int) -> list[ChunkHit]`: score
       내림차순, 동점이면 `chunk_id` 오름차순
   - `pgvector.py`: `PgVectorStore(db: Session)`. upsert는 Postgres `ON CONFLICT DO UPDATE`를 쓴다.
     search는 `cosine_distance` 정렬, `asset_id`는 배열 포함 조건으로 거른다. 트랜잭션 커밋은 호출자
     책임이며 `flush`까지만 한다(기존 repository 관례를 확인해 맞춘다).
   - `memory.py`: `InMemoryVectorStore`. 필터를 Python으로 평가하고 같은 정렬 규칙을 지킨다.
     인스턴스 메모리에만 저장한다(비영속).
4. `app/adapters/factory.py`
   - `get_embedder() -> Embedder`
     - `mock`이면 `MockEmbedder()`
     - `openai`이면 API 키는 `EMBEDDING_API_KEY`, 없으면 `OPENAI_API_KEY`를 쓴다. 둘 다 없으면
       `RuntimeError("EMBEDDING_API_KEY or OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")`.
       base URL은 `EMBEDDING_BASE_URL`만 쓴다(`OPENAI_BASE_URL`을 상속하지 않음).
     - 차원은 `DocumentChunk.embedding` 컬럼 차원(1536)과 같은 값을 넘긴다. 이 숫자를 rag 쪽 한
       곳(예: `app/domains/rag/types.py`의 상수 `EMBEDDING_DIMENSIONS`)에 두고 모델과 factory가 같이
       참조하도록 정리한다. 모델의 `Vector(1536)`도 이 상수를 쓰게 바꾼다(마이그레이션은 바꾸지 않음).
   - `get_vector_store(db: Session) -> VectorStore`: `pgvector`이면 `PgVectorStore(db)`, `mock`이면
     `InMemoryVectorStore()`
5. `tests/conftest.py`의 `_PROVIDER_SETTINGS`에 `EMBEDDING_PROVIDER`, `VECTOR_STORE_PROVIDER` 추가
6. 테스트 추가(아래)
7. 설계 438 §4.1·§4.2에서 다음을 갱신한다. 이 문서는 protected가 아니다.
   - 설정 이름과 값: `VECTOR_STORE_PROVIDER`의 `memory`를 `mock`으로 바꾼다.
   - 임베딩의 base URL은 상속하지 않고, API 키만 fallback한다.

8. PR #449 리뷰 S1 정리: `postgres` 마커 skip이 `tests/conftest.py`의 autouse fixture와
   `tests/rag/conftest.py`의 `postgres_db` 두 곳에 있다. 한 곳만 남긴다.

## Out of Scope

- 임베딩 job, 청킹, Q&A 서비스·API, Obsidian(#441~#443)
- 마이그레이션 변경
- `LLMGateway`, `OPENAI_BASE_URL` 동작 변경
- 아래 8번(PR #449 리뷰 S1) 외의 리팩터링

## Protected Files

없음. `.github/workflows/ci.yml`은 바꾸지 않는다(기존 `Verify pgvector` 잡이 `-m postgres`로 새
테스트를 실행한다).

## Requirements

- ADR-018 R1: 다른 도메인이 `app/domains/rag` 내부를 import하지 않는다. 어댑터(`app/adapters/vector`,
  `app/adapters/embedding`)는 rag의 인프라라서 `app/domains/rag`의 model과 types를 참조해도 된다.
- ADR-018 R4: `VectorStore`와 `ChunkFilter`의 시그니처에 SQLAlchemy 표현식, Session 외 DB 개념을
  드러내지 않는다(`PgVectorStore` 생성자의 `Session`은 허용).
- 모든 공개 함수에 타입 주석을 단다(mypy).
- 주석은 이유가 분명하지 않은 곳에만 최소한으로 쓴다.

## Test Requirements

- 단위(SQLite 기본 실행)
  - `MockEmbedder`: 결정성, 서로 다른 텍스트의 벡터가 다름, 차원, L2 노름 1, 빈 입력
  - `OpenAIEmbedder`: OpenAI 클라이언트를 가짜로 바꿔 배치 분할, `index` 순서 복원, 차원 불일치 시
    `EmbeddingDimensionError`, API 오류의 `EmbeddingError` 변환을 검증한다(네트워크 호출 금지).
  - `InMemoryVectorStore`: upsert 멱등성(같은 키 재적재 시 갱신, 건수), 필터 조합(`asset_id`,
    `source_types`, `published_after`, `embedding_model`), 정렬과 동점 처리, `delete_by_source`
  - factory: provider별 반환 타입, `openai`에서 키가 없을 때의 `RuntimeError`, `EMBEDDING_API_KEY`
    fallback, `EMBEDDING_BASE_URL`만 쓰고 `OPENAI_BASE_URL`은 쓰지 않음
- 통합(`@pytest.mark.postgres`, `postgres_db` 사용)
  - `PgVectorStore`: upsert 삽입과 갱신, 필터 조합 검색, score 계산(같은 벡터면 1.0에 근접),
    `delete_by_source`
- **InMemory와 pgvector가 같은 입력에서 같은 결과(순서 포함)를 내는지** 공용 시나리오 하나로 두
  구현체를 함께 검증한다(postgres 마커가 없으면 InMemory만 실행). 인터페이스가 저장소 중립인지
  확인하는 테스트다.
- enum 값은 `app/domains/rag/types.py`에서 가져온다.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

- 로컬에 pgvector Postgres가 있으면 `TEST_POSTGRES_URL=... uv run pytest -m postgres`를 추가로
  실행한다. 없으면 실행하지 못했다고 결과에 명시한다.

## Documentation Impact

설계 438 §4.1·§4.2를 위 범위대로 갱신한다. 그 외는 없다.

## ADR Need

불필요. ADR-018의 적용이다.

## Failure Record Need

불필요.

## Risk Level

Medium — 기존 패턴(provider factory, 어댑터 ABC)을 따르는 신규 어댑터와 설정 추가다. 스키마,
의존성, CI 변경은 없다.

## Expected Output

- 현재 브랜치 `feat/440-embedder-vector-store`에서 작업한다. 새 브랜치를 만들지 않는다.
- 샌드박스에서 `.git` 쓰기가 막혀 커밋이 실패하면 미커밋 상태로 두고 보고한다. 권한 승격을
  시도하지 않는다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, 가정, 검증 명령별 결과, 실행하지 못한 검증

## Stop Conditions

- 설계·이 핸드오프와 다르게 구현해야 하는 상황
- 의존성 추가가 필요한 상황
- 기존 테스트가 이 변경과 무관한 이유로 실패하는 상황
- 샌드박스 권한 부족

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
