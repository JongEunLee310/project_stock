from datetime import UTC, datetime

import pytest

from app.adapters.llm.budget import DailyCallBudget
from app.adapters.llm.exceptions import LLMBudgetExceededError, LLMCallError


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expires: list[tuple[str, int]] = []

    def incr(self, name: str) -> int:
        self.counts[name] = self.counts.get(name, 0) + 1
        return self.counts[name]

    def expire(self, name: str, time: int) -> bool:
        self.expires.append((name, time))
        return True


def test_daily_call_budget_allows_calls_up_to_limit() -> None:
    redis = FakeRedis()
    budget = DailyCallBudget(redis, limit=2)

    budget.consume()
    budget.consume()

    key = f"llm:cloud_calls:{datetime.now(UTC).strftime('%Y%m%d')}"
    assert redis.counts == {key: 2}
    assert redis.expires == [(key, 2 * 24 * 60 * 60)]


def test_daily_call_budget_raises_after_limit_is_exceeded() -> None:
    redis = FakeRedis()
    budget = DailyCallBudget(redis, limit=1)

    budget.consume()

    with pytest.raises(LLMBudgetExceededError):
        budget.consume()


def test_llm_budget_exceeded_error_is_llm_call_error() -> None:
    assert issubclass(LLMBudgetExceededError, LLMCallError)
