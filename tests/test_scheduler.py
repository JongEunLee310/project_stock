import importlib
import sys
from collections.abc import Callable
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.worker import get_scheduler_runner
from app.core.config import Settings, settings as runtime_settings
from app.main import app
from app.scheduler.interface import FunctionSchedulerJob
from app.scheduler.registry import (
    ScheduleDefinition,
    SchedulerRegistry,
    default_scheduler_registry,
)
from app.scheduler.runner import ManualSchedulerRunner
from app.worker.jobs.agents import run_daily_research_job, run_filing_analysis_job
from app.worker.jobs.alerts import evaluate_alert_rules_job
from app.worker.jobs.decision_review_triggers import (
    evaluate_decision_review_triggers_job,
)
from app.worker.jobs.filings import collect_filings_job
from app.worker.jobs.news import collect_news_job
from app.worker.jobs.prices import collect_prices_job
from app.worker.jobs.rag import embed_documents_job
from app.worker.jobs.signal_snapshots import snapshot_signal_states_job
from tests.conftest import api_data


class FakeQueuedJob:
    def __init__(self, job_id: str) -> None:
        self.id = job_id


class FakeQueue:
    def __init__(self, job_id: str = "rq-job-1") -> None:
        self.job_id = job_id
        self.enqueued: list[Callable[..., object]] = []
        self.timeouts: list[int | None] = []

    def enqueue(
        self, f: Callable[..., object], *, job_timeout: int | None = None
    ) -> FakeQueuedJob:
        self.enqueued.append(f)
        self.timeouts.append(job_timeout)
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
    assert queue.timeouts == [None]
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


def test_default_scheduler_registry_contains_expected_jobs() -> None:
    schedules = default_scheduler_registry.list()
    schedules_by_name = {schedule.job.name: schedule for schedule in schedules}

    assert set(schedules_by_name) == {
        "filing_collection",
        "filing_analysis_agent",
        "price_collection",
        "news_collection",
        "embed_documents",
        "daily_research_agent",
        "signal_snapshot",
        "alert_evaluation",
        "decision_review_trigger_evaluation",
    }
    assert schedules_by_name["filing_collection"].job.func is collect_filings_job
    assert schedules_by_name["filing_collection"].cron == "0 1 * * 6"
    assert schedules_by_name["filing_collection"].enabled is True
    assert schedules_by_name["price_collection"].job.func is collect_prices_job
    assert schedules_by_name["price_collection"].cron == "10 22 * * 1-5"
    assert schedules_by_name["news_collection"].job.func is collect_news_job
    assert schedules_by_name["news_collection"].cron == "0 * * * *"
    assert schedules_by_name["embed_documents"].job.func is embed_documents_job
    assert schedules_by_name["embed_documents"].cron == "20 * * * *"
    assert schedules_by_name["embed_documents"].enabled is True
    assert schedules_by_name["signal_snapshot"].job.func is snapshot_signal_states_job
    assert schedules_by_name["signal_snapshot"].cron == "30 11 * * 1-5"
    assert schedules_by_name["alert_evaluation"].job.func is evaluate_alert_rules_job
    assert schedules_by_name["alert_evaluation"].cron == "*/5 * * * *"
    assert schedules_by_name["alert_evaluation"].enabled is False
    assert (
        schedules_by_name["decision_review_trigger_evaluation"].job.func
        is evaluate_decision_review_triggers_job
    )
    assert schedules_by_name["decision_review_trigger_evaluation"].cron == "*/5 * * * *"
    assert schedules_by_name["decision_review_trigger_evaluation"].enabled is True
    daily = schedules_by_name["daily_research_agent"]
    assert daily.job.func is run_daily_research_job
    assert daily.cron == "30 22 * * 0-4"
    assert daily.enabled is True
    assert not any(name.startswith("analysis_") for name in schedules_by_name)
    assert not any(name.startswith("ANALYSIS_") for name in Settings.model_fields)


def test_alert_engine_enabled_flag_controls_alert_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.scheduler.registry as registry_module

    monkeypatch.delenv("ALERT_ENGINE_ENABLED", raising=False)
    assert Settings().ALERT_ENGINE_ENABLED is False
    monkeypatch.setenv("ALERT_ENGINE_ENABLED", "true")
    assert Settings().ALERT_ENGINE_ENABLED is True

    monkeypatch.setattr(runtime_settings, "ALERT_ENGINE_ENABLED", True)
    reloaded = importlib.reload(registry_module)
    schedule = reloaded.default_scheduler_registry.get("alert_evaluation")

    assert schedule is not None
    assert schedule.enabled is True

    monkeypatch.setattr(runtime_settings, "ALERT_ENGINE_ENABLED", False)
    importlib.reload(reloaded)


def test_cron_config_registers_enabled_scheduler_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered: list[tuple[Callable[..., object], str, str | None, int | None]] = []

    def fake_register(
        func: Callable[..., object],
        queue_name: str,
        *,
        cron: str | None = None,
        job_timeout: int | None = None,
        **_: object,
    ) -> dict[str, object]:
        registered.append((func, queue_name, cron, job_timeout))
        return {}

    import rq.cron

    monkeypatch.setattr(rq.cron, "register", fake_register)
    sys.modules.pop("app.scheduler.cron_config", None)

    importlib.import_module("app.scheduler.cron_config")

    assert registered == [
        (run_filing_analysis_job, "default", "30 1 * * 6", 1800),
        (collect_filings_job, "default", "0 1 * * 6", 900),
        (evaluate_decision_review_triggers_job, "default", "*/5 * * * *", None),
        (collect_prices_job, "default", "10 22 * * 1-5", None),
        (collect_news_job, "default", "0 * * * *", None),
        (embed_documents_job, "default", "20 * * * *", 1800),
        (run_daily_research_job, "default", "30 22 * * 0-4", 3600),
        (snapshot_signal_states_job, "default", "30 11 * * 1-5", None),
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


@pytest.mark.parametrize(
    ("job_name", "expected_timeout"),
    [
        ("embed_documents", 1800),
        ("daily_research_agent", 3600),
        ("filing_collection", 900),
        ("price_collection", None),
        ("news_collection", None),
        ("signal_snapshot", None),
        ("alert_evaluation", None),
        ("decision_review_trigger_evaluation", None),
    ],
)
def test_schedule_timeout_and_manual_enqueue(
    job_name: str, expected_timeout: int | None
) -> None:
    schedule = default_scheduler_registry.get(job_name)
    assert schedule is not None
    assert schedule.job_timeout == expected_timeout
    if schedule.enabled:
        queue = FakeQueue()
        ManualSchedulerRunner(default_scheduler_registry, queue).run(job_name)
        assert queue.enqueued == [schedule.job.func]
        assert queue.timeouts == [expected_timeout]
