from dataclasses import dataclass

from app.core.config import settings
from app.scheduler.interface import FunctionSchedulerJob, SchedulerJob
from app.worker.jobs.analysis import analyze_all_watchlists_job
from app.worker.jobs.alerts import evaluate_alert_rules_job
from app.worker.jobs.news import collect_news_job
from app.worker.jobs.prices import collect_prices_job
from app.worker.jobs.signal_snapshots import snapshot_signal_states_job


@dataclass(frozen=True)
class ScheduleDefinition:
    job: SchedulerJob
    cron: str
    enabled: bool = True


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
            job=FunctionSchedulerJob(
                name="analysis_kr_open",
                func=analyze_all_watchlists_job,
            ),
            cron="0 23 * * 0-4",
            enabled=settings.ANALYSIS_SCHEDULE_ENABLED,
        ),
        ScheduleDefinition(
            job=FunctionSchedulerJob(
                name="analysis_kr_main",
                func=analyze_all_watchlists_job,
            ),
            cron="0 0-7 * * 1-5",
            enabled=settings.ANALYSIS_SCHEDULE_ENABLED,
        ),
        ScheduleDefinition(
            job=FunctionSchedulerJob(
                name="analysis_us_session",
                func=analyze_all_watchlists_job,
            ),
            cron="0 13-21 * * 1-5",
            enabled=settings.ANALYSIS_SCHEDULE_ENABLED,
        ),
        ScheduleDefinition(
            job=FunctionSchedulerJob(
                name="analysis_kr_post",
                func=analyze_all_watchlists_job,
            ),
            cron="0 9,11 * * 1-5",
            enabled=settings.ANALYSIS_SCHEDULE_ENABLED,
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
