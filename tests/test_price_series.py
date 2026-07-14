from datetime import date, datetime, time, timezone
from decimal import Decimal
import re
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.market.base import PriceBarResult
from app.adapters.market.mock import MockPriceSeriesProvider
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.prices.model import StockPriceBar
from app.domains.prices.repository import PriceBarRepository
from app.domains.prices.service import PriceSeriesService
from tests.conftest import api_data, api_error

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def test_get_price_series_returns_contract_shape(client: TestClient) -> None:
    response = client.get(
        "/api/v1/stocks/005930/prices",
        params={"market": "KOSPI", "range": "1M"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] is None
    data = cast(dict[str, Any], api_data(response))
    assert data["symbol"] == "005930"
    assert data["market"] == "KOSPI"
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


def test_price_series_derives_intraday_interval_for_1d(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/stocks/NVDA/prices",
        params={"market": "NASDAQ", "range": "1D"},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["interval"] == "15m"


def test_price_series_accepts_kosdaq_market(client: TestClient) -> None:
    response = client.get(
        "/api/v1/stocks/035720/prices",
        params={"market": "KOSDAQ", "range": "1M"},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["market"] == "KOSDAQ"
    assert data["currency"] == "KRW"


def test_price_series_rejects_krx_market(client: TestClient) -> None:
    response = client.get(
        "/api/v1/stocks/005930/prices",
        params={"market": "KRX", "range": "1M"},
    )

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"


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


def test_price_series_service_uses_intraday_provider_for_1d(
    db: Session,
    monkeypatch: Any,
) -> None:
    provider = MockPriceSeriesProvider()
    calls: list[tuple[str, str]] = []
    original = provider.get_intraday_bars

    def get_intraday_bars(symbol: str, market: str) -> list[PriceBarResult]:
        calls.append((symbol, market))
        return original(symbol, market)

    monkeypatch.setattr(provider, "get_intraday_bars", get_intraday_bars)
    monkeypatch.setattr(
        "app.domains.prices.service.get_price_series_provider",
        lambda: provider,
    )

    # range contract: app/api/v1/endpoints/watchlists.py Literal.
    result = PriceSeriesService(db).get_series("aapl", "nasdaq", range_value="1D")

    assert calls == [("AAPL", "NASDAQ")]
    # interval contract: app/domains/prices/service.py _RANGE_INTERVALS.
    assert result.interval == "15m"
    assert len(result.bars) <= 26
    assert all(DATETIME_PATTERN.match(bar.date) for bar in result.bars)


def test_price_series_service_validates_range_and_derived_interval(
    db: Session,
) -> None:
    service = PriceSeriesService(db)

    # range contract: app/api/v1/endpoints/watchlists.py Literal.
    service._validate_range("1D")
    with pytest.raises(AppException) as range_error:
        service._validate_range("2D")
    assert range_error.value.status_code == 400
    assert range_error.value.error_code == ErrorCode.INVALID_PRICE_RANGE

    # interval contract: app/domains/prices/service.py _RANGE_INTERVALS.
    with pytest.raises(AppException) as interval_error:
        service._validate_interval("1d", "15m")
    assert interval_error.value.status_code == 400
    assert interval_error.value.error_code == ErrorCode.INVALID_PRICE_INTERVAL


def test_price_series_service_formats_bar_date_by_interval(db: Session) -> None:
    timestamp = datetime(2026, 6, 25, 13, 30, tzinfo=timezone.utc)
    bar = StockPriceBar(
        symbol="AAPL",
        market="NASDAQ",
        interval="15m",
        timestamp=timestamp,
        open_price=Decimal("100"),
        high_price=Decimal("101"),
        low_price=Decimal("99"),
        close_price=Decimal("100.5"),
        adjusted_close_price=Decimal("100.5"),
        volume=100,
        currency="USD",
        source="test",
    )
    service = PriceSeriesService(db)

    # interval contract: app/domains/prices/service.py _RANGE_INTERVALS.
    assert service._to_bar(bar, "15m").date == timestamp.isoformat()
    assert service._to_bar(bar, "1d").date == "2026-06-25"
