from typing import Any, cast

from fastapi.testclient import TestClient

from tests.conftest import set_current_user


def create_asset(client: TestClient, symbol: str = "AAPL") -> dict[str, Any]:
    response = client.post(
        "/api/v1/assets",
        json={"symbol": symbol, "name": f"{symbol} Inc.", "market": "NASDAQ"},
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def report_payload(asset_id: int) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "summary": "Services growth offsets softer hardware demand.",
        "positive_factors": ["Services revenue accelerated", "Margins improved"],
        "negative_factors": ["Hardware demand remains soft"],
        "risk_level": "MEDIUM",
        "thesis_conflict_status": "SUPPORTS",
        "conflict_reason": "The news supports the active thesis.",
        "news_item_ids": [10, 11],
    }


def create_report(client: TestClient, asset_id: int) -> dict[str, Any]:
    response = client.post("/api/v1/reports", json=report_payload(asset_id))
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def test_create_research_report_success(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)

    data = create_report(client, asset["id"])

    assert data["id"] > 0
    assert data["asset_id"] == asset["id"]
    assert data["summary"] == "Services growth offsets softer hardware demand."
    assert data["positive_factors"] == [
        "Services revenue accelerated",
        "Margins improved",
    ]
    assert data["news_item_ids"] == [10, 11]
    assert "created_at" in data


def test_list_research_reports_by_asset(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)
    other_asset = create_asset(client, "MSFT")
    report = create_report(client, asset["id"])
    create_report(client, other_asset["id"])

    response = client.get("/api/v1/reports", params={"asset_id": asset["id"]})

    assert response.status_code == 200
    assert response.json() == [report]


def test_get_research_report_detail(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)
    report = create_report(client, asset["id"])

    response = client.get(f"/api/v1/reports/{report['id']}")

    assert response.status_code == 200
    assert response.json() == report


def test_get_research_report_returns_404_when_missing(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/reports/999")

    assert response.status_code == 404


def test_list_research_reports_requires_asset_id(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/reports")

    assert response.status_code == 422


def test_report_response_returns_json_fields_as_lists(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)

    data = create_report(client, asset["id"])

    assert isinstance(data["positive_factors"], list)
    assert isinstance(data["news_item_ids"], list)
