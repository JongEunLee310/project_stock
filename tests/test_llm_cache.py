from datetime import UTC, datetime, tzinfo
from typing import ClassVar

import pytest
from pydantic import BaseModel

from app.adapters.llm import cache as cache_module
from app.adapters.llm.cache import LLMResponseCache
from app.adapters.llm.privacy import CloudSafePayload
from app.adapters.llm.types import LLMTaskType, SensitivityLevel


class CachePayload(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.AGGREGATED

    symbol: str
    score: int


class CacheResponse(BaseModel):
    summary: str


class AlternateCacheResponse(BaseModel):
    summary: str
    confidence: int


class FakeRedisCache:
    def __init__(self) -> None:
        self.values: dict[str, str | bytes] = {}
        self.set_calls: list[tuple[str, str, int]] = []

    def get(self, name: str) -> str | bytes | None:
        return self.values.get(name)

    def set(self, name: str, value: str, ex: int) -> bool:
        self.values[name] = value
        self.set_calls.append((name, value, ex))
        return True


def make_cache() -> LLMResponseCache:
    return LLMResponseCache(FakeRedisCache(), ttl_seconds=300)


def make_payload(symbol: str = "AAPL", score: int = 7) -> CachePayload:
    return CachePayload(symbol=symbol, score=score)


def build_key(
    cache: LLMResponseCache,
    *,
    payload: CachePayload | None = None,
    system_prompt: str = "summarize",
    model_name: str = "gpt-test",
    schema: type[BaseModel] = CacheResponse,
) -> str:
    return cache.build_key(
        LLMTaskType.PORTFOLIO_BRIEFING,
        make_payload() if payload is None else payload,
        system_prompt,
        model_name,
        schema,
    )


def test_build_key_is_deterministic_for_same_inputs() -> None:
    cache = make_cache()

    first = build_key(cache)
    second = build_key(cache)

    assert first == second
    assert first.startswith("llm:cache:v1:PORTFOLIO_BRIEFING:")


def test_build_key_changes_when_cache_schema_version_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = make_cache()

    first = build_key(cache)
    monkeypatch.setattr(cache_module, "CACHE_SCHEMA_VERSION", "v2")
    second = build_key(cache)

    assert first != second
    assert second.startswith("llm:cache:v2:PORTFOLIO_BRIEFING:")


def test_build_key_preserves_digest_material_boundaries() -> None:
    cache = make_cache()

    assert build_key(cache, system_prompt="ab", model_name="c") != build_key(
        cache,
        system_prompt="a",
        model_name="bc",
    )


def test_build_key_changes_when_utc_date_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = make_cache()

    class FixedDateTime:
        current = datetime(2026, 7, 4, tzinfo=UTC)

        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return cls.current

    monkeypatch.setattr(cache_module, "datetime", FixedDateTime)
    first = build_key(cache)
    FixedDateTime.current = datetime(2026, 7, 5, tzinfo=UTC)
    second = build_key(cache)

    assert first != second


def test_build_key_changes_when_payload_changes() -> None:
    cache = make_cache()

    assert build_key(cache) != build_key(cache, payload=make_payload(score=8))


def test_build_key_changes_when_prompt_changes() -> None:
    cache = make_cache()

    assert build_key(cache) != build_key(cache, system_prompt="different")


def test_build_key_changes_when_model_changes() -> None:
    cache = make_cache()

    assert build_key(cache) != build_key(cache, model_name="gpt-other")


def test_build_key_changes_when_schema_changes() -> None:
    cache = make_cache()

    assert build_key(cache) != build_key(cache, schema=AlternateCacheResponse)


def test_store_lookup_round_trip_and_passes_ttl() -> None:
    redis = FakeRedisCache()
    cache = LLMResponseCache(redis, ttl_seconds=123)
    key = build_key(cache)

    cache.store(
        key,
        {"summary": "cached"},
        provider="openai",
        model_name="gpt-test",
    )
    cached = cache.lookup(key)

    assert cached is not None
    assert cached.output == {"summary": "cached"}
    assert cached.provider == "openai"
    assert cached.model_name == "gpt-test"
    assert redis.set_calls[0][0] == key
    assert redis.set_calls[0][2] == 123


def test_lookup_treats_missing_empty_corrupt_and_incomplete_values_as_miss() -> None:
    redis = FakeRedisCache()
    cache = LLMResponseCache(redis, ttl_seconds=300)

    assert cache.lookup("missing") is None

    bad_values: list[str | bytes] = [
        "",
        b"",
        "not-json",
        "[]",
        '{"output": {"summary": "cached"}}',
        '{"output": "wrong", "provider": "openai", "model_name": "gpt-test"}',
    ]
    for raw_value in bad_values:
        redis.values["key"] = raw_value
        assert cache.lookup("key") is None


class RaisingRedisCache:
    def get(self, name: str) -> str | bytes | None:
        raise RuntimeError("redis get failed")

    def set(self, name: str, value: str, ex: int) -> object:
        raise RuntimeError("redis set failed")


def test_redis_errors_are_treated_as_cache_misses() -> None:
    cache = LLMResponseCache(RaisingRedisCache(), ttl_seconds=300)

    assert cache.lookup("key") is None
    cache.store("key", {"summary": "live"}, "openai", "gpt-test")
