from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.jobs.service import JobRunService
from tests.conftest import TestingSessionLocal


def test_job_run_start_to_succeed_transition(db: Session) -> None:
    service = JobRunService(db)
    job_run = service.start("news_collection", {"source": "example"})

    assert job_run.status == "running"
    assert job_run.started_at is not None

    succeeded_job_run = service.succeed(job_run.id)

    assert succeeded_job_run.status == "success"
    assert succeeded_job_run.finished_at is not None


def test_job_run_start_to_fail_transition(db: Session) -> None:
    service = JobRunService(db)
    job_run = service.start("news_collection")

    failed_job_run = service.fail(job_run.id, "adapter timeout")

    assert failed_job_run.status == "failed"
    assert failed_job_run.finished_at is not None
    assert failed_job_run.error_message == "adapter timeout"


def test_job_runs_api_lists_recent_runs(client: TestClient) -> None:
    with TestingSessionLocal() as db:
        job_run = JobRunService(db).start("news_collection", {"source": "example"})
        JobRunService(db).succeed(job_run.id)

    response = client.get("/api/v1/job-runs")

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], response.json())
    assert len(data) == 1
    assert data[0]["job_type"] == "news_collection"
    assert data[0]["status"] == "success"
    assert data[0]["started_at"] is not None
    assert data[0]["finished_at"] is not None
