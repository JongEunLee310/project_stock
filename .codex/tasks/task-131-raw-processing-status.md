# Codex Handoff Task

## Source Issue

BE #179(LLM 파이프라인 2단계 · Raw 저장 구조 보강 — processing_status). 상위 Epic #174. 설계
`docs/designs/068-raw-processing-status.md`. 기준 문서 `docs/knowledge/llm-data-pipeline.md`
(6.2·11절 2단계). Milestone: 데이터 수집 파이프라인 — 백엔드(#5).

## Task Summary

기존 원본 저장 테이블 `raw_prices`·`raw_news_events`에 가공 진행 상태 컬럼 `processing_status`를
신설한다. 값은 1단계에서 정의한 `app/domains/ingestion/schema.ProcessingStatus` enum을 **재사용**
한다. 컬럼 추가 + 기존 행 `fetched` backfill 마이그레이션을 함께 만든다. 상태 전이 로직
(`normalized`/`failed` 세팅)은 3·4단계 몫이며 본 task 범위가 아니다.

## Goal

완료 시 참이어야 할 것:

- `app/domains/raw_prices/model.py`의 `RawPrice`와 `app/domains/raw_news/model.py`의
  `RawNewsEvent`에 `processing_status` 컬럼이 있고, 서비스 경유 insert 시 값 미지정이면
  `fetched`로 채워진다.
- alembic 마이그레이션이 두 테이블에 컬럼을 추가하고 `server_default`로 기존 행을 `fetched`로
  backfill 한다. up/down 모두 동작한다.
- 컬럼 값은 `ProcessingStatus`(`app/domains/ingestion/schema.py`) 값 도메인을 따른다. 병렬
  enum을 새로 만들지 않는다.
- 각 테이블에 `processing_status` 단일 컬럼 인덱스가 있다.
- ruff·mypy·pytest 전부 통과한다.

## Background

- **모델 관례**: `app/db/base.py`의 `Base` + `TimestampMixin`. 문자열 컬럼은
  `sqlalchemy.String(...)`. enum 값은 DB 네이티브 enum이 아니라 문자열로 저장한다
  (`app/domains/decision_logs/model.py`가 enum `.value` 문자열 저장 예시). 기존
  `RawPrice.fetched_at`이 `server_default=func.now()`를 쓰는 것처럼, 컬럼 기본값은
  `server_default`로 준다.
- **enum 재사용(중요)**: `app/domains/ingestion/schema.py`에 이미
  `ProcessingStatus(str, Enum)`(`fetched`/`normalized`/`failed`/`skipped_duplicate`)이 있다.
  컬럼 기본값·비교에 이 enum을 import해 쓴다. 새 enum을 만들지 말 것.
- **컬럼 정의 기준**: `processing_status: Mapped[str] = mapped_column(String(20),
  server_default=ProcessingStatus.FETCHED.value, nullable=False, index=True)` 형태. Python
  side 기본값(`default=...`)은 넣지 않아도 되며 기존 `fetched_at`과 동일하게 server_default만
  둔다(테스트는 서비스 경유 commit 후 refresh 값으로 확인).
- **수집 서비스 미변경 원칙**: `save_raw`/repository는 `processing_status`를 넘기지 않으므로
  server_default가 자동 적용된다. 서비스·repository 로직에 상태 값을 주입하는 코드를 추가하지
  않는다(전이는 3·4단계). 단, 컬럼 추가로 기존 create 스키마·저장 경로가 깨지지 않는지만
  확인한다.
- **마이그레이션 구조**: `docs/designs/039-db-migration-structure.md`를 따른다. 현재 단일 head는
  `c3d4e5f60057`(1단계). 신규 revision의 `down_revision`은 `c3d4e5f60057`이다. `alembic heads`가
  단일 head를 유지해야 한다.
- **인덱스 이름**: `ix_raw_prices_processing_status`, `ix_raw_news_events_processing_status`.

## Implementation Scope

- `app/domains/raw_prices/model.py`: `RawPrice`에 `processing_status` 컬럼 추가(String(20),
  server_default `fetched`, nullable=False, index). `ProcessingStatus`를
  `app.domains.ingestion.schema`에서 import.
- `app/domains/raw_news/model.py`: `RawNewsEvent`에 동일 컬럼 추가.
- `alembic/versions/`: 신규 revision(`down_revision="c3d4e5f60057"`). upgrade는 두 테이블에
  `processing_status` 컬럼(server_default `fetched`, not null) + 각 인덱스 추가. downgrade는
  인덱스·컬럼 제거. SQLite 배치 모드가 필요하면 `docs/designs/039` 관례를 따른다.
- 테스트(아래 Test Requirements).

## Out of Scope

- 상태 전이 로직: 정규화 성공 시 `normalized`, 검증 실패 시 `failed` 세팅(3·4단계).
- 상태별 조회 repository 메서드·재처리 잡(3단계에서 소비처와 함께).
- 통합 원본 테이블 신설(1단계 Decision A 유지).
- Normalizer·Validator·Feature Builder·ContextBuilder·Gateway 로직.
- route·API 노출.
- `RawProviderResponse` projection(1단계에서 정의 완료) 변경.
- create/read 스키마(`raw_prices/schema.py`, `raw_news/schema.py`)에 `processing_status` 노출
  추가(필요해지면 3단계). 컬럼 추가로 기존 스키마가 깨지지 않는지만 확인.

## Protected Files

`app/adapters/llm/*`, `app/domains/ingestion/*`(1단계 계약, `ProcessingStatus`는 재사용만·수정
금지), `app/domains/llm_context/*`, `app/domains/llm_analysis/*`, `app/domains/prices/*`,
`app/domains/news/*`, `app/domains/decision_logs/*`는 변경하지 않는다. Implementation Scope 밖
파일은 변경하지 않는다.

## Requirements

- `processing_status` 값 도메인은 `ProcessingStatus` enum을 따른다. 새 enum을 만들지 않는다.
- 컬럼은 not null이고 `server_default`가 `fetched`다(기존 행 backfill).
- 마이그레이션은 단일 head(`c3d4e5f60057` 뒤)를 유지하고 up/down 모두 동작한다.
- 수집 서비스에 상태 전이 로직을 넣지 않는다(2단계는 컬럼·기본값·인덱스까지만).
- 신규 컬럼은 타입 주석을 완전히 채워 mypy `no-untyped-def`를 피한다.

## Test Requirements

- `RawPrice`·`RawNewsEvent`를 서비스(`save_raw`) 경유로 저장하면 `processing_status`가
  `fetched`로 채워진다.
- 컬럼에 `normalized`/`failed`를 명시 저장·조회할 수 있다(상태 표현 가능성 확인, 전이 로직 아님).
- 마이그레이션 up 후 컬럼이 존재하고, down이 컬럼·인덱스를 되돌린다(스키마 회귀, SQLite).
- 기존 `raw_prices`·`raw_news` 관련 테스트가 계속 통과한다(저장 경로 회귀).

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

설계 `docs/designs/068-raw-processing-status.md`가 근거다. 문서를 새로 쓰지 않는다. knowledge/도메인
문서 반영 여부는 orchestrator가 리뷰 시 판단한다.

## ADR Need

불필요. 기존 테이블에 상태 컬럼 하나를 추가하는 통상 마이그레이션이다. Codex는 ADR을 작성하지
않는다.

## Failure Record Need

불필요.

## Risk Level

Low-Medium. 기존 두 테이블에 not-null 컬럼을 추가하는 마이그레이션이다. 주의점은 (1) not-null
컬럼 추가 시 `server_default`로 기존 행 backfill 보장, (2) `down_revision` 정확히
`c3d4e5f60057`로 단일 head 유지, (3) `ProcessingStatus` enum 재사용(신설 금지), (4) 상태 전이
로직을 넣지 않기(범위 밖), (5) SQLite alter 제약(배치 모드) 대응이다.

## Expected Output

- 위 scope의 두 모델 컬럼 추가·마이그레이션(up/down)·인덱스·테스트.
- 검증 3종(ruff·mypy·pytest) 통과 로그와 `alembic heads` 단일 head 확인.
- 가정(컬럼 타입·기본값·인덱스명)과 검증 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files (특히 `app/domains/ingestion/*`의 `ProcessingStatus`).
- Do not add state-transition logic or 3~7단계 로직.
- `ProcessingStatus` enum을 재사용하고 병렬 enum을 만들지 않는다.
- Report assumptions and verification results.

## Stop Conditions

- not-null 컬럼 추가가 기존 데이터/테스트 픽스처와 충돌하면 멈추고 보고한다.
- 신규 마이그레이션이 기존 체인(`c3d4e5f60057`)과 충돌하거나 head가 갈라지면 멈추고 보고한다.
- SQLite에서 컬럼·인덱스 추가가 배치 모드로도 처리되지 않으면 멈추고 보고한다.
