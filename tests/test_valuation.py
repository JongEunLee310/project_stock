from datetime import date
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.domains.assets.model import Asset
from app.domains.valuation.model import ValuationSnapshot
from app.domains.valuation.schema import ValuationMetricName
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user


def create_asset(*, symbol: str, sector: str | None = None) -> int:
    with TestingSessionLocal() as db:
        asset = Asset(
            symbol=symbol,
            name=f"{symbol} Inc.",
            market="NASDAQ",
            sector=sector,
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset.id


def create_snapshot(symbol: str, **overrides: object) -> None:
    values: dict[str, object] = {
        "symbol": symbol,
        "market": "NASDAQ",
        "as_of": date(2026, 7, 11),
        # Source: docs/designs/279-valuation-real-collection.md test fixture.
        "per": Decimal("18.3000"),
        "forward_per": Decimal("16.9000"),
        "psr": Decimal("2.4000"),
        "pbr": Decimal("3.1000"),
        "ev_ebitda": Decimal("11.7000"),
        "peg": Decimal("1.2000"),
        "fcf_yield": Decimal("5.4000"),
        "source": "fixture",
    }
    values.update(overrides)
    with TestingSessionLocal() as db:
        db.add(ValuationSnapshot(**values))
        db.commit()


def test_get_valuation_metrics_uses_latest_snapshot_and_preserves_order(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset(symbol="LATEST")
    create_snapshot("LATEST", as_of=date(2026, 7, 10), per=Decimal("10"))
    create_snapshot("LATEST", as_of=date(2026, 7, 11), peg=None)

    response = client.get(f"/api/v1/assets/{asset_id}/valuation-metrics")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert [item["metric"] for item in data["metrics"]] == [
        metric.value for metric in ValuationMetricName
    ]
    values = {item["metric"]: item["value"] for item in data["metrics"]}
    assert values["PER"] == "18.3000"
    assert values["PEG"] is None
    assert all(item["five_year_median"] is None for item in data["metrics"])
    assert all(item["percentile"] is None for item in data["metrics"])
    assert data["profile"] == "GENERAL"
    assert data["highlighted_metrics"] == ["PER", "PBR", "EV_EBITDA"]


def test_get_valuation_metrics_without_snapshot_returns_null_values(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset(symbol="EMPTY")

    response = client.get(f"/api/v1/assets/{asset_id}/valuation-metrics")

    data = cast(dict[str, Any], api_data(response))
    assert data["profile"] == "GENERAL"
    assert all(item["value"] is None for item in data["metrics"])


@pytest.mark.parametrize(
    ("symbol", "sector", "per", "forward_per", "profile", "highlights"),
    [
        (
            "BANK",
            "Financial Services",
            None,
            None,
            "FINANCIAL",
            ["PBR", "PER"],
        ),
        ("LOSS", "Technology", None, None, "DEFICIT", ["PSR", "FCF_YIELD"]),
        (
            "PROFIT",
            "Technology",
            Decimal("20"),
            None,
            "GENERAL",
            ["PER", "PBR", "EV_EBITDA"],
        ),
    ],
)
def test_get_valuation_metrics_applies_profile_rules(
    client: TestClient,
    symbol: str,
    sector: str,
    per: Decimal | None,
    forward_per: Decimal | None,
    profile: str,
    highlights: list[str],
) -> None:
    set_current_user(1)
    asset_id = create_asset(symbol=symbol, sector=sector)
    create_snapshot(symbol, per=per, forward_per=forward_per)

    data = cast(
        dict[str, Any],
        api_data(client.get(f"/api/v1/assets/{asset_id}/valuation-metrics")),
    )

    assert data["profile"] == profile
    assert data["highlighted_metrics"] == highlights


def test_get_valuation_metrics_returns_404_for_missing_asset(
    client: TestClient,
) -> None:
    set_current_user(1)
    existing_asset_id = create_asset(symbol="EXISTING")

    response = client.get(
        f"/api/v1/assets/{existing_asset_id + 1}/valuation-metrics"
    )

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }


def test_get_valuation_metrics_requires_authentication(client: TestClient) -> None:
    asset_id = create_asset(symbol="AUTH")

    response = client.get(f"/api/v1/assets/{asset_id}/valuation-metrics")

    assert response.status_code == 401
