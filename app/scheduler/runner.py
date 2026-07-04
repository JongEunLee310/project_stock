import logging
from dataclasses import dataclass
from typing import Literal, Protocol

from app.scheduler.interface import SchedulerJobFunc
from app.scheduler.registry import SchedulerRegistry

logger = logging.getLogger(__name__)

SchedulerRunStatus = Literal["queued"]


class QueuedJob(Protocol):
    id: str


class SchedulerQueue(Protocol):
    def enqueue(self, f: SchedulerJobFunc) -> QueuedJob: ...


@dataclass(frozen=True)
class SchedulerRunResult:
    job_name: str
    job_id: str
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
        queue: SchedulerQueue,
    ) -> None:
        self.registry = registry
        self.queue = queue

    def run(self, job_name: str) -> SchedulerRunResult:
        schedule = self.registry.get(job_name)
        if schedule is None:
            raise SchedulerJobNotFoundError(job_name)
        if not schedule.enabled:
            raise SchedulerJobDisabledError(job_name)

        logger.info(
            "scheduler job queued",
            extra={"operation": "scheduler.run", "job_name": schedule.job.name},
        )
        queued_job = self.queue.enqueue(schedule.job.func)
        return SchedulerRunResult(
            job_name=schedule.job.name,
            job_id=str(queued_job.id),
            status="queued",
        )
