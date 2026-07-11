from typing import Any, cast

from fastapi.testclient import TestClient

from app.domains.assets.model import Asset
from app.domains.valuation.schema import ValuationMetricName
from app.domains.valuation.service import _TEMPLATES
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user


def create_assets(count: int) -> list[int]:
    with TestingSessionLocal() as db:
        assets = [
            Asset(
                symbol=f"VAL{index}",
                name=f"Valuation {index}",
                market="NASDAQ",
            )
            for index in range(count)
        ]
        db.add_all(assets)
        db.commit()
        for asset in assets:
            db.refresh(asset)
        return [asset.id for asset in assets]


def test_get_valuation_metrics_rotates_all_templates_and_is_deterministic(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_ids = create_assets(len(_TEMPLATES))
    metric_order = [metric.value for metric in ValuationMetricName]
    responses: list[dict[str, Any]] = []

    for asset_id in asset_ids:
        first_response = client.get(
            f"/api/v1/assets/{asset_id}/valuation-metrics"
        )
        second_response = client.get(
            f"/api/v1/assets/{asset_id}/valuation-metrics"
        )

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        first_data = cast(dict[str, Any], api_data(first_response))
        second_data = cast(dict[str, Any], api_data(second_response))
        assert first_data == second_data
        assert first_data["asset_id"] == asset_id
        assert [item["metric"] for item in first_data["metrics"]] == metric_order
        assert set(first_data["highlighted_metrics"]) <= set(metric_order)
        assert all(
            item["percentile"] is None or 0 <= item["percentile"] <= 100
            for item in first_data["metrics"]
        )
        responses.append(first_data)

    deficit = next(item for item in responses if item["profile"] == "DEFICIT")
    deficit_metrics = {
        item["metric"]: item["value"] for item in deficit["metrics"]
    }
    assert deficit_metrics["PER"] is None
    assert deficit_metrics["FORWARD_PER"] is None
    assert deficit_metrics["PEG"] is None


def test_get_valuation_metrics_returns_404_for_missing_asset(
    client: TestClient,
) -> None:
    set_current_user(1)
    existing_asset_id = create_assets(1)[0]

    response = client.get(
        f"/api/v1/assets/{existing_asset_id + 1}/valuation-metrics"
    )

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }


def test_get_valuation_metrics_requires_authentication(client: TestClient) -> None:
    asset_id = create_assets(1)[0]

    response = client.get(f"/api/v1/assets/{asset_id}/valuation-metrics")

    assert response.status_code == 401
