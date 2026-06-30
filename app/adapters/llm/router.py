from dataclasses import dataclass

from app.adapters.llm.exceptions import LLMRoutingError
from app.adapters.llm.types import LLMTaskType


@dataclass(frozen=True)
class TaskRoute:
    launch: str
    future_primary: str


LLM_TASK_ROUTES: dict[LLMTaskType, TaskRoute] = {
    LLMTaskType.NEWS_SUMMARY: TaskRoute(launch="cloud", future_primary="local"),
    LLMTaskType.THESIS_CONFLICT: TaskRoute(launch="cloud", future_primary="cloud"),
    LLMTaskType.PORTFOLIO_BRIEFING: TaskRoute(launch="cloud", future_primary="cloud"),
    LLMTaskType.DASHBOARD_BRIEFING: TaskRoute(launch="cloud", future_primary="local"),
    LLMTaskType.WATCHLIST_NOTE: TaskRoute(launch="cloud", future_primary="local"),
    LLMTaskType.TAG_SENTIMENT: TaskRoute(launch="cloud", future_primary="local"),
    LLMTaskType.AGENT: TaskRoute(launch="cloud", future_primary="cloud"),
}


class LLMRouter:
    def __init__(
        self,
        routes: dict[LLMTaskType, TaskRoute] | None = None,
    ) -> None:
        self.routes: dict[LLMTaskType, TaskRoute] = (
            LLM_TASK_ROUTES if routes is None else routes
        )

    def resolve(self, task_type: LLMTaskType) -> str:
        route = self.routes.get(task_type)
        if route is None:
            raise LLMRoutingError(f"LLM task route is not defined: {task_type!r}")
        return route.launch
