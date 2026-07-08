from datetime import datetime, timezone
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.assets.repository import AssetRepository
from app.domains.prices.schema import PriceBar, PriceSeriesResponse
from app.domains.watchlists.repository import (
    WatchlistItemRepository,
    WatchlistRepository,
)
from app.domains.watchlists.sparkline_service import WatchlistSparklineService
from tests.conftest import api_data, set_current_user


def create_asset(client: TestClient, symbol: str = "AAPL") -> dict[str, Any]:
    response = client.post(
        "/api/v1/assets",
        json={"symbol": symbol, "name": f"{symbol} Inc.", "market": "NASDAQ"},
    )
    assert response.status_code == 201
    body = response.json()
    return cast(dict[str, Any], body["data"])


def create_watchlist(client: TestClient, name: str = "Core") -> dict[str, Any]:
    response = client.post("/api/v1/watchlists", json={"name": name})
    assert response.status_code == 201
    body = response.json()
    return cast(dict[str, Any], body["data"])


def add_item(client: TestClient, watchlist_id: int, asset_id: int) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/watchlists/{watchlist_id}/items",
        json={"asset_id": asset_id, "priority": 0},
    )
    assert response.status_code == 201
    body = response.json()
    return cast(dict[str, Any], body["data"])


def test_get_watchlist_sparklines_defaults_to_1m(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    asset = create_asset(client, "AAPL")
    add_item(client, watchlist["id"], asset["id"])

    response = client.get(f"/api/v1/watchlists/{watchlist['id']}/sparklines")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert len(data["items"]) == 1
    assert data["items"][0]["symbol"] == "AAPL"
    bars = data["items"][0]["bars"]
    assert len(bars) == 22
    assert set(bars[0]) == {"date", "close"}
    assert isinstance(bars[0]["close"], str)


def test_get_watchlist_sparklines_accepts_explicit_3m_range(
    client: TestClient,
) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    asset = create_asset(client, "AAPL")
    add_item(client, watchlist["id"], asset["id"])

    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/sparklines",
        params={"range": "3M"},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert len(data["items"][0]["bars"]) == 66


def test_get_watchlist_sparklines_returns_empty_items_for_empty_watchlist(
    client: TestClient,
) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)

    response = client.get(f"/api/v1/watchlists/{watchlist['id']}/sparklines")

    assert response.status_code == 200
    assert api_data(response) == {"items": []}


def test_watchlist_sparkline_service_extracts_daily_close_bars(db: Session) -> None:
    asset = AssetRepository(db).create(
        symbol="AAPL",
        name="Apple Inc.",
        market="NASDAQ",
        sector="Technology",
        industry=None,
        description=None,
    )
    watchlist = WatchlistRepository(db).create(user_id=1, name="Core")
    WatchlistItemRepository(db).create(
        watchlist_id=watchlist.id,
        asset_id=asset.id,
        priority=0,
        reason=None,
        tags=[],
        memo=None,
    )

    class FakePriceSeriesService:
        def get_series(
            self,
            symbol: str,
            market: str,
            range_value: str = "3M",
            interval: str = "1d",
            adjusted: bool = True,
        ) -> PriceSeriesResponse:
            assert symbol == "AAPL"
            assert market == "NASDAQ"
            assert range_value == "1M"
            assert interval == "1d"
            assert adjusted is True
            return PriceSeriesResponse(
                symbol=symbol,
                market=market,
                currency="USD",
                interval=interval,
                range=range_value,
                source="test",
                last_updated_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
                bars=[
                    PriceBar(
                        date="2026-06-24",
                        open="100",
                        high="102",
                        low="99",
                        close="101.5",
                        adjusted_close="101.4",
                        volume=1000,
                    ),
                    PriceBar(
                        date="2026-06-25",
                        open="101.5",
                        high="103",
                        low="101",
                        close="102",
                        adjusted_close="101.9",
                        volume=1100,
                    ),
                ],
            )

    service = WatchlistSparklineService(db)
    cast(Any, service).price_series_service = FakePriceSeriesService()

    result = service.get_sparklines(watchlist.id, user_id=1, range_value="1M")

    assert result.model_dump() == {
        "items": [
            {
                "symbol": "AAPL",
                "bars": [
                    {"date": "2026-06-24", "close": "101.5"},
                    {"date": "2026-06-25", "close": "102"},
                ],
            }
        ]
    }
