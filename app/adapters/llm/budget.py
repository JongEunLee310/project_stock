from datetime import UTC, datetime
from typing import Protocol

from app.adapters.llm.exceptions import LLMBudgetExceededError


class RedisCounter(Protocol):
    def incr(self, name: str) -> int: ...

    def expire(self, name: str, time: int) -> object: ...


class DailyCallBudget:
    def __init__(self, redis: RedisCounter, limit: int) -> None:
        self.redis = redis
        self.limit = limit

    def consume(self) -> None:
        key = f"llm:cloud_calls:{datetime.now(UTC).strftime('%Y%m%d')}"
        count = self.redis.incr(key)
        if count == 1:
            self.redis.expire(key, 2 * 24 * 60 * 60)
        if count > self.limit:
            raise LLMBudgetExceededError("daily cloud LLM call limit exceeded")
