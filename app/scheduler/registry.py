from dataclasses import dataclass

from app.scheduler.interface import FunctionSchedulerJob, SchedulerJob
from app.scheduler.jobs import run_mock_collection_job


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
                name="mock_collection",
                func=run_mock_collection_job,
            ),
            cron="*/15 * * * *",
            enabled=True,
        )
    ]
)
