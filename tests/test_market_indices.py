from datetime import timezone
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.adapters.market.base import ExchangeRateResult, IndexQuoteResult
from app.adapters.market.mock import (
    MARKET_INDEX_SYMBOLS,
    MockExchangeRateProvider,
    MockIndexQuoteProvider,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.market.fx_service import (
    DEFAULT_FX_PAIR,
    ExchangeRateService,
    parse_fx_pairs,
)
from app.domains.market.index_service import MarketIndexService
from app.domains.market.schema import ExchangeRateResponse, MarketIndexQuoteResponse
from tests.conftest import api_data, api_error


def test_mock_index_quote_provider_returns_deterministic_quotes() -> None:
    provider = MockIndexQuoteProvider()

    first_result = provider.get_quotes(MARKET_INDEX_SYMBOLS)
    second_result = provider.get_quotes(MARKET_INDEX_SYMBOLS)

    assert len(first_result) == 4
    assert first_result == second_result
    assert [quote.symbol for quote in first_result] == MARKET_INDEX_SYMBOLS
    for quote in first_result:
        assert isinstance(quote.symbol, str)
        assert isinstance(quote.name, str)
        assert isinstance(quote.value, Decimal)
        assert isinstance(quote.change_percent, Decimal)
        assert quote.reference_at.tzinfo is not None
        assert quote.reference_at.utcoffset() == timezone.utc.utcoffset(None)


def test_mock_exchange_rate_provider_returns_supported_pair() -> None:
    provider = MockExchangeRateProvider()

    result = provider.get_rates(["USD/KRW"])

    assert len(result) == 1
    assert result[0].pair == "USD/KRW"
    assert result[0].rate == Decimal("1384.50")
    assert result[0].change_percent == Decimal("0.18")
    assert result[0].as_of.tzinfo is not None
    assert result[0].as_of.utcoffset() == timezone.utc.utcoffset(None)


def test_mock_exchange_rate_provider_excludes_unsupported_pairs() -> None:
    provider = MockExchangeRateProvider()

    result = provider.get_rates(["USD/KRW", "EUR/KRW"])

    assert [rate.pair for rate in result] == ["USD/KRW"]


def test_mock_exchange_rate_provider_returns_deterministic_rates() -> None:
    provider = MockExchangeRateProvider()

    first_result = provider.get_rates(["USD/KRW"])
    second_result = provider.get_rates(["USD/KRW"])

    assert first_result == second_result


def test_market_index_service_maps_provider_dataclass_to_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quote = IndexQuoteResult(
        symbol="SPX",
        name="S&P 500",
        value=Decimal("6200.12"),
        change_percent=Decimal("0.34"),
        reference_at=MockIndexQuoteProvider().get_quotes(["SPX"])[0].reference_at,
    )

    class StubProvider:
        def get_quotes(self, symbols: list[str]) -> list[IndexQuoteResult]:
            assert symbols == MARKET_INDEX_SYMBOLS
            return [quote]

    monkeypatch.setattr(
        "app.domains.market.index_service.get_index_quote_provider",
        lambda: StubProvider(),
    )

    result = MarketIndexService().get_quotes()

    assert result == [
        MarketIndexQuoteResponse(
            symbol="SPX",
            name="S&P 500",
            value=Decimal("6200.12"),
            change_percent=Decimal("0.34"),
            reference_at=quote.reference_at,
        )
    ]


def test_exchange_rate_service_maps_provider_dataclass_to_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rate = ExchangeRateResult(
        pair="USD/KRW",
        rate=Decimal("1384.50"),
        change_percent=Decimal("0.18"),
        as_of=MockExchangeRateProvider().get_rates(["USD/KRW"])[0].as_of,
    )

    class StubProvider:
        def get_rates(self, pairs: list[str]) -> list[ExchangeRateResult]:
            assert pairs == ["USD/KRW"]
            return [rate]

    monkeypatch.setattr(
        "app.domains.market.fx_service.get_exchange_rate_provider",
        lambda: StubProvider(),
    )

    result = ExchangeRateService().get_rates(["USD/KRW"])

    assert result == [
        ExchangeRateResponse(
            pair="USD/KRW",
            rate=Decimal("1384.50"),
            change_percent=Decimal("0.18"),
            reference_at=rate.as_of,
        )
    ]


def test_market_index_service_maps_provider_error_to_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingProvider:
        def get_quotes(self, symbols: list[str]) -> list[IndexQuoteResult]:
            raise RuntimeError("provider failed")

    monkeypatch.setattr(
        "app.domains.market.index_service.get_index_quote_provider",
        lambda: FailingProvider(),
    )

    with pytest.raises(AppException) as exc_info:
        MarketIndexService().get_quotes()

    assert exc_info.value.status_code == 502
    assert exc_info.value.error_code == ErrorCode.MARKET_DATA_PROVIDER_ERROR


def test_exchange_rate_service_maps_provider_error_to_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingProvider:
        def get_rates(self, pairs: list[str]) -> list[ExchangeRateResult]:
            raise RuntimeError("provider failed")

    monkeypatch.setattr(
        "app.domains.market.fx_service.get_exchange_rate_provider",
        lambda: FailingProvider(),
    )

    with pytest.raises(AppException) as exc_info:
        ExchangeRateService().get_rates(["USD/KRW"])

    assert exc_info.value.status_code == 502
    assert exc_info.value.error_code == ErrorCode.MARKET_DATA_PROVIDER_ERROR


def test_parse_fx_pairs_defaults_when_omitted_or_empty() -> None:
    assert parse_fx_pairs(None) == [DEFAULT_FX_PAIR]
    assert parse_fx_pairs(" , ") == [DEFAULT_FX_PAIR]


def test_parse_fx_pairs_trims_and_normalizes_pairs() -> None:
    assert parse_fx_pairs(" usd/krw, eur/krw ") == ["USD/KRW", "EUR/KRW"]


def test_get_market_indices_returns_public_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/market/indices")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] is None
    data = cast(list[dict[str, Any]], api_data(response))
    assert len(data) == 4
    assert [quote["symbol"] for quote in data] == MARKET_INDEX_SYMBOLS
    first_quote = data[0]
    assert set(first_quote) == {
        "symbol",
        "name",
        "value",
        "change_percent",
        "reference_at",
    }
    assert isinstance(first_quote["symbol"], str)
    assert isinstance(first_quote["name"], str)
    assert isinstance(first_quote["value"], str)
    assert isinstance(first_quote["change_percent"], str)
    assert first_quote["reference_at"].endswith("Z")


def test_get_market_fx_returns_default_pair(client: TestClient) -> None:
    response = client.get("/api/v1/market/fx")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] is None
    data = cast(list[dict[str, Any]], api_data(response))
    assert len(data) == 1
    first_rate = data[0]
    assert set(first_rate) == {
        "pair",
        "rate",
        "change_percent",
        "reference_at",
    }
    assert first_rate["pair"] == "USD/KRW"
    assert first_rate["rate"] == "1384.50"
    assert first_rate["change_percent"] == "0.18"
    assert first_rate["reference_at"].endswith("Z")


def test_get_market_fx_returns_explicit_supported_pair(client: TestClient) -> None:
    response = client.get("/api/v1/market/fx", params={"pairs": " usd/krw "})

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert [rate["pair"] for rate in data] == ["USD/KRW"]


def test_get_market_fx_returns_empty_list_for_unsupported_pairs(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/market/fx", params={"pairs": "EUR/KRW"})

    assert response.status_code == 200
    assert api_data(response) == []


def test_get_market_indices_maps_provider_error_to_502(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingProvider:
        def get_quotes(self, symbols: list[str]) -> list[IndexQuoteResult]:
            raise RuntimeError("provider failed")

    monkeypatch.setattr(
        "app.domains.market.index_service.get_index_quote_provider",
        lambda: FailingProvider(),
    )

    response = client.get("/api/v1/market/indices")

    assert response.status_code == 502
    assert api_error(response) == {
        "code": "MARKET_DATA_PROVIDER_ERROR",
        "message": "시세 제공자에서 가격 데이터를 가져오지 못했습니다.",
    }
