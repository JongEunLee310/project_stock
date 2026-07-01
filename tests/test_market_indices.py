from datetime import timezone
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.adapters.market.base import IndexQuoteResult
from app.adapters.market.mock import MARKET_INDEX_SYMBOLS, MockIndexQuoteProvider
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.market.index_service import MarketIndexService
from app.domains.market.schema import MarketIndexQuoteResponse
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
