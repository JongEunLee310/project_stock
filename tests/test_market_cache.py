from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Callable

import pytest

from app.adapters.market import cache as cache_module
from app.adapters.market.base import (
    ExchangeRateProvider,
    ExchangeRateResult,
    IndexQuoteProvider,
    IndexQuoteResult,
    MarketDataProvider,
    PriceTargetResult,
    QuoteResult,
)
from app.adapters.market.cache import (
    CachedExchangeRateProvider,
    CachedIndexQuoteProvider,
    CachedMarketDataProvider,
    fetch_json_cached,
)

# All numeric market values in this module are synthetic fixtures.


class StubRedis:
    def __init__(self) -> None:
        self.values: dict[str, str | bytes] = {}
        self.setex_calls: list[tuple[str, int, str]] = []

    def get(self, key: str) -> str | bytes | None:
        return self.values.get(key)

    def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        self.values[key] = value
        self.setex_calls.append((key, ttl_seconds, value))
        return True


class RaisingRedis:
    def get(self, key: str) -> str | bytes | None:
        raise RuntimeError("redis unavailable")

    def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        raise RuntimeError("redis unavailable")


class WriteRaisingRedis(StubRedis):
    def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        raise RuntimeError("redis unavailable")


def install_redis(monkeypatch: pytest.MonkeyPatch, redis: Any) -> None:
    monkeypatch.setattr(cache_module, "get_redis_connection", lambda: redis)


def test_fetch_json_cached_miss_then_hit_and_passes_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = StubRedis()
    install_redis(monkeypatch, redis)
    calls = 0

    def loader() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"value": 7}

    first = fetch_json_cached("market:test", 123, loader)
    second = fetch_json_cached("market:test", 123, loader)

    assert first == {"value": 7}
    assert second == first
    assert calls == 1
    assert redis.setex_calls[0][0:2] == ("market:test", 123)


def test_fetch_json_cached_falls_back_when_redis_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_redis(monkeypatch, RaisingRedis())

    assert fetch_json_cached("market:test", 60, lambda: {"live": True}) == {
        "live": True
    }


def test_fetch_json_cached_returns_loaded_value_when_cache_write_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_redis(monkeypatch, WriteRaisingRedis())
    calls = 0

    def loader() -> dict[str, bool]:
        nonlocal calls
        calls += 1
        return {"live": True}

    assert fetch_json_cached("market:test", 60, loader) == {"live": True}
    assert calls == 1


class StubMarketProvider(MarketDataProvider):
    def __init__(self, as_of: datetime) -> None:
        self.as_of = as_of
        self.calls = 0
        self.price_target_calls = 0

    def get_quote(self, symbols: list[str]) -> list[QuoteResult]:
        self.calls += 1
        return [
            QuoteResult(
                symbol=symbol,
                name=symbol,
                price=Decimal("195.64"),
                previous_close=Decimal("193.20"),
                change=Decimal("2.44"),
                change_percent=Decimal("1.26"),
                currency="USD",
                as_of=self.as_of,
                market_cap=Decimal("3000000000000"),
            )
            for symbol in symbols
        ]

    def get_price_targets(self, symbols: list[str]) -> list[PriceTargetResult]:
        self.price_target_calls += 1
        return [
            PriceTargetResult(
                symbol=symbol,
                target_price=Decimal("220.00"),
                target_price_high=Decimal("250.00"),
                target_price_low=Decimal("180.00"),
                target_analyst_count=42,
            )
            for symbol in symbols
        ]


def test_cached_market_provider_round_trips_decimal_and_datetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = StubRedis()
    install_redis(monkeypatch, redis)
    as_of = datetime(2026, 7, 13, 3, 4, 5, tzinfo=UTC)
    inner = StubMarketProvider(as_of)
    provider = CachedMarketDataProvider(inner)

    live = provider.get_quote(["MSFT", "AAPL"])
    cached = provider.get_quote(["MSFT", "AAPL"])

    assert cached == live
    assert isinstance(cached[0].price, Decimal)
    assert isinstance(cached[0].as_of, datetime)
    assert inner.calls == 1
    assert redis.setex_calls[0][0] == "market:quote:AAPL,MSFT"
    assert redis.setex_calls[0][1] == cache_module.QUOTE_CACHE_TTL_SECONDS


def test_cached_market_provider_uses_one_hour_price_target_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = StubRedis()
    install_redis(monkeypatch, redis)
    inner = StubMarketProvider(datetime(2026, 7, 13, tzinfo=UTC))
    provider = CachedMarketDataProvider(inner)

    live = provider.get_price_targets(["MSFT", "AAPL"])
    cached = provider.get_price_targets(["MSFT", "AAPL"])

    assert cached == live
    assert isinstance(cached[0].target_price, Decimal)
    assert inner.price_target_calls == 1
    assert redis.setex_calls[0][0] == "market:price-target:AAPL,MSFT"
    assert redis.setex_calls[0][1] == cache_module.PRICE_TARGET_CACHE_TTL_SECONDS


class StubIndexProvider(IndexQuoteProvider):
    def get_quotes(self, symbols: list[str]) -> list[IndexQuoteResult]:
        return [
            IndexQuoteResult(
                symbol=symbol,
                name=symbol,
                value=Decimal("5600.00"),
                change_percent=Decimal("0.50"),
                reference_at=datetime(2026, 7, 13, tzinfo=UTC),
            )
            for symbol in symbols
        ]


class StubExchangeRateProvider(ExchangeRateProvider):
    def get_rates(self, pairs: list[str]) -> list[ExchangeRateResult]:
        return [
            ExchangeRateResult(
                pair=pair,
                rate=Decimal("1384.50"),
                change_percent=Decimal("0.18"),
                as_of=datetime(2026, 7, 13, tzinfo=UTC),
            )
            for pair in pairs
        ]


@pytest.mark.parametrize(
    ("provider_factory", "method_name", "values", "expected_key", "expected_ttl"),
    [
        (
            lambda: CachedIndexQuoteProvider(StubIndexProvider()),
            "get_quotes",
            ["VIX", "SPX"],
            "market:index:SPX,VIX",
            cache_module.INDEX_CACHE_TTL_SECONDS,
        ),
        (
            lambda: CachedExchangeRateProvider(StubExchangeRateProvider()),
            "get_rates",
            ["USD/KRW"],
            "market:fx:USD/KRW",
            cache_module.FX_CACHE_TTL_SECONDS,
        ),
    ],
)
def test_index_and_fx_cache_wrappers_use_expected_keys_and_ttls(
    monkeypatch: pytest.MonkeyPatch,
    provider_factory: Callable[[], object],
    method_name: str,
    values: list[str],
    expected_key: str,
    expected_ttl: int,
) -> None:
    redis = StubRedis()
    install_redis(monkeypatch, redis)
    provider = provider_factory()

    result = getattr(provider, method_name)(values)

    assert result
    assert redis.setex_calls[0][0:2] == (expected_key, expected_ttl)
