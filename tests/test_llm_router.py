from typing import cast

import pytest

from app.adapters.llm.exceptions import LLMRoutingError
from app.adapters.llm.router import LLM_TASK_ROUTES, LLMRouter
from app.adapters.llm.types import LLMTaskType


def test_llm_router_resolves_launch_provider_for_all_task_types() -> None:
    router = LLMRouter()

    for task_type in LLMTaskType:
        assert router.resolve(task_type) == "cloud"


def test_llm_task_routes_cover_all_task_types() -> None:
    assert set(LLM_TASK_ROUTES) == set(LLMTaskType)


def test_llm_router_fails_closed_for_undefined_task_type() -> None:
    router = LLMRouter({})
    undefined_task_type = cast(LLMTaskType, "UNKNOWN_TASK")

    with pytest.raises(LLMRoutingError, match="route is not defined"):
        router.resolve(undefined_task_type)


def test_llm_task_routes_record_future_primary_provider() -> None:
    assert {
        task_type: route.future_primary for task_type, route in LLM_TASK_ROUTES.items()
    } == {
        LLMTaskType.NEWS_SUMMARY: "local",
        LLMTaskType.THESIS_CONFLICT: "cloud",
        LLMTaskType.PORTFOLIO_BRIEFING: "cloud",
        LLMTaskType.DASHBOARD_BRIEFING: "local",
        LLMTaskType.WATCHLIST_NOTE: "local",
        LLMTaskType.TAG_SENTIMENT: "local",
        LLMTaskType.AGENT: "cloud",
    }
