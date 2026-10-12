# Codex Handoff Task

## Source Issue

#439 — [BE] RAG 1차: pgvector 인프라·document_chunks 모델 (에픽 #438)

## Task Summary

RAG 1차의 저장 기반을 만든다. Postgres 이미지를 pgvector 이미지로 바꾸고, `vector` 확장과
`document_chunks` 테이블을 마이그레이션으로 추가하고, 신규 도메인 `app/domains/rag/`에 모델과
enum을 둔다. SQLite 테스트 환경에서도 모델이 생성되도록 variant를 선언하고, pgvector 전용
검증은 `postgres` 마커 테스트와 별도 CI 잡으로 분리한다.

## Goal

완료 시 다음이 참이어야 한다.

- `docker-compose.yml`의 postgres 서비스 이미지가 `pgvector/pgvector:pg16`이다.
- 새 Alembic 마이그레이션이 `c3d4e5f6006e` 다음 단일 head로 존재하고, upgrade 시 `vector` 확장과
  `document_chunks` 테이블·인덱스를 만들고 downgrade 시 테이블을 제거한다.
- `app/domains/rag/model.py`의 `DocumentChunk`와 `app/domains/rag/types.py`의 enum 두 종이 설계와
  일치한다.
- 기존 SQLite 기반 `uv run pytest`가 그대로 통과한다(새 모델 포함 `create_all` 성공).
- `postgres` 마커 테스트가 `TEST_POSTGRES_URL` 없이는 skip되고, CI의 새 잡에서 실제 pgvector
  Postgres로 실행된다.

## Background

- 설계 정본: `docs/designs/438-rag-research-qa.md` §1(인프라), §2.2(모델), §2.3(enum), §7(테스트
  전략). 반드시 먼저 읽는다.
- 결정 배경: `docs/decisions/ADR-018-rag-agent-placement-and-vector-store.md`. 특히 R1(다른 도메인이
  rag 내부를 import하지 않음)과 R3(벡터 저장소에 정본을 두지 않음).
- 테스트 DB는 SQLite 인메모리다(`tests/conftest.py:33`). `Base.metadata.create_all`로 전체 모델을
  만든다(`tests/conftest.py:43`). pgvector `Vector` 타입과 Postgres `ARRAY`는 SQLite에서 동작하지
  않으므로 variant가 필요하다.
- 모델 등록은 `app/db/models.py`의 side-effect import로 한다. 같은 방식으로 rag 모델을 등록한다.
- 마이그레이션 revision id는 기존 파일들의 수작업 id 스타일을 따른다(예: `c3d4e5f6006e`). 현재
  head는 `c3d4e5f6006e`다(`uv run alembic heads`로 확인함).
- **의존성 `pgvector`는 orchestrator가 이미 추가했다**(`pyproject.toml`, `uv.lock`). `uv add`,
  `uv sync`, 네트워크 접근, `git fetch`를 하지 않는다.
- 로컬에는 Docker가 떠 있지 않을 수 있다. 그 경우 `postgres` 마커 테스트는 skip되는 것이 정상이며,
  실제 실행 검증은 CI 새 잡이 맡는다.

## Human Gate

이 작업은 DB 스키마 변경, 의존성 추가, CI 설정 변경, 인프라(compose) 변경을 포함한다
(`docs/harness/human-gate-policy.md`). 사용자가 2026-10-12 설계 438을 검토한 뒤 "#439부터 Codex에
넘겨서 진행해줘"라고 지시해 승인했다. 머지는 개발자가 최종 결정한다.

## Implementation Scope

1. `docker-compose.yml`: postgres 서비스 이미지를 `pgvector/pgvector:pg16`으로 교체. 다른 서비스와
   설정은 건드리지 않는다.
2. `app/domains/rag/__init__.py`, `app/domains/rag/types.py`, `app/domains/rag/model.py` 신설.
   - `ChunkSourceType(str, Enum)`: `NEWS`
   - `ChunkContentQuality(str, Enum)`: `FULL`, `SUMMARY`, `TITLE_ONLY`
   - `DocumentChunk`(`__tablename__ = "document_chunks"`): 설계 §2.2 표의 필드·타입·nullable·제약을
     그대로 따른다.
     - `embedding`: `Vector(1536)`에 SQLite용 JSON variant
     - `asset_ids`: `ARRAY(Integer)`에 SQLite용 JSON variant, 기본값 빈 배열
     - enum 컬럼은 기존 도메인 관례처럼 문자열 컬럼으로 저장한다(기존 모델 하나를 참고해 맞춘다).
     - unique 제약: (`source_type`, `source_id`, `chunk_index`, `embedding_model`)
     - 인덱스: `embedding` HNSW(`vector_cosine_ops`), `asset_ids` GIN, `published_at` btree,
       (`source_type`, `source_id`) btree. Postgres 전용 인덱스가 SQLite `create_all`을 깨뜨리면
       dialect 조건으로 분리한다.
3. `app/db/models.py`: rag 모델 등록 import 한 줄 추가.
4. Alembic 마이그레이션 신설(`alembic/versions/`): upgrade에서 `CREATE EXTENSION IF NOT EXISTS
   vector`, 테이블·제약·인덱스 생성. downgrade에서 테이블 제거. 확장은 downgrade에서 제거하지
   않는다(다른 객체가 의존할 수 있으므로). 이 판단을 마이그레이션 docstring에 한 줄로 남긴다.
5. pytest 마커 `postgres` 등록(`pyproject.toml`의 pytest 설정 위치에 맞춘다). `TEST_POSTGRES_URL`이
   없으면 이 마커 테스트를 skip하는 fixture를 `tests/` 아래에 둔다.
6. 테스트 추가(아래 Test Requirements).
7. `.github/workflows/ci.yml`: 기존 `verify` 잡은 그대로 두고 새 잡을 추가한다.
   - 서비스 컨테이너 `pgvector/pgvector:pg16`(health check 포함)
   - 단계: checkout, Python 3.12, uv, `uv sync`, `alembic upgrade head` → `alembic downgrade -1` →
     `alembic upgrade head`(Postgres 대상), `uv run pytest -m postgres`
   - `DATABASE_URL`과 `TEST_POSTGRES_URL`은 서비스 컨테이너 주소로 잡 env에 둔다. 시크릿은 쓰지
     않는다.

## Out of Scope

- `Embedder`, `VectorStore`, 임베딩 job, Q&A API, Obsidian(#440~#443)
- `raw_news`, `news`, `news_insights` 등 기존 도메인 코드 변경
- 기존 `verify` 잡과 SonarCloud 단계 변경
- 설정 키(`EMBEDDING_*`, `VECTOR_STORE_PROVIDER`) 추가. #440에서 다룬다.

## Protected Files

- `.github/workflows/ci.yml` — **이 작업에서 수정을 허용한다.** 새 잡 추가만 허용하고 기존 잡과
  단계는 바꾸지 않는다.
- 그 외 protected 파일(`AGENTS.md`, `CLAUDE.md`, `docs/harness/`, `docs/decisions/` 등)은 수정하지
  않는다.

## Requirements

- 모델 필드와 제약은 설계 §2.2와 정확히 일치해야 한다. 설계와 다르게 해야 할 이유가 생기면
  임의로 바꾸지 말고 Stop Condition으로 보고한다.
- 마이그레이션은 단일 head를 유지한다.
- rag 도메인 밖에서 rag 내부를 import하는 코드는 `app/db/models.py`의 등록 import 외에는 없어야
  한다(ADR-018 R1).
- 주석은 이유가 분명하지 않은 곳에만 최소한으로 쓴다.

## Test Requirements

- SQLite(기본 pytest)
  - `DocumentChunk`를 저장하고 다시 읽는 라운드트립: `embedding`(길이 1536 리스트), `asset_ids`
    (여러 값과 빈 배열), enum 문자열 값 보존
  - unique 제약 위반 시 오류가 나는지 확인
- Postgres(`@pytest.mark.postgres`)
  - 확장과 테이블이 있는 DB에서 벡터 라운드트립
  - 코사인 거리 정렬이 기대 순서로 나오는지 확인하는 최소 쿼리 한 건(테스트 안에서만 사용)
  - `asset_ids` 포함 조건이 동작하는지 확인
- 테스트 픽스처의 enum 값은 `app/domains/rag/types.py`에서 가져온다(리터럴 하드코딩 금지).

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

- `uv run alembic heads`는 새 revision 하나만 head로 출력해야 한다.
- 로컬에 pgvector Postgres가 있으면 추가로 `TEST_POSTGRES_URL=... uv run pytest -m postgres`와
  upgrade/downgrade/upgrade를 실행한다. 없으면 실행하지 못했다고 결과에 명시한다.

## Documentation Impact

- 설계 438 §9 OQ2(기존 볼륨 호환)는 로컬 Docker로만 확인할 수 있다. Codex는 확인하지 않고, PR
  본문에 "OQ2 미확인, orchestrator가 확인"이라고 남긴다.
- 그 외 문서 변경 없음.

## ADR Need

불필요. ADR-018에서 결정했다.

## Failure Record Need

불필요.

## Risk Level

High — DB 스키마 변경, 의존성 추가, CI 설정 변경, compose 이미지 교체. Human Gate 승인 기록은 위
섹션에 있다.

## Expected Output

- 위 범위의 코드·마이그레이션·테스트·CI diff
- 현재 브랜치 `feat/rag-research-qa`에 커밋한다. 새 브랜치를 만들지 않는다. push와 PR 생성은
  하지 않는다(orchestrator가 수행).
- 커밋 메시지는 한국어 `type: 본문` 형식(예: `feat: pgvector 확장과 document_chunks 모델 추가`)
- 최종 보고: 변경 파일 목록, 가정, 검증 명령별 결과, 실행하지 못한 검증

## Stop Conditions

- 설계 §2.2와 다르게 구현해야 하는 상황
- 의존성 추가가 더 필요한 상황(`uv add` 금지)
- 기존 테스트가 이 변경과 무관한 이유로 실패하는 상황
- 샌드박스 권한 부족. 권한 승격을 시도하지 않는다.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
