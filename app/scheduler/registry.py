from dataclasses import dataclass

from app.scheduler.interface import FunctionSchedulerJob, SchedulerJob
from app.worker.jobs.news import collect_news_job
from app.worker.jobs.prices import collect_prices_job


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
    ]
)
