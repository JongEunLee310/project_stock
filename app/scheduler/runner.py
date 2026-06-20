import logging
from dataclasses import dataclass
from typing import Literal

from app.domains.jobs.service import JobRunService
from app.scheduler.registry import SchedulerRegistry

logger = logging.getLogger(__name__)

SchedulerRunStatus = Literal["success", "failed"]


@dataclass(frozen=True)
class SchedulerRunResult:
    job_name: str
    job_run_id: int
    status: SchedulerRunStatus


class SchedulerJobNotFoundError(ValueError):
    def __init__(self, job_name: str) -> None:
        super().__init__(f"scheduler job not found: {job_name}")
        self.job_name = job_name


class SchedulerJobDisabledError(ValueError):
    def __init__(self, job_name: str) -> None:
        super().__init__(f"scheduler job is disabled: {job_name}")
        self.job_name = job_name


class ManualSchedulerRunner:
    def __init__(
        self,
        registry: SchedulerRegistry,
        job_run_service: JobRunService,
    ) -> None:
        self.registry = registry
        self.job_run_service = job_run_service

    def run_once(self, job_name: str) -> SchedulerRunResult:
        schedule = self.registry.get(job_name)
        if schedule is None:
            raise SchedulerJobNotFoundError(job_name)
        if not schedule.enabled:
            raise SchedulerJobDisabledError(job_name)

        metadata = {
            "trigger": "manual",
            "cron": schedule.cron,
            "scheduler": "mock",
        }
        job_run = self.job_run_service.start(schedule.job.name, metadata)
        try:
            logger.info(
                "scheduler job started",
                extra={"operation": "scheduler.run_once"},
            )
            schedule.job.run()
            self.job_run_service.succeed(job_run.id)
            logger.info(
                "scheduler job succeeded",
                extra={"operation": "scheduler.run_once"},
            )
            return SchedulerRunResult(
                job_name=schedule.job.name,
                job_run_id=job_run.id,
                status="success",
            )
        except Exception as exc:
            self.job_run_service.fail(job_run.id, str(exc))
            logger.exception(
                "scheduler job failed",
                extra={"operation": "scheduler.run_once"},
            )
            raise
