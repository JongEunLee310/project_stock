from datetime import date, datetime, time, timezone
from decimal import Decimal
import re
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.market.base import PriceBarResult
from app.adapters.market.mock import MockPriceSeriesProvider
from app.domains.prices.model import StockPriceBar
from app.domains.prices.repository import PriceBarRepository
from tests.conftest import api_data, api_error

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def test_get_price_series_returns_contract_shape(client: TestClient) -> None:
    response = client.get(
        "/api/v1/stocks/005930/prices",
        params={"market": "KRX", "range": "1M"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] is None
    data = cast(dict[str, Any], api_data(response))
    assert data["symbol"] == "005930"
    assert data["market"] == "KRX"
    assert data["currency"] == "KRW"
    assert data["interval"] == "1d"
    assert data["range"] == "1M"
    assert data["source"] == "mock"
    assert data["last_updated_at"].endswith("Z")
    assert "lastUpdatedAt" not in data

    bars = data["bars"]
    assert len(bars) == 22
    assert bars == sorted(bars, key=lambda bar: bar["date"])
    first_bar = bars[0]
    assert set(first_bar) == {
        "date",
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
    }
    assert "adjustedClose" not in first_bar
    assert DATE_PATTERN.match(first_bar["date"])
    for field in ("open", "high", "low", "close", "adjusted_close"):
        assert isinstance(first_bar[field], str)
        Decimal(first_bar[field])
    assert isinstance(first_bar["volume"], int)


def test_price_series_adjusted_false_uses_close_as_adjusted_close(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/stocks/AAPL/prices",
        params={"market": "NASDAQ", "range": "1M", "adjusted": False},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    for bar in data["bars"]:
        assert bar["adjusted_close"] == bar["close"]


def test_price_series_rejects_invalid_range(client: TestClient) -> None:
    response = client.get(
        "/api/v1/stocks/AAPL/prices",
        params={"market": "NASDAQ", "range": "5Y"},
    )

    assert response.status_code == 400
    assert api_error(response) == {
        "code": "INVALID_PRICE_RANGE",
        "message": "지원하지 않는 가격 범위입니다.",
    }


def test_price_series_rejects_invalid_interval(client: TestClient) -> None:
    response = client.get(
        "/api/v1/stocks/AAPL/prices",
        params={"market": "NASDAQ", "interval": "1h"},
    )

    assert response.status_code == 400
    assert api_error(response) == {
        "code": "INVALID_PRICE_INTERVAL",
        "message": "지원하지 않는 가격 간격입니다.",
    }


def test_price_series_requires_market(client: TestClient) -> None:
    response = client.get("/api/v1/stocks/AAPL/prices")

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"


def test_price_series_rejects_invalid_market(client: TestClient) -> None:
    response = client.get(
        "/api/v1/stocks/AAPL/prices",
        params={"market": "LSE"},
    )

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"


def test_price_series_returns_404_when_provider_has_no_bars(
    client: TestClient,
    monkeypatch: Any,
) -> None:
    class EmptyProvider:
        def get_daily_bars(
            self,
            symbol: str,
            market: str,
            range_value: str,
            adjusted: bool,
        ) -> list[PriceBarResult]:
            return []

    monkeypatch.setattr(
        "app.domains.prices.service.get_price_series_provider",
        lambda: EmptyProvider(),
    )

    response = client.get(
        "/api/v1/stocks/EMPTY/prices",
        params={"market": "NASDAQ"},
    )

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "PRICE_SERIES_NOT_FOUND",
        "message": "가격 시계열을 찾을 수 없습니다.",
    }


def test_price_series_maps_provider_error_to_502(
    client: TestClient,
    monkeypatch: Any,
) -> None:
    class FailingProvider:
        def get_daily_bars(
            self,
            symbol: str,
            market: str,
            range_value: str,
            adjusted: bool,
        ) -> list[PriceBarResult]:
            raise RuntimeError("provider failed")

    monkeypatch.setattr(
        "app.domains.prices.service.get_price_series_provider",
        lambda: FailingProvider(),
    )

    response = client.get(
        "/api/v1/stocks/AAPL/prices",
        params={"market": "NASDAQ"},
    )

    assert response.status_code == 502
    assert api_error(response) == {
        "code": "MARKET_DATA_PROVIDER_ERROR",
        "message": "시세 제공자에서 가격 데이터를 가져오지 못했습니다.",
    }


def test_price_series_date_matches_mock_utc_trading_dates(
    client: TestClient,
) -> None:
    provider = MockPriceSeriesProvider()
    expected_dates = [
        bar.timestamp.date().isoformat()
        for bar in provider.get_daily_bars("AAPL", "NASDAQ", "1M", adjusted=True)
    ]

    response = client.get(
        "/api/v1/stocks/AAPL/prices",
        params={"market": "NASDAQ", "range": "1M"},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert [bar["date"] for bar in data["bars"]] == expected_dates


def test_price_bar_repository_upsert_is_idempotent(db: Session) -> None:
    repository = PriceBarRepository(db)
    timestamp = datetime.combine(date(2026, 6, 25), time.min, tzinfo=timezone.utc)
    bars = [
        PriceBarResult(
            symbol="AAPL",
            market="NASDAQ",
            interval="1d",
            timestamp=timestamp,
            open_price=Decimal("100.00"),
            high_price=Decimal("110.00"),
            low_price=Decimal("95.00"),
            close_price=Decimal("105.00"),
            adjusted_close_price=Decimal("104.50"),
            volume=123456,
            currency="USD",
            source="mock",
        )
    ]

    repository.upsert_many(bars)
    repository.upsert_many(bars)

    count = db.scalar(select(func.count()).select_from(StockPriceBar))
    assert count == 1
