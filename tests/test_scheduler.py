from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.jobs.model import JobRun
from app.domains.jobs.service import JobRunService
from app.scheduler.interface import FunctionSchedulerJob
from app.scheduler.registry import ScheduleDefinition, SchedulerRegistry
from app.scheduler.runner import ManualSchedulerRunner
from tests.conftest import TestingSessionLocal, api_data


def test_function_scheduler_job_runs_wrapped_callable() -> None:
    calls: list[str] = []
    job = FunctionSchedulerJob("example", lambda: calls.append("ran"))

    job.run()

    assert calls == ["ran"]


def test_manual_scheduler_runner_records_success(db: Session) -> None:
    registry = SchedulerRegistry(
        [
            ScheduleDefinition(
                job=FunctionSchedulerJob("mock_collection", lambda: None),
                cron="*/15 * * * *",
            )
        ]
    )

    result = ManualSchedulerRunner(registry, JobRunService(db)).run_once(
        "mock_collection"
    )

    job_run = db.scalars(select(JobRun)).one()
    assert result.job_name == "mock_collection"
    assert result.job_run_id == job_run.id
    assert result.status == "success"
    assert job_run.job_type == "mock_collection"
    assert job_run.status == "success"
    assert job_run.started_at is not None
    assert job_run.finished_at is not None
    assert job_run.metadata_ == {
        "trigger": "manual",
        "cron": "*/15 * * * *",
        "scheduler": "mock",
    }


def test_manual_scheduler_runner_records_failure(db: Session) -> None:
    def fail() -> None:
        raise RuntimeError("mock failure")

    registry = SchedulerRegistry(
        [
            ScheduleDefinition(
                job=FunctionSchedulerJob("mock_collection", fail),
                cron="*/15 * * * *",
            )
        ]
    )

    with pytest.raises(RuntimeError, match="mock failure"):
        ManualSchedulerRunner(registry, JobRunService(db)).run_once("mock_collection")

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.job_type == "mock_collection"
    assert job_run.status == "failed"
    assert job_run.finished_at is not None
    assert job_run.error_message == "mock failure"


def test_run_scheduler_job_once_api_records_job_run(client: TestClient) -> None:
    response = client.post("/api/v1/worker/scheduler/jobs/mock_collection/run")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["job_name"] == "mock_collection"
    assert data["status"] == "success"
    assert isinstance(data["job_run_id"], int)

    with TestingSessionLocal() as db:
        job_run = db.scalars(select(JobRun)).one()
        assert job_run.id == data["job_run_id"]
        assert job_run.job_type == "mock_collection"
        assert job_run.status == "success"


def test_run_scheduler_job_once_api_returns_404_for_unknown_job(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/worker/scheduler/jobs/unknown/run")

    assert response.status_code == 404
    assert response.json()["detail"] == "scheduler job not found"
