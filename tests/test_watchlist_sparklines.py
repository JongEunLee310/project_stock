from datetime import datetime, timezone
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
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


def test_get_watchlist_sparklines_accepts_1d_intraday_range(
    client: TestClient,
) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    asset = create_asset(client, "AAPL")
    add_item(client, watchlist["id"], asset["id"])

    # range contract: app/api/v1/endpoints/watchlists.py Literal.
    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/sparklines",
        params={"range": "1D"},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    bars = data["items"][0]["bars"]
    assert len(bars) == 78
    assert "T" in bars[0]["date"]


def test_get_watchlist_sparklines_rejects_unsupported_range(
    client: TestClient,
) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)

    # range contract: app/api/v1/endpoints/watchlists.py Literal.
    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/sparklines",
        params={"range": "2D"},
    )

    assert response.status_code == 422


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


def test_watchlist_sparkline_service_derives_intraday_interval(db: Session) -> None:
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
            interval: str | None = None,
            adjusted: bool = True,
        ) -> PriceSeriesResponse:
            # range contract: app/api/v1/endpoints/watchlists.py Literal.
            assert range_value == "1D"
            # interval contract: app/domains/prices/service.py _RANGE_INTERVALS.
            assert interval == "5m"
            return PriceSeriesResponse(
                symbol=symbol,
                market=market,
                currency="USD",
                interval=interval,
                range=range_value,
                source="test",
                last_updated_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
                bars=[],
            )

    service = WatchlistSparklineService(db)
    cast(Any, service).price_series_service = FakePriceSeriesService()

    result = service.get_sparklines(watchlist.id, user_id=1, range_value="1D")

    assert result.items[0].bars == []


def test_watchlist_sparkline_service_skips_price_series_not_found_404(
    db: Session,
) -> None:
    aapl = AssetRepository(db).create(
        symbol="AAPL",
        name="Apple Inc.",
        market="NASDAQ",
        sector="Technology",
        industry=None,
        description=None,
    )
    msft = AssetRepository(db).create(
        symbol="MSFT",
        name="Microsoft Inc.",
        market="NASDAQ",
        sector="Technology",
        industry=None,
        description=None,
    )
    watchlist = WatchlistRepository(db).create(user_id=1, name="Core")
    item_repo = WatchlistItemRepository(db)
    item_repo.create(watchlist.id, aapl.id, priority=0, reason=None, tags=[], memo=None)
    item_repo.create(watchlist.id, msft.id, priority=1, reason=None, tags=[], memo=None)

    class FakePriceSeriesService:
        def get_series(
            self,
            symbol: str,
            market: str,
            range_value: str = "3M",
            interval: str = "1d",
            adjusted: bool = True,
        ) -> PriceSeriesResponse:
            if symbol == "MSFT":
                # ErrorCode is sourced from app/core/error_codes.py.
                raise AppException(
                    status_code=404,
                    detail="No price series.",
                    error_code=ErrorCode.PRICE_SERIES_NOT_FOUND,
                )
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

    assert [item.symbol for item in result.items] == ["AAPL"]


def test_watchlist_sparkline_service_reraises_non_price_series_not_found_404(
    db: Session,
) -> None:
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
        watchlist.id,
        asset.id,
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
            raise AppException(
                status_code=404,
                detail="Asset missing.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )

    service = WatchlistSparklineService(db)
    cast(Any, service).price_series_service = FakePriceSeriesService()

    with pytest.raises(AppException) as exc_info:
        service.get_sparklines(watchlist.id, user_id=1, range_value="1M")

    assert exc_info.value.error_code == ErrorCode.ASSET_NOT_FOUND
