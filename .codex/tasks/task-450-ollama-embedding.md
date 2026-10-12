# Codex Handoff Task

## Source Issue

#450 — [BE] RAG 1차: 임베딩 소스를 로컬 Ollama(bge-m3, 1024차원)로 전환 (에픽 #438)

## Task Summary

실제 임베딩을 로컬 Ollama의 `bge-m3`로 생성하도록 바꾼다. 벡터 차원을 1536에서 1024로 바꾸는
마이그레이션을 추가하고, compose에 `ollama` 서비스를 붙이고, 임베딩 설정 기본값과 factory를
로컬 엔드포인트에 맞춘다. #440(`Embedder`·`VectorStore` 어댑터) 위에서 같은 브랜치로 진행한다.

## Goal

완료 시 다음이 참이어야 한다.

- 새 마이그레이션이 `c3d4e5f6006f` 다음 단일 head이고, `document_chunks.embedding`을
  `vector(1024)`로 바꾸며 HNSW 인덱스를 다시 만든다. downgrade는 `vector(1536)`으로 되돌린다.
- `EMBEDDING_DIMENSIONS`가 1024이고, 모델·factory·Mock이 이 상수를 따른다.
- 설정 기본값이 `EMBEDDING_MODEL="bge-m3"`, `EMBEDDING_BASE_URL="http://localhost:11434/v1"`다.
- `EMBEDDING_BASE_URL`이 있고 API 키가 없으면 factory가 더미 키로 `OpenAIEmbedder`를 만든다.
- `docker-compose.yml`에 `ollama` 서비스가 있고, `backend`와 `worker`가 compose 네트워크 주소로
  Ollama를 쓴다.

## Background

- 결정: 사용자가 2026-10-12 로컬 Ollama 사용을 선택했다. 로컬 `OPENAI_BASE_URL`은 ChatGPT 구독
  기반 프록시라 임베딩 API를 쓸 수 없다(설계 438 §9 OQ1).
- orchestrator 실측(2026-10-12, `ollama/ollama:0.40.3` 컨테이너, `bge-m3`)
  - OpenAI 호환 `POST /v1/embeddings`로 1024차원 벡터를 받는다.
  - 요청의 `dimensions` 인자를 지원한다(1024 요청 시 1024, 512 요청 시 512). 그래서
    `OpenAIEmbedder`가 보내는 `dimensions`(`app/adapters/embedding/openai.py`)는 그대로 둔다.
  - 처리 시간은 1,500자 청크 약 2.8초, 120자 청크 약 1.2초(CPU)다.
- #440이 만든 것: `app/adapters/embedding/`, `app/adapters/vector/`, `get_embedder()`,
  `get_vector_store()`, `app/domains/rag/types.py`의 `EMBEDDING_DIMENSIONS = 1536`.
- #439의 마이그레이션 `c3d4e5f6006f`는 이미 dev에 머지됐다. **수정하지 않고 새 마이그레이션을
  추가한다.**
- `document_chunks`의 행은 원본에서 언제든 다시 만들 수 있다(ADR-018 R3). 차원이 다른 기존 행은
  타입 변경 전에 삭제해도 된다.
- 기존 LLM 프록시 더미 키 처리: `app/adapters/factory.py`의 `LOCAL_PROXY_OPENAI_API_KEY`와
  `get_llm_client`. 같은 방식으로 임베딩용 더미 키 상수를 둔다.
- 의존성 추가는 없다. `uv add`, `uv sync`, 네트워크, `git fetch`를 하지 않는다. Docker 명령도
  실행하지 않는다(실호출 검증은 orchestrator가 한다).

## Implementation Scope

1. `app/domains/rag/types.py`: `EMBEDDING_DIMENSIONS = 1024`
2. 마이그레이션 신설(`alembic/versions/`, revision id는 기존 수작업 스타일)
   - upgrade
     1. HNSW 인덱스 `ix_document_chunks_embedding`를 지운다.
     2. `document_chunks`의 행을 모두 지운다. 이유를 docstring에 한 줄로 남긴다(차원이 달라 변환할
        수 없고, 원본에서 다시 만들 수 있음).
     3. `embedding` 컬럼 타입을 `vector(1024)`로 바꾼다.
     4. HNSW 인덱스를 `vector_cosine_ops`로 다시 만든다.
   - downgrade: 같은 순서로 `vector(1536)`으로 되돌린다.
3. `app/core/config.py`
   - `EMBEDDING_MODEL: str = "bge-m3"`
   - `EMBEDDING_BASE_URL: str | None = "http://localhost:11434/v1"`
4. `app/adapters/factory.py`의 `get_embedder()`
   - `openai` provider에서 API 키는 `EMBEDDING_API_KEY`, 없으면 `OPENAI_API_KEY`를 쓴다.
   - 둘 다 없고 `EMBEDDING_BASE_URL`이 있으면 더미 키 상수(예: `LOCAL_EMBEDDING_API_KEY = "local-embedding"`)를 쓴다.
   - 키도 base URL도 없을 때만 `RuntimeError`를 던진다.
   - `OPENAI_BASE_URL`은 계속 상속하지 않는다.
5. `docker-compose.yml`
   - `ollama` 서비스: `image: ollama/ollama:0.40.3`, `restart: unless-stopped`,
     `ports: ["11434:11434"]`, 볼륨 `ollama_data:/root/.ollama`
   - 최상위 `volumes`에 `ollama_data` 추가
   - `backend`와 `worker`의 `environment`에 `EMBEDDING_BASE_URL: http://ollama:11434/v1`을 추가한다.
     `depends_on`은 추가하지 않는다(임베딩 실패는 job과 API에서 처리).
   - 다른 서비스와 기존 설정은 바꾸지 않는다.
6. `.env.example`: 임베딩 항목을 새 기본값에 맞추고, 호스트에서 직접 실행할 때와 compose 안에서
   실행할 때의 base URL 차이를 주석 한 줄로 적는다(기존 `OPENAI_BASE_URL` 주석 형식을 따른다).
7. 테스트 갱신과 추가(아래)

## Out of Scope

- ADR-018과 설계 438 갱신(orchestrator가 한다)
- `OpenAIEmbedder`의 요청 형식 변경
- 임베딩 job, Q&A API(#441, #442)
- 모델 자동 다운로드(entrypoint 스크립트 등). 1회 수동 절차로 문서화한다(orchestrator 담당).

## Protected Files

없음.

## Requirements

- 마이그레이션은 단일 head를 유지한다.
- 모델의 `Vector(EMBEDDING_DIMENSIONS)`와 새 마이그레이션의 차원이 일치해야 한다.
- 주석은 이유가 분명하지 않은 곳에만 최소한으로 쓴다.

## Test Requirements

- factory 단위 테스트
  - 키 없이 `EMBEDDING_BASE_URL`만 있을 때 더미 키로 `OpenAIEmbedder`를 만든다.
  - 키와 base URL이 모두 없으면 `RuntimeError`가 난다.
  - `EMBEDDING_API_KEY`가 있으면 그 키를 쓴다.
  - `OPENAI_BASE_URL`을 상속하지 않는다(#440 테스트 유지).
- 차원 상수가 1024로 바뀌면서 깨지는 기존 테스트를 고친다. 테스트 안의 1536 리터럴은
  `EMBEDDING_DIMENSIONS`를 참조하도록 바꾼다(#439 `tests/rag/test_document_chunks.py` 포함).
- `postgres` 마커 테스트가 새 차원에서 통과하도록 맞춘다(CI `Verify pgvector`가 실행한다).

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
grep -rn "1536" app tests
```

- `alembic heads`는 새 revision 하나만 출력해야 한다.
- 마지막 grep은 downgrade의 `vector(1536)` 외에는 결과가 없어야 한다. 마이그레이션 파일은
  `alembic/versions`에 있으므로 이 grep 범위에 들어가지 않는다.

## Documentation Impact

`.env.example`만 이 작업에서 갱신한다. ADR-018과 설계 438은 orchestrator가 같은 PR에서 갱신한다.

## ADR Need

불필요. ADR-018의 범위 안에서 임베딩 provider를 정하는 결정이며, orchestrator가 ADR-018 본문에
반영한다.

## Failure Record Need

불필요.

## Risk Level

High — DB 스키마 변경(컬럼 타입 변경과 행 삭제)과 인프라(compose 서비스 추가). 사용자가 로컬
Ollama를 선택했고, orchestrator가 실측으로 실현 가능성을 확인했다. 머지는 개발자가 결정한다.

## Expected Output

- 현재 브랜치 `feat/440-embedder-vector-store`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋 상태로 두고 보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, 가정, 검증 명령별 결과, 실행하지 못한 검증

## Stop Conditions

- 기존 마이그레이션을 수정해야만 하는 상황
- 의존성 추가가 필요한 상황
- 기존 테스트가 이 변경과 무관한 이유로 실패하는 상황
- 샌드박스 권한 부족

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
