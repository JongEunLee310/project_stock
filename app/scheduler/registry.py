from dataclasses import dataclass

from app.core.config import settings
from app.scheduler.interface import FunctionSchedulerJob, SchedulerJob
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
from app.worker.jobs.timeouts import (
    DAILY_RESEARCH_JOB_TIMEOUT,
    EMBED_DOCUMENTS_JOB_TIMEOUT,
    FILING_ANALYSIS_JOB_TIMEOUT,
    FILING_COLLECTION_JOB_TIMEOUT,
)


@dataclass(frozen=True)
class ScheduleDefinition:
    job: SchedulerJob
    cron: str
    enabled: bool = True
    job_timeout: int | None = None


class SchedulerRegistry:
    def __init__(self, schedules: list[ScheduleDefinition]) -> None:
        self._schedules = {schedule.job.name: schedule for schedule in schedules}

    def get(self, job_name: str) -> ScheduleDefinition | None:
        return self._schedules.get(job_name)

    def list(self) -> list[ScheduleDefinition]:
        return list(self._schedules.values())


default_scheduler_registry = SchedulerRegistry(
    [
        ScheduleDefinition(
            job=FunctionSchedulerJob(
                name="filing_analysis_agent", func=run_filing_analysis_job
            ),
            cron="30 1 * * 6",
            enabled=True,
            job_timeout=FILING_ANALYSIS_JOB_TIMEOUT,
        ),
        ScheduleDefinition(
            job=FunctionSchedulerJob(
                name="filing_collection", func=collect_filings_job
            ),
            cron="0 1 * * 6",
            enabled=True,
            job_timeout=FILING_COLLECTION_JOB_TIMEOUT,
        ),
        ScheduleDefinition(
            job=FunctionSchedulerJob(
                name="decision_review_trigger_evaluation",
                func=evaluate_decision_review_triggers_job,
            ),
            cron="*/5 * * * *",
            enabled=True,
        ),
        ScheduleDefinition(
            job=FunctionSchedulerJob(
                name="alert_evaluation",
                func=evaluate_alert_rules_job,
            ),
            cron="*/5 * * * *",
            enabled=settings.ALERT_ENGINE_ENABLED,
        ),
        ScheduleDefinition(
            job=FunctionSchedulerJob(
                name="price_collection",
                func=collect_prices_job,
            ),
            cron="10 22 * * 1-5",
            enabled=True,
        ),
        ScheduleDefinition(
            job=FunctionSchedulerJob(
                name="news_collection",
                func=collect_news_job,
            ),
            cron="0 * * * *",
            enabled=True,
        ),
        ScheduleDefinition(
            job=FunctionSchedulerJob(name="embed_documents", func=embed_documents_job),
            cron="20 * * * *",
            enabled=True,
            job_timeout=EMBED_DOCUMENTS_JOB_TIMEOUT,
        ),
        ScheduleDefinition(
            job=FunctionSchedulerJob(
                name="daily_research_agent",
                func=run_daily_research_job,
            ),
            cron="30 22 * * 0-4",
            enabled=True,
            job_timeout=DAILY_RESEARCH_JOB_TIMEOUT,
        ),
        ScheduleDefinition(
            job=FunctionSchedulerJob(
                name="signal_snapshot",
                func=snapshot_signal_states_job,
            ),
            cron="30 11 * * 1-5",
            enabled=True,
        ),
    ]
)
