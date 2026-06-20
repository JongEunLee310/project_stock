from collections.abc import Mapping
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.domains.alert_candidates.schema import AlertCandidateCreate
from app.domains.alert_candidates.service import AlertCandidateService
from app.domains.alert_candidates.types import AlertCandidateType, AlertImportance
from app.main import app
from tests.conftest import TestingSessionLocal, api_data, api_meta, set_current_user

Contract = Mapping[str, type[Any] | tuple[type[Any], ...]]


def assert_envelope(body: Mapping[str, Any], *, has_meta: bool) -> None:
    assert set(body) == {"data", "message", "error", "meta"}
    assert body["message"] is None
    assert body["error"] is None
    if has_meta:
        assert_contract(body["meta"], {"page": int, "size": int, "total": int})
    else:
        assert body["meta"] is None


def assert_contract(payload: Any, contract: Contract) -> None:
    assert isinstance(payload, dict)
    missing = set(contract) - set(payload)
    assert not missing, f"missing contract fields: {sorted(missing)}"
    for field, expected_type in contract.items():
        assert isinstance(payload[field], expected_type), field


def create_asset(client: TestClient, symbol: str = "AAPL") -> dict[str, Any]:
    response = client.post(
        "/api/v1/assets",
        json={
            "symbol": symbol,
            "name": f"{symbol} Inc.",
            "market": "NASDAQ",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "description": "Makes devices and services.",
        },
    )
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


def create_watchlist(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/v1/watchlists", json={"name": "Core"})
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


def create_portfolio(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/v1/portfolios",
        json={"name": "Long Term", "concentration_threshold": "0.6"},
    )
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


def create_alert_candidate(user_id: int) -> None:
    db = TestingSessionLocal()
    try:
        AlertCandidateService(db).create_candidate(
            AlertCandidateCreate(
                user_id=user_id,
                candidate_type=AlertCandidateType.NEWS_SURGE,
                importance=AlertImportance.MEDIUM,
                title="News volume increased",
                message="Review before sending a notification.",
                evidence={"source": "test"},
            )
        )
    finally:
        db.close()


WATCHLIST_CONTRACT: Contract = {
    "id": int,
    "user_id": int,
    "name": str,
    "created_at": str,
}

WATCHLIST_ITEM_CONTRACT: Contract = {
    "id": int,
    "watchlist_id": int,
    "asset_id": int,
    "priority": int,
    "reason": (str, type(None)),
    "tags": list,
    "memo": (str, type(None)),
    "created_at": str,
}

ASSET_DETAIL_CONTRACT: Contract = {
    "id": int,
    "symbol": str,
    "name": str,
    "market": str,
    "price": str,
    "previous_close": str,
    "change": str,
    "change_percent": str,
    "currency": str,
    "sector": (str, type(None)),
    "industry": (str, type(None)),
    "description": (str, type(None)),
    "as_of": str,
}

RESEARCH_SUMMARY_CONTRACT: Contract = {
    "asset_id": int,
    "positive_factors": list,
    "negative_factors": list,
    "items_to_verify": list,
    "sources": list,
    "updated_at": str,
}

RESEARCH_SUMMARY_SOURCE_CONTRACT: Contract = {
    "type": str,
    "label": str,
    "url": (str, type(None)),
}

PORTFOLIO_SUMMARY_CONTRACT: Contract = {
    "portfolio_id": int,
    "concentration_threshold": str,
    "total_cost_value": str,
    "total_value": str,
    "cash_balance": str,
    "cash_weight": str,
    "has_sector_concentration": bool,
    "positions": list,
    "sector_weights": list,
}

POSITION_WEIGHT_CONTRACT: Contract = {
    "asset_id": int,
    "quantity": str,
    "avg_buy_price": str,
    "cost_value": str,
    "market_value": str,
    "cost_weight": str,
    "weight": str,
    "exceeds_threshold": bool,
}

SECTOR_WEIGHT_CONTRACT: Contract = {
    "sector": str,
    "market_value": str,
    "weight": str,
    "exceeds_threshold": bool,
}

ALERT_CANDIDATE_CONTRACT: Contract = {
    "id": int,
    "user_id": int,
    "candidate_type": str,
    "importance": str,
    "status": str,
    "title": str,
    "message": (str, type(None)),
    "asset_id": (int, type(None)),
    "evidence": (dict, type(None)),
    "created_at": str,
}


def test_watchlist_response_contract(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    asset = create_asset(client)
    item_response = client.post(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        json={
            "asset_id": asset["id"],
            "priority": 10,
            "reason": "Core AI exposure",
            "tags": ["ai"],
            "memo": "Review after earnings.",
        },
    )
    assert item_response.status_code == 201

    list_response = client.get("/api/v1/watchlists")
    items_response = client.get(f"/api/v1/watchlists/{watchlist['id']}/items")

    assert list_response.status_code == 200
    assert_envelope(list_response.json(), has_meta=True)
    watchlists = cast(list[dict[str, Any]], api_data(list_response))
    assert_contract(watchlists[0], WATCHLIST_CONTRACT)
    assert api_meta(list_response) == {"page": 1, "size": 20, "total": 1}

    assert items_response.status_code == 200
    assert_envelope(items_response.json(), has_meta=True)
    items = cast(list[dict[str, Any]], api_data(items_response))
    assert_contract(items[0], WATCHLIST_ITEM_CONTRACT)
    assert isinstance(items[0]["tags"][0], str)


def test_stock_detail_response_contract(client: TestClient) -> None:
    asset = create_asset(client)

    response = client.get(f"/api/v1/assets/{asset['id']}/detail")

    assert response.status_code == 200
    assert_envelope(response.json(), has_meta=False)
    assert_contract(api_data(response), ASSET_DETAIL_CONTRACT)


def test_research_summary_response_contract(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)

    response = client.get(f"/api/v1/assets/{asset['id']}/research-summary")

    assert response.status_code == 200
    assert_envelope(response.json(), has_meta=False)
    data = cast(dict[str, Any], api_data(response))
    assert_contract(data, RESEARCH_SUMMARY_CONTRACT)
    assert all(isinstance(item, str) for item in data["positive_factors"])
    assert all(isinstance(item, str) for item in data["negative_factors"])
    assert all(isinstance(item, str) for item in data["items_to_verify"])
    assert_contract(data["sources"][0], RESEARCH_SUMMARY_SOURCE_CONTRACT)


def test_portfolio_summary_response_contract(client: TestClient) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client)
    asset = create_asset(client)
    position_response = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/positions",
        json={"asset_id": asset["id"], "quantity": "2", "avg_buy_price": "100"},
    )
    assert position_response.status_code == 201

    response = client.get(f"/api/v1/portfolios/{portfolio['id']}/summary")

    assert response.status_code == 200
    assert_envelope(response.json(), has_meta=False)
    data = cast(dict[str, Any], api_data(response))
    assert_contract(data, PORTFOLIO_SUMMARY_CONTRACT)
    assert_contract(data["positions"][0], POSITION_WEIGHT_CONTRACT)
    assert_contract(data["sector_weights"][0], SECTOR_WEIGHT_CONTRACT)


def test_alert_candidate_list_response_contract(client: TestClient) -> None:
    create_alert_candidate(1)
    set_current_user(1)

    response = client.get("/api/v1/alert-candidates")

    assert response.status_code == 200
    assert_envelope(response.json(), has_meta=True)
    candidates = cast(list[dict[str, Any]], api_data(response))
    assert_contract(candidates[0], ALERT_CANDIDATE_CONTRACT)
    assert api_meta(response) == {"page": 1, "size": 20, "total": 1}


def test_contract_helper_detects_missing_required_field() -> None:
    payload = {"id": 1, "name": "Core", "created_at": "2026-06-19T00:00:00"}

    with pytest.raises(AssertionError, match="missing contract fields"):
        assert_contract(payload, WATCHLIST_CONTRACT)


def test_openapi_contains_frontend_contract_paths_and_components() -> None:
    schema = app.openapi()

    expected_paths = {
        "/api/v1/watchlists",
        "/api/v1/watchlists/{watchlist_id}/items",
        "/api/v1/assets/{asset_id}/detail",
        "/api/v1/assets/{asset_id}/research-summary",
        "/api/v1/portfolios/{portfolio_id}/summary",
        "/api/v1/alert-candidates",
    }
    assert expected_paths <= set(schema["paths"])

    schemas = schema["components"]["schemas"]
    expected_components = {
        "PageMeta",
        "WatchlistResponse",
        "WatchlistItemResponse",
        "AssetDetailResponse",
        "ResearchSummaryResponse",
        "ResearchSummarySource",
        "PortfolioSummaryResponse",
        "PositionWeight",
        "SectorWeight",
        "AlertCandidateResponse",
    }
    assert expected_components <= set(schemas)
