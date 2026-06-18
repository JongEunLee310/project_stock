# Codex Handoff Task

## Source Issue

Issue #8: Raw News 저장 구조 구현
Issue #9: 정규화된 뉴스 News Item 도메인 구현
Issue #12: Job Run 실행 이력 기록 구현

## Task Summary

뉴스 수집 파이프라인에 필요한 3개 DB 도메인을 구현한다. `raw_news_events`(원본 뉴스), `news_items`(정규화 뉴스), `job_runs`(작업 이력) 테이블과 각 도메인의 모델·스키마·레포지토리를 생성한다.

## Goal

- 외부 뉴스 원본 데이터를 손실 없이 `raw_news_events`에 저장할 수 있다.
- 정규화된 뉴스를 특정 종목(`assets`)과 연결해 `news_items`에 저장할 수 있다.
- Background Job의 실행 이력을 `job_runs`에 기록하고 조회할 수 있다.

## Background

- **설계 문서를 구현 전에 반드시 읽는다:**
  - `docs/designs/008-raw-news-domain.md` — raw_news_events 테이블·스키마·레포지토리
  - `docs/designs/009-news-item-domain.md` — news_items 테이블·스키마·레포지토리
  - `docs/designs/012-job-runs-domain.md` — job_runs 테이블·스키마·서비스
- 현재 최신 Alembic head revision: `8c3f0d2b7a91` (merge head)
- 기존 도메인 패턴: `app/domains/<name>/model.py`, `schema.py`, `repository.py`, `service.py`
- `TimestampMixin`(`created_at`, `updated_at`)은 `app/db/base.py`에 정의됨
- `news_items`는 `raw_news_events`와 `assets` 두 테이블을 FK 참조
- 이 태스크 완료 후 Issue #10(Adapter), Issue #11(Worker)이 진행됨

## Implementation Scope

### Issue #8 — raw_news_events

- `app/domains/raw_news/__init__.py`
- `app/domains/raw_news/model.py` — RawNewsEvent 모델
- `app/domains/raw_news/schema.py` — RawNewsEventCreate, RawNewsEventResponse
- `app/domains/raw_news/repository.py` — RawNewsEventRepository

### Issue #9 — news_items

- `app/domains/news/__init__.py`
- `app/domains/news/model.py` — NewsItem 모델
- `app/domains/news/schema.py` — NewsItemCreate, NewsItemResponse
- `app/domains/news/repository.py` — NewsItemRepository

### Issue #12 — job_runs

- `app/domains/jobs/__init__.py`
- `app/domains/jobs/model.py` — JobRun 모델
- `app/domains/jobs/schema.py` — JobRunCreate, JobRunResponse
- `app/domains/jobs/repository.py` — JobRunRepository
- `app/domains/jobs/service.py` — JobRunService (start/succeed/fail 메서드)
- `app/api/v1/endpoints/job_runs.py` — GET /api/v1/job-runs (목록 조회)
- `app/api/v1/router.py` — job_runs 라우터 등록 추가

### Alembic

- `alembic/versions/<rev>_create_raw_news_events_table.py` — down_revision: `8c3f0d2b7a91`
- `alembic/versions/<rev>_create_news_items_table.py` — down_revision: raw_news revision
- `alembic/versions/<rev>_create_job_runs_table.py` — down_revision: `8c3f0d2b7a91`
- `alembic/versions/<rev>_merge_news_and_jobs_heads.py` — 위 두 브랜치를 merge
- `alembic/env.py` — RawNewsEvent, NewsItem, JobRun import 추가

### Tests

- `tests/test_raw_news.py` — RawNewsEvent CRUD, URL 중복 방지 테스트
- `tests/test_news_items.py` — NewsItem 생성, 종목별 조회 테스트
- `tests/test_job_runs.py` — JobRun 이력 기록, 상태 전이, 목록 API 테스트

## Out of Scope

- AI 요약 로직 (Issue #14)
- Adapter 구현 (Issue #10)
- Worker/Celery/RQ 설정 (Issue #11)
- `news_items`의 `summary`, `sentiment`, `impact_level` 실제 채움 로직 (컬럼만 추가)
- 인증 (Job Runs 조회 API는 인증 불필요 — 내부 관리 용도)

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

### raw_news_events 테이블

| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | Integer PK | |
| title | String(500) | |
| url | String(2048) | UNIQUE 제약 |
| body | Text nullable | |
| source | String(100) | |
| published_at | DateTime(timezone=True) nullable | |
| collected_at | DateTime(timezone=True) | server_default=now() |
| payload | JSON nullable | 원본 응답 전체 저장 |
| created_at | DateTime | TimestampMixin |
| updated_at | DateTime | TimestampMixin |

- URL unique 제약 이름: `uq_raw_news_events_url`
- 중복 URL 저장 시도 시 `IntegrityError` 발생 → 레포지토리에서 catch해 `None` 반환 (upsert 없음)

### news_items 테이블

| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | Integer PK | |
| raw_news_event_id | Integer FK(raw_news_events.id) nullable | |
| asset_id | Integer FK(assets.id) | |
| title | String(500) | |
| url | String(2048) | |
| source | String(100) | |
| published_at | DateTime(timezone=True) nullable | |
| summary | Text nullable | AI 요약 채움 예정 |
| sentiment | String(20) nullable | positive/negative/neutral |
| impact_level | String(20) nullable | high/medium/low |
| created_at | DateTime | TimestampMixin |
| updated_at | DateTime | TimestampMixin |

- 인덱스: `ix_news_items_asset_id`

### job_runs 테이블

| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | Integer PK | |
| job_type | String(100) | 예: "news_collection", "watchlist_analysis" |
| status | String(20) | pending/running/success/failed |
| started_at | DateTime(timezone=True) nullable | |
| finished_at | DateTime(timezone=True) nullable | |
| error_message | Text nullable | |
| metadata | JSON nullable | 실행 파라미터 저장 |
| created_at | DateTime | TimestampMixin |
| updated_at | DateTime | TimestampMixin |

- `JobRunService.start(job_type, metadata)` → JobRun 생성 (status=running, started_at=now)
- `JobRunService.succeed(job_run_id)` → status=success, finished_at=now
- `JobRunService.fail(job_run_id, error_message)` → status=failed, finished_at=now, error_message 저장
- GET /api/v1/job-runs — 최근 50건, 내림차순 정렬

## Test Requirements

- `tests/test_raw_news.py`: 저장 성공, URL 중복 시 None 반환, collected_at 자동 설정
- `tests/test_news_items.py`: 생성 성공, asset_id로 목록 조회
- `tests/test_job_runs.py`: start→succeed 전이, start→fail 전이, API 목록 조회(200 + 결과 존재)

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_raw_news.py tests/test_news_items.py tests/test_job_runs.py -v
```

## Documentation Impact

없음.

## ADR Need

없음.

## Failure Record Need

없음.

## Risk Level

Low — 기존 도메인 패턴 반복. 신규 FK 참조 포함이나 기존 테이블(assets, raw_news_events) 변경 없음.

## Expected Output

- 위 scope 파일 전체 신규 생성
- Alembic 마이그레이션 4개 (raw_news, news_items, job_runs, merge head)
- `uv run pytest tests/test_raw_news.py tests/test_news_items.py tests/test_job_runs.py` 통과
- lint/typecheck 통과

## Rules

- 구현 전 설계 문서(`docs/designs/008-raw-news-domain.md`, `docs/designs/009-news-item-domain.md`, `docs/designs/012-job-runs-domain.md`)를 읽고 테이블 구조·시그니처를 설계 문서 기준으로 구현한다. 설계 문서와 충돌하는 구현은 금지한다.
- 스코프 외 파일 변경 금지.
- 테스트 약화 금지.
- 보호 파일 변경 금지.
- Alembic head는 merge revision으로 단일 head를 유지한다.
- `raw_news_events.url` unique 제약은 DB 레벨에서 보장한다.
