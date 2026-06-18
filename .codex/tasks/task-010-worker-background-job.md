# Codex Handoff Task

## Source Issue

Issue #11: Worker와 Background Job 구조 구현

## Task Summary

RQ(Redis Queue) 기반 Worker를 구성하고, 뉴스 수집과 관심 종목 분석 Job을 정의한다. FastAPI API에서 Job을 enqueue하고, Worker가 실행 이력을 `job_runs`에 기록한다.

## Goal

- API 요청으로 Background Job을 등록할 수 있다.
- Worker가 등록된 작업을 실행한다.
- FastAPI 요청 처리가 장시간 작업에 의해 막히지 않는다.

## Background

- **설계 문서를 구현 전에 반드시 읽는다:** `docs/designs/011-worker-background-job.md` — Worker 구조·Job 시그니처·API
- task-008(DB 도메인), task-009(Adapter) 완료 후 진행.
- **RQ 채택** (Celery 대비 경량, Redis가 이미 `pyproject.toml`에 있음).
- Redis 연결 설정은 `app/core/config.py`의 `Settings`에 `REDIS_URL: str = "redis://localhost:6379/0"` 추가.
- Docker Compose에 Worker 실행 방법을 README에 안내한다 (docker-compose.yml 변경 불필요).
- Job 함수는 독립적으로 테스트 가능하도록 설계한다 — Worker 데몬 없이도 직접 호출 가능.

## Implementation Scope

- `pyproject.toml` — `rq>=1.16.0` 의존성 추가 (dependencies 섹션)
- `uv.lock` — lock 파일 재생성 (`uv lock`)
- `app/worker/__init__.py`
- `app/worker/connection.py` — Redis 연결 (`get_redis_connection()`)
- `app/worker/jobs/news.py` — `collect_news_job(symbols: list[str])` 함수
- `app/worker/jobs/analysis.py` — `analyze_watchlist_job(watchlist_id: int)` 스텁 함수
- `app/worker/entrypoint.py` — `rq worker` 진입점 (큐 이름: `default`)
- `app/api/v1/endpoints/worker.py` — Job enqueue API 엔드포인트
- `app/api/v1/router.py` — worker 라우터 등록 추가
- `app/core/config.py` — `REDIS_URL` 필드 추가
- `tests/test_worker_jobs.py` — Job 함수 단위 테스트

## Out of Scope

- `analyze_watchlist_job` 실제 구현 (스텁으로 `pass` + log 처리, Issue #19에서 구현)
- Celery 설정
- Worker 프로세스 자동 시작 (docker-compose.yml 변경 없음)
- Job 스케줄링 (cron)
- Job 결과 조회 API (job_runs 목록은 task-008에서 구현됨)

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

### pyproject.toml 변경

`rq>=1.16.0`을 `dependencies`에 추가.

### app/core/config.py

`Settings`에 `REDIS_URL: str = "redis://localhost:6379/0"` 추가.

### app/worker/connection.py

```python
def get_redis_connection() -> Redis:
    from app.core.config import settings
    return Redis.from_url(settings.REDIS_URL)
```

### collect_news_job(symbols: list[str])

1. DB Session 생성
2. `JobRunService.start("news_collection", {"symbols": symbols})` → job_run
3. `MockNewsAdapter` (또는 설정된 Adapter)로 `RawNewsService.collect_and_save(adapter, symbols)` 호출
4. `JobRunService.succeed(job_run.id)` 호출
5. 예외 발생 시 `JobRunService.fail(job_run.id, str(e))` 호출 후 re-raise

### analyze_watchlist_job(watchlist_id: int)

스텁 구현:
```python
logger.info("analyze_watchlist_job called: watchlist_id=%s (not implemented)", watchlist_id)
```
JobRun 기록 포함.

### API 엔드포인트

`POST /api/v1/worker/jobs/news`
- Request body: `{ "symbols": ["AAPL", "TSLA"] }`
- RQ Queue에 `collect_news_job` enqueue
- Response: `{ "job_id": "<rq-job-id>", "status": "queued" }`

`POST /api/v1/worker/jobs/analysis`
- Request body: `{ "watchlist_id": 1 }`
- RQ Queue에 `analyze_watchlist_job` enqueue
- Response: `{ "job_id": "<rq-job-id>", "status": "queued" }`

### app/worker/entrypoint.py

```python
# rq worker 실행 진입점
# 사용: uv run python -m app.worker.entrypoint
```
`rq.Worker(["default"], connection=get_redis_connection()).work()` 호출.

## Test Requirements

- `tests/test_worker_jobs.py`:
  - `collect_news_job`: DB(SQLite in-memory) + MockNewsAdapter로 직접 호출 → `job_runs` status=success 검증
  - `collect_news_job`: 예외 발생 시 status=failed, error_message 저장 검증
  - API `POST /api/v1/worker/jobs/news`: RQ enqueue를 mock 처리, 응답 200 + job_id 포함 검증
- RQ Worker 데몬 실행은 테스트하지 않는다 (외부 프로세스).

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_worker_jobs.py -v
```

## Documentation Impact

없음.

## ADR Need

없음 — RQ 선택은 MVP 단계의 가역적 결정이므로 ADR 불필요.

## Failure Record Need

없음.

## Risk Level

Medium — `pyproject.toml` 변경 포함. Worker 구조는 기존 패턴이 없어 신규 설계. Job 함수가 DB Session을 직접 생성하므로 테스트 격리에 주의 필요.

## Expected Output

- 위 scope 파일 전체 신규 생성
- `pyproject.toml`에 `rq>=1.16.0` 추가
- `uv run pytest tests/test_worker_jobs.py` 통과
- lint/typecheck 통과

## Rules

- 구현 전 설계 문서(`docs/designs/011-worker-background-job.md`)를 읽고 모듈 구조·Job 시그니처·API를 설계 문서 기준으로 구현한다. 설계 문서와 충돌하는 구현은 금지한다.
- task-008, task-009 완료 확인 후 진행.
- Job 함수는 Worker 데몬 없이 직접 호출 가능해야 한다.
- `docker-compose.yml`, `.github/workflows/ci.yml` 변경 금지.
- 스코프 외 파일 변경 금지.
- 테스트 약화 금지.
- 보호 파일 변경 금지.
