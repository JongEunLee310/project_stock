# Design: Worker & Background Job (Issue #11)

## 구조 결정

RQ(Redis Queue) 채택. Redis가 이미 의존성에 포함되어 있고 MVP 규모에서 Celery는 과함.

## 모듈 구조

```
app/worker/
  connection.py   — Redis 연결
  entrypoint.py   — rq worker 진입점
  jobs/
    news.py       — collect_news_job
    analysis.py   — analyze_watchlist_job (스텁)
```

## Job 함수 시그니처

- `collect_news_job(symbols: list[str]) -> None` — 뉴스 수집 후 raw_news_events 저장, job_runs 이력 기록
- `analyze_watchlist_job(watchlist_id: int) -> None` — 스텁 (Issue #19에서 구현)

## Worker 연결

- `get_redis_connection() -> Redis` — settings.REDIS_URL 기반

## API

| Method | Path | 요청 | 응답 |
|---|---|---|---|
| POST | /api/v1/worker/jobs/news | `{ "symbols": list[str] }` | `{ "job_id": str, "status": "queued" }` |
| POST | /api/v1/worker/jobs/analysis | `{ "watchlist_id": int }` | `{ "job_id": str, "status": "queued" }` |

## 설정 추가

`app/core/config.py` — `REDIS_URL: str = "redis://localhost:6379/0"`

## 외부 의존성

- `rq>=1.16.0`

## 의존성

- Issue #8 (RawNewsEvent 도메인)
- Issue #10 (NewsAdapter)
- Issue #12 (JobRun 도메인)
