from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

SchedulerJobFunc = Callable[..., None]


class SchedulerJob(Protocol):
    @property
    def name(self) -> str:
        """Stable scheduler job name used in registries and logs."""

    @property
    def func(self) -> SchedulerJobFunc:
        """Worker job function enqueued by scheduler triggers."""


@dataclass(frozen=True)
class FunctionSchedulerJob:
    name: str
    func: SchedulerJobFunc
