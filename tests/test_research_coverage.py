from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.adapters.market.base import PriceBarResult
from app.domains.assets.model import Asset
from app.domains.earnings.model import EarningsReport
from app.domains.news.model import NewsItem
from app.domains.prices.model import StockPriceBar
from app.domains.prices.repository import PriceBarRepository
from app.domains.valuation.model import ValuationSnapshot
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user


def create_asset(*, symbol: str = "AAPL", market: str = "NASDAQ") -> int:
    with TestingSessionLocal() as db:
        asset = Asset(symbol=symbol, name=f"{symbol} Inc.", market=market)
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset.id


def create_collected_data(
    asset_id: int,
) -> tuple[datetime, datetime, datetime, datetime]:
    news_updated_at = datetime(2026, 7, 10, 9, 30, tzinfo=UTC)
    price_updated_at = datetime(2026, 7, 10, 10, 45, tzinfo=UTC)
    valuation_updated_at = datetime(2026, 7, 10, 11, 15, tzinfo=UTC)
    earnings_updated_at = datetime(2026, 7, 10, 11, 45, tzinfo=UTC)
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
                    updated_at=news_updated_at - timedelta(hours=1 - index),
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
                    updated_at=price_updated_at - timedelta(hours=2 - index),
                )
                for index in range(3)
            ]
        )
        db.add(
            ValuationSnapshot(
                symbol=asset.symbol,
                market=asset.market,
                as_of=datetime(2026, 7, 10, tzinfo=UTC).date(),
                per=Decimal("18.3"),
                forward_per=Decimal("16.9"),
                psr=Decimal("2.4"),
                pbr=Decimal("3.1"),
                ev_ebitda=Decimal("11.7"),
                peg=Decimal("1.2"),
                fcf_yield=Decimal("5.4"),
                source="test",
                updated_at=valuation_updated_at,
            )
        )
        db.add(
            EarningsReport(
                symbol=asset.symbol,
                market=asset.market,
                period="2026Q1",
                period_end=datetime(2026, 3, 31, tzinfo=UTC).date(),
                # Source: docs/designs/280-earnings-real-collection.md fixture.
                revenue=Decimal("100"),
                operating_income=Decimal("25"),
                eps=Decimal("1.2"),
                eps_estimate=Decimal("1.1"),
                source="test",
                updated_at=earnings_updated_at,
            )
        )
        db.commit()
    return (
        news_updated_at,
        price_updated_at,
        earnings_updated_at,
        valuation_updated_at,
    )


def test_get_research_coverage_derives_collected_axes(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset()
    news_updated_at, price_updated_at, earnings_updated_at, valuation_updated_at = (
        create_collected_data(asset_id)
    )

    response = client.get(f"/api/v1/assets/{asset_id}/research-coverage")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["asset_id"] == asset_id
    assert data["axes"] == [
        {
            "axis": "NEWS",
            "status": "COLLECTED",
            "last_updated_at": news_updated_at.isoformat().replace("+00:00", "Z"),
            "item_count": 2,
        },
        {
            "axis": "PRICE",
            "status": "COLLECTED",
            "last_updated_at": price_updated_at.isoformat().replace("+00:00", "Z"),
            "item_count": 3,
        },
        {
            "axis": "EARNINGS",
            "status": "COLLECTED",
            "last_updated_at": earnings_updated_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "item_count": 1,
        },
        {
            "axis": "VALUATION",
            "status": "COLLECTED",
            "last_updated_at": valuation_updated_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "item_count": 1,
        },
        {
            "axis": "DISCLOSURE",
            "status": "NOT_COLLECTED",
            "last_updated_at": None,
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
        and axis["last_updated_at"] is None
        and axis["item_count"] == 0
        for axis in data["axes"]
    )


def test_get_research_coverage_reflects_price_upsert_updated_at(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset()
    _, initial_updated_at, _, _ = create_collected_data(asset_id)

    with TestingSessionLocal() as db:
        bar = db.scalars(
            select(StockPriceBar).where(
                StockPriceBar.symbol == "AAPL",
                StockPriceBar.market == "NASDAQ",
                StockPriceBar.interval == "1d",
                StockPriceBar.timestamp == datetime(2026, 7, 10, tzinfo=UTC),
            )
        ).one()
        PriceBarRepository(db).upsert_many(
            [
                PriceBarResult(
                    symbol=bar.symbol,
                    market=bar.market,
                    interval=bar.interval,
                    timestamp=bar.timestamp,
                    open_price=bar.open_price,
                    high_price=bar.high_price,
                    low_price=bar.low_price,
                    close_price=Decimal("102"),
                    adjusted_close_price=Decimal("102"),
                    volume=bar.volume,
                    currency=bar.currency,
                    source=bar.source,
                )
            ]
        )
        db.refresh(bar)
        upsert_updated_at = bar.updated_at.replace(tzinfo=UTC)

    response = client.get(f"/api/v1/assets/{asset_id}/research-coverage")

    assert response.status_code == 200
    assert upsert_updated_at > initial_updated_at
    data = cast(dict[str, Any], api_data(response))
    price_axis = next(axis for axis in data["axes"] if axis["axis"] == "PRICE")
    assert price_axis["last_updated_at"] == upsert_updated_at.isoformat().replace(
        "+00:00", "Z"
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
