from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from fastapi.testclient import TestClient

from app.domains.assets.model import Asset
from app.domains.news.model import NewsItem
from app.domains.prices.model import StockPriceBar
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user


def create_asset(*, symbol: str = "AAPL", market: str = "NASDAQ") -> int:
    with TestingSessionLocal() as db:
        asset = Asset(symbol=symbol, name=f"{symbol} Inc.", market=market)
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset.id


def create_collected_data(asset_id: int) -> tuple[datetime, datetime]:
    news_collected_at = datetime(2026, 7, 10, 9, 30, tzinfo=UTC)
    price_collected_at = datetime(2026, 7, 10, 10, 45, tzinfo=UTC)
    with TestingSessionLocal() as db:
        asset = db.get(Asset, asset_id)
        assert asset is not None
        db.add_all(
            [
                NewsItem(
                    asset_id=asset.id,
                    title=f"뉴스 {index}",
                    url=f"https://example.com/news/{index}",
                    source="test",
                    created_at=news_collected_at - timedelta(hours=1 - index),
                )
                for index in range(2)
            ]
        )
        db.add_all(
            [
                StockPriceBar(
                    symbol=asset.symbol,
                    market=asset.market,
                    interval="1d",
                    timestamp=datetime(2026, 7, 8 + index, tzinfo=UTC),
                    open_price=Decimal("100"),
                    high_price=Decimal("101"),
                    low_price=Decimal("99"),
                    close_price=Decimal("100"),
                    adjusted_close_price=Decimal("100"),
                    volume=1000,
                    currency="USD",
                    source="test",
                    created_at=price_collected_at - timedelta(hours=2 - index),
                )
                for index in range(3)
            ]
        )
        db.commit()
    return news_collected_at, price_collected_at


def test_get_research_coverage_derives_collected_axes(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset()
    news_collected_at, price_collected_at = create_collected_data(asset_id)

    response = client.get(f"/api/v1/assets/{asset_id}/research-coverage")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["asset_id"] == asset_id
    assert data["axes"] == [
        {
            "axis": "NEWS",
            "status": "COLLECTED",
            "last_collected_at": news_collected_at.isoformat().replace("+00:00", "Z"),
            "item_count": 2,
        },
        {
            "axis": "PRICE",
            "status": "COLLECTED",
            "last_collected_at": price_collected_at.isoformat().replace("+00:00", "Z"),
            "item_count": 3,
        },
        {
            "axis": "EARNINGS",
            "status": "NOT_COLLECTED",
            "last_collected_at": None,
            "item_count": 0,
        },
        {
            "axis": "VALUATION",
            "status": "NOT_COLLECTED",
            "last_collected_at": None,
            "item_count": 0,
        },
        {
            "axis": "DISCLOSURE",
            "status": "NOT_COLLECTED",
            "last_collected_at": None,
            "item_count": 0,
        },
    ]


def test_get_research_coverage_returns_all_axes_not_collected_without_data(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset()

    response = client.get(f"/api/v1/assets/{asset_id}/research-coverage")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert [axis["axis"] for axis in data["axes"]] == [
        "NEWS",
        "PRICE",
        "EARNINGS",
        "VALUATION",
        "DISCLOSURE",
    ]
    assert all(
        axis["status"] == "NOT_COLLECTED"
        and axis["last_collected_at"] is None
        and axis["item_count"] == 0
        for axis in data["axes"]
    )


def test_get_research_coverage_returns_404_for_missing_asset(
    client: TestClient,
) -> None:
    set_current_user(1)
    existing_asset_id = create_asset()

    response = client.get(
        f"/api/v1/assets/{existing_asset_id + 1}/research-coverage"
    )

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }


def test_get_research_coverage_requires_authentication(client: TestClient) -> None:
    asset_id = create_asset()

    response = client.get(f"/api/v1/assets/{asset_id}/research-coverage")

    assert response.status_code == 401
