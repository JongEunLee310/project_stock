import importlib
import sys
from collections.abc import Callable
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.worker import get_scheduler_runner
from app.main import app
from app.scheduler.interface import FunctionSchedulerJob
from app.scheduler.registry import (
    ScheduleDefinition,
    SchedulerRegistry,
    default_scheduler_registry,
)
from app.scheduler.runner import ManualSchedulerRunner
from app.worker.jobs.news import collect_news_job
from app.worker.jobs.prices import collect_prices_job
from tests.conftest import api_data


class FakeQueuedJob:
    def __init__(self, job_id: str) -> None:
        self.id = job_id


class FakeQueue:
    def __init__(self, job_id: str = "rq-job-1") -> None:
        self.job_id = job_id
        self.enqueued: list[Callable[..., None]] = []

    def enqueue(self, f: Callable[..., None]) -> FakeQueuedJob:
        self.enqueued.append(f)
        return FakeQueuedJob(self.job_id)


def test_function_scheduler_job_keeps_worker_function_reference() -> None:
    def example_job() -> None:
        return None

    job = FunctionSchedulerJob("example", example_job)

    assert job.name == "example"
    assert job.func is example_job


def test_manual_scheduler_runner_enqueues_registered_job() -> None:
    queue = FakeQueue("price-rq-job")
    registry = SchedulerRegistry(
        [
            ScheduleDefinition(
                job=FunctionSchedulerJob("price_collection", collect_prices_job),
                cron="10 22 * * 1-5",
            )
        ]
    )

    result = ManualSchedulerRunner(registry, queue).run("price_collection")

    assert queue.enqueued == [collect_prices_job]
    assert result.job_name == "price_collection"
    assert result.job_id == "price-rq-job"
    assert result.status == "queued"


def test_manual_scheduler_runner_rejects_disabled_job() -> None:
    queue = FakeQueue()
    registry = SchedulerRegistry(
        [
            ScheduleDefinition(
                job=FunctionSchedulerJob("price_collection", collect_prices_job),
                cron="10 22 * * 1-5",
                enabled=False,
            )
        ]
    )

    with pytest.raises(ValueError, match="scheduler job is disabled"):
        ManualSchedulerRunner(registry, queue).run("price_collection")

    assert queue.enqueued == []


def test_default_scheduler_registry_contains_only_collection_jobs() -> None:
    schedules = default_scheduler_registry.list()
    schedules_by_name = {schedule.job.name: schedule for schedule in schedules}

    assert set(schedules_by_name) == {"price_collection", "news_collection"}
    assert schedules_by_name["price_collection"].job.func is collect_prices_job
    assert schedules_by_name["price_collection"].cron == "10 22 * * 1-5"
    assert schedules_by_name["news_collection"].job.func is collect_news_job
    assert schedules_by_name["news_collection"].cron == "0 * * * *"
    assert {schedule.job.func for schedule in schedules} <= {
        collect_prices_job,
        collect_news_job,
    }


def test_cron_config_registers_enabled_scheduler_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered: list[tuple[Callable[..., None], str, str | None]] = []

    def fake_register(
        func: Callable[..., None],
        queue_name: str,
        *,
        cron: str | None = None,
        **_: object,
    ) -> dict[str, object]:
        registered.append((func, queue_name, cron))
        return {}

    import rq.cron

    monkeypatch.setattr(rq.cron, "register", fake_register)
    sys.modules.pop("app.scheduler.cron_config", None)

    importlib.import_module("app.scheduler.cron_config")

    assert registered == [
        (collect_prices_job, "default", "10 22 * * 1-5"),
        (collect_news_job, "default", "0 * * * *"),
    ]


def test_run_scheduler_job_once_api_returns_queued_job_id(
    client: TestClient,
) -> None:
    queue = FakeQueue("api-rq-job")

    def override_get_scheduler_runner() -> ManualSchedulerRunner:
        return ManualSchedulerRunner(default_scheduler_registry, queue)

    app.dependency_overrides[get_scheduler_runner] = override_get_scheduler_runner

    response = client.post("/api/v1/worker/scheduler/jobs/price_collection/run")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data == {
        "job_name": "price_collection",
        "job_id": "api-rq-job",
        "status": "queued",
    }
    assert queue.enqueued == [collect_prices_job]


def test_run_scheduler_job_once_api_returns_404_for_unknown_job(
    client: TestClient,
) -> None:
    queue = FakeQueue()

    def override_get_scheduler_runner() -> ManualSchedulerRunner:
        return ManualSchedulerRunner(default_scheduler_registry, queue)

    app.dependency_overrides[get_scheduler_runner] = override_get_scheduler_runner

    response = client.post("/api/v1/worker/scheduler/jobs/unknown/run")

    assert response.status_code == 404
    assert response.json()["detail"] == "scheduler job not found"
    assert queue.enqueued == []


def test_run_scheduler_job_once_api_returns_409_for_disabled_job(
    client: TestClient,
) -> None:
    queue = FakeQueue()
    registry = SchedulerRegistry(
        [
            ScheduleDefinition(
                job=FunctionSchedulerJob("price_collection", collect_prices_job),
                cron="10 22 * * 1-5",
                enabled=False,
            )
        ]
    )

    def override_get_scheduler_runner() -> ManualSchedulerRunner:
        return ManualSchedulerRunner(registry, queue)

    app.dependency_overrides[get_scheduler_runner] = override_get_scheduler_runner

    response = client.post("/api/v1/worker/scheduler/jobs/price_collection/run")

    assert response.status_code == 409
    assert response.json()["detail"] == "scheduler job is disabled"
    assert queue.enqueued == []
