from datetime import date
from typing import ClassVar

from pydantic import BaseModel

from app.adapters.llm.cache import LLMCache
from app.adapters.llm.privacy import CloudSafePayload
from app.adapters.llm.types import LLMTaskType, SensitivityLevel


class FakeRedisCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.setex_calls: list[tuple[str, int, str]] = []

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def setex(self, name: str, time: int, value: str) -> bool:
        self.setex_calls.append((name, time, value))
        self.values[name] = value
        return True


class ExamplePayload(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.AGGREGATED

    value: str
    count: int


class ExampleSchema(BaseModel):
    summary: str


class ExpandedSchema(BaseModel):
    summary: str
    risk: str


def make_cache() -> LLMCache:
    return LLMCache(FakeRedisCache(), ttl=300)


def make_payload() -> ExamplePayload:
    return ExamplePayload(value="stable", count=3)


def test_cache_miss_returns_none() -> None:
    cache = make_cache()

    assert cache.get_cached("llm:cache:missing") is None


def test_cache_put_then_hit_returns_value() -> None:
    cache = make_cache()

    cache.put("llm:cache:key", '{"summary":"ok"}')

    assert cache.get_cached("llm:cache:key") == '{"summary":"ok"}'


def test_cache_put_passes_ttl_to_redis() -> None:
    redis = FakeRedisCache()
    cache = LLMCache(redis, ttl=123)

    cache.put("llm:cache:key", "value")

    assert redis.setex_calls == [("llm:cache:key", 123, "value")]


def test_compute_key_is_deterministic_for_same_inputs() -> None:
    cache = make_cache()

    first = cache.compute_key(
        LLMTaskType.PORTFOLIO_BRIEFING,
        7,
        make_payload(),
        "system prompt",
        ExampleSchema,
        "v1",
        on_date=date(2026, 7, 4),
    )
    second = cache.compute_key(
        LLMTaskType.PORTFOLIO_BRIEFING,
        7,
        make_payload(),
        "system prompt",
        ExampleSchema,
        "v1",
        on_date=date(2026, 7, 4),
    )

    assert first == second
    assert first.startswith("llm:cache:")


def test_compute_key_changes_when_prompt_changes() -> None:
    cache = make_cache()

    first = cache.compute_key(
        LLMTaskType.PORTFOLIO_BRIEFING,
        7,
        make_payload(),
        "system prompt",
        ExampleSchema,
        "v1",
        on_date=date(2026, 7, 4),
    )
    second = cache.compute_key(
        LLMTaskType.PORTFOLIO_BRIEFING,
        7,
        make_payload(),
        "system prompt changed",
        ExampleSchema,
        "v1",
        on_date=date(2026, 7, 4),
    )

    assert first != second


def test_compute_key_changes_when_schema_changes() -> None:
    cache = make_cache()

    first = cache.compute_key(
        LLMTaskType.PORTFOLIO_BRIEFING,
        7,
        make_payload(),
        "system prompt",
        ExampleSchema,
        "v1",
        on_date=date(2026, 7, 4),
    )
    second = cache.compute_key(
        LLMTaskType.PORTFOLIO_BRIEFING,
        7,
        make_payload(),
        "system prompt",
        ExpandedSchema,
        "v1",
        on_date=date(2026, 7, 4),
    )

    assert first != second


def test_compute_key_changes_when_date_bucket_changes() -> None:
    cache = make_cache()

    first = cache.compute_key(
        LLMTaskType.PORTFOLIO_BRIEFING,
        7,
        make_payload(),
        "system prompt",
        ExampleSchema,
        "v1",
        on_date=date(2026, 7, 4),
    )
    second = cache.compute_key(
        LLMTaskType.PORTFOLIO_BRIEFING,
        7,
        make_payload(),
        "system prompt",
        ExampleSchema,
        "v1",
        on_date=date(2026, 7, 5),
    )

    assert first != second
