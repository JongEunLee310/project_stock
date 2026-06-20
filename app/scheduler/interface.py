from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class SchedulerJob(Protocol):
    @property
    def name(self) -> str:
        """Stable scheduler job name used in registries and logs."""

    def run(self) -> None:
        """Execute the job once."""


@dataclass(frozen=True)
class FunctionSchedulerJob:
    name: str
    func: Callable[[], None]

    def run(self) -> None:
        self.func()
