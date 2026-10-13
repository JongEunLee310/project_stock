# Codex Handoff Task

## Source Issue

#471 — [BE] RAG 2차-1: 지식 정본 knowledge_documents와 지식 청크 인덱싱 (트래킹 #445, 에픽 #438)

## Task Summary

연간보고서 섹션 같은 지식 문서를 담는 정본 테이블 `knowledge_documents`를 만들고, 기존 임베딩 인덱서가 이
문서를 `source_type=KNOWLEDGE` 청크로 적재하게 한다. 공시 수집(#472)은 이번 범위가 아니다.

## Goal

- `knowledge_documents` 테이블과 마이그레이션이 생기고 Alembic head가 하나다.
- `EmbeddingIndexer.run`이 뉴스에 이어 지식 문서를 스캔해 적재한다. 내용이 같으면 건너뛰고, 바뀌면 다시 적재한다.
- 기존 뉴스 인덱싱과 Q&A·일일 리서치 검색 결과는 바뀌지 않는다.

## Background

- 설계 정본: `docs/designs/445-filing-knowledge-collection.md` §1·§2·§4. **반드시 먼저 읽는다.** ADR-018도 참고한다.
- 기존 청크 모델·인덱서: `app/domains/rag/model.py`, `app/domains/rag/types.py`, `app/domains/rag/indexing.py`
  (`chunk_text`, `embedding_input_hash`), `app/domains/rag/indexing_service.py`(`EmbeddingIndexer`),
  `app/adapters/vector/pgvector.py`
- 모델 등록: `app/db/models.py`(모든 모델 import), 마이그레이션 패턴은 최근 `alembic/versions/` 파일(현재 head
  `c3d4e5f60071`)을 따른다. `JobRun.metadata_` 매핑 방식을 참고한다.
- 의존성 추가는 없다. `uv add`, `uv sync`, 네트워크, `git fetch`, docker 명령을 하지 않는다.

## Implementation Scope

1. 새 도메인 `app/domains/knowledge/`
   - `types.py`: `KnowledgeKind`(`FILING_SECTION`), `FilingSection`(`BUSINESS`, `RISK_FACTORS`)
   - `model.py`: `KnowledgeDocument` — 필드·제약·인덱스는 설계 §2.1 그대로. `metadata` 컬럼은 Python 속성
     `metadata_`, 기본 `{}`
   - `schema.py`: 생성용 값 객체(`KnowledgeDocumentCreate`)
   - `repository.py`: 설계 §2.3의 네 함수. commit하지 않는다.
2. 마이그레이션: `knowledge_documents` 생성(FK `assets.id`, unique (`kind`, `external_id`), 인덱스
   (`asset_id`, `kind`, `effective_date`)). downgrade 포함.
3. `ChunkSourceType.KNOWLEDGE` 추가
4. `EmbeddingIndexer.run`(설계 §4)
   - 뉴스 스캔을 먼저 하고, 남은 `max_documents` 한도 안에서 지식 문서를 id 순으로 스캔한다.
   - 지식 청크 필드: `content_quality=FULL`, `asset_ids=[asset_id]`(null이면 `[]`), `published_at`은
     `effective_date`의 Asia/Seoul 자정(timezone-aware), 없으면 `created_at`. 임베딩 입력은 `title` + 빈 줄 + `content`.
   - `content_hash` 비교·삭제 후 upsert·배치 shape 검증은 뉴스와 같은 규칙을 쓴다. 한 번의 `embed` 호출로 두
     원천을 함께 보내도 되고 나눠도 된다.
   - `has_more`는 두 원천 중 하나라도 처리하지 못한 문서가 남을 수 있으면 True다(기존 의미 유지:
     `documents == max_documents`).
   - 뉴스만 있을 때의 결과(`IndexingResult` 값, 청크)는 이전과 같아야 한다.
5. 설계 문서는 구현과 다르게 정한 것이 있을 때만 고친다.

## Out of Scope

- 공시 어댑터·수집 서비스·job·스케줄·설정(#472)
- 검색(`search`) 변경, 다중 풀 검색(#474)
- Q&A·일일 리서치 서비스 변경

## Protected Files

없음.

## Test Requirements

- 모델: unique 제약 위반, `metadata_` 기본값, FK
- 마이그레이션: 기존 마이그레이션 테스트 패턴(`tests/test_alembic_metadata.py`, `tests/rag/test_embedding_migration.py`)
  이 있으면 맞춰 갱신, `uv run alembic heads` 단일 head
- repository: 네 함수
- 인덱서: 지식 청크 필드, 같은 내용 재실행 시 `unchanged`, 내용 변경 시 재적재(기존 청크 삭제), `asset_id` null,
  뉴스와 지식 문서 혼합 시 `max_documents` 한도와 `has_more`, 뉴스만 있을 때 기존 테스트 그대로 통과
- Postgres 마커 테스트가 있으면 새 테이블이 깨지지 않게 유지(로컬에서 실행 못 해도 됨)

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## ADR Need

불필요(ADR-018이 `knowledge_documents` 정본을 정함).

## Failure Record Need

불필요.

## Risk Level

Medium — 스키마 추가와 공용 인덱서 변경. 뉴스 경로 불변을 테스트로 확인한다.

## Expected Output

- 현재 브랜치 `feat/471-knowledge-documents`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋 상태로 두고 보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, 가정, 검증 결과

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
