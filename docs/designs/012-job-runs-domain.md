# Design: Job Run 실행 이력 (Issue #12)

## 테이블: job_runs

| 필드 | 타입 | 제약 |
|---|---|---|
| id | Integer | PK |
| job_type | String(100) | NOT NULL |
| status | String(20) | NOT NULL (pending/running/success/failed) |
| started_at | DateTime(tz) | nullable |
| finished_at | DateTime(tz) | nullable |
| error_message | Text | nullable |
| metadata | JSON | nullable |
| created_at | DateTime(tz) | NOT NULL |
| updated_at | DateTime(tz) | NOT NULL |

## 스키마

- `JobRunCreate`: job_type, metadata
- `JobRunResponse`: id, job_type, status, started_at, finished_at, error_message, created_at

## Repository

- `create(job_type: str, metadata: dict | None) -> JobRun`
- `update_status(id: int, status: str, **kwargs) -> JobRun`
- `list_recent(limit: int) -> list[JobRun]`

## Service

- `start(job_type: str, metadata: dict | None) -> JobRun` — status=running, started_at=now
- `succeed(job_run_id: int) -> JobRun` — status=success, finished_at=now
- `fail(job_run_id: int, error_message: str) -> JobRun` — status=failed, finished_at=now, error_message 저장

## API

| Method | Path | 요청 | 응답 |
|---|---|---|---|
| GET | /api/v1/job-runs | ?limit=50 | list[JobRunResponse] |

## 의존성

없음 (독립 도메인)

## Alembic 마이그레이션

신규 파일: `alembic/versions/<rev>_create_job_runs_table.py`  
`down_revision`: `8c3f0d2b7a91`  
별도 merge revision으로 raw_news_events 마이그레이션과 단일 head 유지.
