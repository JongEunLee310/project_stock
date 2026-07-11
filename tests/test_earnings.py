from decimal import Decimal
from typing import Any, cast

from fastapi.testclient import TestClient

from app.domains.assets.model import Asset
from app.domains.earnings.service import _TEMPLATES
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user


def create_assets(count: int) -> list[int]:
    with TestingSessionLocal() as db:
        assets = [
            Asset(
                symbol=f"ERN{index}",
                name=f"Earnings {index}",
                market="NASDAQ",
            )
            for index in range(count)
        ]
        db.add_all(assets)
        db.commit()
        for asset in assets:
            db.refresh(asset)
        return [asset.id for asset in assets]


def test_get_earnings_summary_rotates_all_templates_and_is_deterministic(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_ids = create_assets(len(_TEMPLATES))
    responses: list[dict[str, Any]] = []

    for asset_id in asset_ids:
        first_response = client.get(f"/api/v1/assets/{asset_id}/earnings-summary")
        second_response = client.get(f"/api/v1/assets/{asset_id}/earnings-summary")

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        first_data = cast(dict[str, Any], api_data(first_response))
        second_data = cast(dict[str, Any], api_data(second_response))
        assert first_data == second_data
        assert first_data["asset_id"] == asset_id
        assert len(first_data["quarters"]) == 4
        periods = [quarter["period"] for quarter in first_data["quarters"]]
        assert periods == sorted(periods)
        responses.append(first_data)

    quarters = [
        quarter for response in responses for quarter in response["quarters"]
    ]
    surprises = [
        Decimal(quarter["eps_surprise_percent"])
        for quarter in quarters
        if quarter["eps_surprise_percent"] is not None
    ]
    assert any(surprise > 0 for surprise in surprises)
    assert any(surprise < 0 for surprise in surprises)
    assert any(
        quarter["eps_estimate"] is None
        and quarter["eps_surprise_percent"] is None
        for quarter in quarters
    )


def test_get_earnings_summary_returns_404_for_missing_asset(
    client: TestClient,
) -> None:
    set_current_user(1)
    existing_asset_id = create_assets(1)[0]

    response = client.get(
        f"/api/v1/assets/{existing_asset_id + 1}/earnings-summary"
    )

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }


def test_get_earnings_summary_requires_authentication(client: TestClient) -> None:
    asset_id = create_assets(1)[0]

    response = client.get(f"/api/v1/assets/{asset_id}/earnings-summary")

    assert response.status_code == 401
