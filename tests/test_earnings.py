from datetime import date
from decimal import Decimal
from typing import Any, cast

from fastapi.testclient import TestClient

from app.domains.assets.model import Asset
from app.domains.earnings.model import EarningsReport
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user


def create_asset_and_reports() -> int:
    with TestingSessionLocal() as db:
        asset = Asset(symbol="ERN", name="Earnings", market="NASDAQ")
        db.add(asset)
        db.flush()
        # Source: docs/designs/280-earnings-real-collection.md service fixture.
        rows = [
            ("2024Q2", date(2024, 6, 30), "80", "16", "0.80", "0.75"),
            ("2024Q3", date(2024, 9, 30), "90", "18", "0.90", "0.95"),
            ("2024Q4", date(2024, 12, 31), "100", "20", "1.00", "0.90"),
            ("2025Q1", date(2025, 3, 31), "110", "22", "1.10", "1.00"),
            ("2025Q2", date(2025, 6, 30), "100", "25", "1.00", "0.80"),
            ("2025Q3", date(2025, 9, 30), "108", "21.6", "0.90", "1.00"),
            ("2025Q4", date(2025, 12, 31), "125", "31.25", "1.20", None),
            ("2026Q1", date(2026, 3, 31), "132", "33", "1.25", "1.25"),
        ]
        db.add_all(
            EarningsReport(
                symbol=asset.symbol,
                market=asset.market,
                period=period,
                period_end=period_end,
                revenue=Decimal(revenue),
                operating_income=Decimal(operating_income),
                eps=Decimal(eps),
                eps_estimate=Decimal(estimate) if estimate is not None else None,
                source="fixture",
            )
            for period, period_end, revenue, operating_income, eps, estimate in rows
        )
        db.commit()
        return asset.id


def test_get_summary_derives_latest_four_quarters(client: TestClient) -> None:
    set_current_user(1)
    asset_id = create_asset_and_reports()

    response = client.get(f"/api/v1/assets/{asset_id}/earnings-summary")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert [item["period"] for item in data["quarters"]] == [
        "2025Q2", "2025Q3", "2025Q4", "2026Q1"
    ]
    # Source: values calculated from the fixture above.
    assert [item["revenue_yoy_percent"] for item in data["quarters"]] == [
        "25.00", "20.00", "25.00", "20.00"
    ]
    assert [item["operating_margin_percent"] for item in data["quarters"]] == [
        "25.00", "20.00", "25.00", "25.00"
    ]
    assert [item["eps_surprise_percent"] for item in data["quarters"]] == [
        "25.00", "-10.00", None, "0.00"
    ]
    assert data["guidance"] is None
    assert data["segments"] == []


def test_get_summary_excludes_incomplete_rows_and_allows_missing_yoy(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset_and_reports()
    with TestingSessionLocal() as db:
        latest = db.query(EarningsReport).filter_by(period="2026Q1").one()
        latest.operating_income = None
        old = db.query(EarningsReport).filter_by(period="2024Q2").one()
        db.delete(old)
        db.commit()

    data = cast(
        dict[str, Any],
        api_data(client.get(f"/api/v1/assets/{asset_id}/earnings-summary")),
    )

    assert [item["period"] for item in data["quarters"]] == [
        "2025Q1", "2025Q2", "2025Q3", "2025Q4"
    ]
    quarter = next(item for item in data["quarters"] if item["period"] == "2025Q2")
    assert quarter["revenue_yoy_percent"] is None


def test_get_summary_without_data_returns_empty_contract(client: TestClient) -> None:
    set_current_user(1)
    with TestingSessionLocal() as db:
        asset = Asset(symbol="EMPTY", name="Empty", market="NASDAQ")
        db.add(asset)
        db.commit()
        db.refresh(asset)
        asset_id = asset.id

    data = cast(
        dict[str, Any],
        api_data(client.get(f"/api/v1/assets/{asset_id}/earnings-summary")),
    )
    assert data["quarters"] == []
    assert data["guidance"] is None
    assert data["segments"] == []


def test_get_earnings_summary_returns_404_for_missing_asset(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset_and_reports()
    response = client.get(f"/api/v1/assets/{asset_id + 1}/earnings-summary")
    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }


def test_get_earnings_summary_requires_authentication(client: TestClient) -> None:
    asset_id = create_asset_and_reports()
    response = client.get(f"/api/v1/assets/{asset_id}/earnings-summary")
    assert response.status_code == 401
