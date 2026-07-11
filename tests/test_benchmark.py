from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.domains.assets.model import Asset
from app.domains.benchmark.schema import BenchmarkSeriesKind
from app.domains.benchmark.service import _POINT_COUNTS
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user


def create_asset() -> int:
    with TestingSessionLocal() as db:
        asset = Asset(symbol="BMK", name="Benchmark", market="NASDAQ")
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset.id


@pytest.mark.parametrize("range_", list(_POINT_COUNTS))
def test_get_benchmark_comparison_returns_aligned_deterministic_series(
    client: TestClient,
    range_: str,
) -> None:
    set_current_user(1)
    asset_id = create_asset()

    first_response = client.get(
        f"/api/v1/assets/{asset_id}/benchmark-comparison",
        params={"range": range_},
    )
    second_response = client.get(
        f"/api/v1/assets/{asset_id}/benchmark-comparison",
        params={"range": range_},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_data = cast(dict[str, Any], api_data(first_response))
    second_data = cast(dict[str, Any], api_data(second_response))
    assert first_data == second_data
    assert first_data["asset_id"] == asset_id
    assert first_data["range"] == range_
    assert [series["kind"] for series in first_data["series"]] == [
        kind.value for kind in BenchmarkSeriesKind
    ]
    date_axes = [
        [point["date"] for point in series["points"]]
        for series in first_data["series"]
    ]
    assert all(date_axis == date_axes[0] for date_axis in date_axes)
    assert all(len(series["points"]) == _POINT_COUNTS[range_] for series in first_data["series"])
    assert all(series["points"][0]["return_percent"] == "0" for series in first_data["series"])


def test_get_benchmark_comparison_defaults_to_three_months(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset()

    response = client.get(f"/api/v1/assets/{asset_id}/benchmark-comparison")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["range"] == "3M"


def test_get_benchmark_comparison_rejects_unsupported_range(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset()

    response = client.get(
        f"/api/v1/assets/{asset_id}/benchmark-comparison",
        params={"range": "1D"},
    )

    assert response.status_code == 422


def test_get_benchmark_comparison_returns_404_for_missing_asset(
    client: TestClient,
) -> None:
    set_current_user(1)
    existing_asset_id = create_asset()

    response = client.get(
        f"/api/v1/assets/{existing_asset_id + 1}/benchmark-comparison"
    )

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }


def test_get_benchmark_comparison_requires_authentication(
    client: TestClient,
) -> None:
    asset_id = create_asset()

    response = client.get(f"/api/v1/assets/{asset_id}/benchmark-comparison")

    assert response.status_code == 401
