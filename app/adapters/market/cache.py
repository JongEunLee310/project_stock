from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
import json
import logging
from typing import Any, cast

from app.adapters.market.base import (
    ExchangeRateProvider,
    ExchangeRateResult,
    IndexQuoteProvider,
    IndexQuoteResult,
    MarketDataProvider,
    QuoteResult,
)
from app.worker.connection import get_redis_connection

logger = logging.getLogger(__name__)

QUOTE_CACHE_TTL_SECONDS = 60
INDEX_CACHE_TTL_SECONDS = 60
FX_CACHE_TTL_SECONDS = 300
_TYPE_KEY = "__market_cache_type__"


def fetch_json_cached(
    key: str,
    ttl_seconds: int,
    loader: Callable[[], Any],
) -> Any:
    try:
        redis = get_redis_connection()
        cached = redis.get(key)
        if cached is not None:
            raw = cached.decode("utf-8") if isinstance(cached, bytes) else cached
            return _decode_json(json.loads(raw))
    except Exception:
        # Market data must remain available when Redis is unavailable or corrupt.
        logger.exception(
            "Market cache read failed; loading from provider",
            extra={"key": key},
        )
        return loader()

    value = loader()
    try:
        redis.setex(
            key,
            ttl_seconds,
            json.dumps(_encode_json(value), separators=(",", ":")),
        )
    except Exception:
        # A cache write failure must not discard successfully loaded market data.
        logger.exception("Market cache write failed", extra={"key": key})
    return value


class CachedMarketDataProvider(MarketDataProvider):
    def __init__(self, provider: MarketDataProvider) -> None:
        self.provider = provider

    def get_quote(self, symbols: list[str]) -> list[QuoteResult]:
        key = _cache_key("quote", symbols)
        payload = fetch_json_cached(
            key,
            QUOTE_CACHE_TTL_SECONDS,
            lambda: _dataclasses_to_dicts(self.provider.get_quote(symbols)),
        )
        return _quote_results_from_dicts(payload)


class CachedIndexQuoteProvider(IndexQuoteProvider):
    def __init__(self, provider: IndexQuoteProvider) -> None:
        self.provider = provider

    def get_quotes(self, symbols: list[str]) -> list[IndexQuoteResult]:
        key = _cache_key("index", symbols)
        payload = fetch_json_cached(
            key,
            INDEX_CACHE_TTL_SECONDS,
            lambda: _dataclasses_to_dicts(self.provider.get_quotes(symbols)),
        )
        return _index_results_from_dicts(payload)


class CachedExchangeRateProvider(ExchangeRateProvider):
    def __init__(self, provider: ExchangeRateProvider) -> None:
        self.provider = provider

    def get_rates(self, pairs: list[str]) -> list[ExchangeRateResult]:
        key = _cache_key("fx", pairs)
        payload = fetch_json_cached(
            key,
            FX_CACHE_TTL_SECONDS,
            lambda: _dataclasses_to_dicts(self.provider.get_rates(pairs)),
        )
        return _exchange_rate_results_from_dicts(payload)


def _cache_key(kind: str, values: list[str]) -> str:
    normalized_values = sorted(value.upper() for value in values)
    return f"market:{kind}:{','.join(normalized_values)}"


def _dataclasses_to_dicts(items: list[Any]) -> list[dict[str, Any]]:
    return [asdict(item) for item in items]


def _quote_results_from_dicts(payload: Any) -> list[QuoteResult]:
    return [QuoteResult(**cast(dict[str, Any], item)) for item in payload]


def _index_results_from_dicts(payload: Any) -> list[IndexQuoteResult]:
    return [IndexQuoteResult(**cast(dict[str, Any], item)) for item in payload]


def _exchange_rate_results_from_dicts(payload: Any) -> list[ExchangeRateResult]:
    return [ExchangeRateResult(**cast(dict[str, Any], item)) for item in payload]


def _encode_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {_TYPE_KEY: "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {_TYPE_KEY: "datetime", "value": value.isoformat()}
    if isinstance(value, dict):
        return {key: _encode_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode_json(item) for item in value]
    return value


def _decode_json(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode_json(item) for item in value]
    if not isinstance(value, dict):
        return value
    value_type = value.get(_TYPE_KEY)
    if value_type == "decimal":
        return Decimal(value["value"])
    if value_type == "datetime":
        return datetime.fromisoformat(value["value"])
    return {key: _decode_json(item) for key, item in value.items()}
