from typing import Any, cast

from fastapi.testclient import TestClient

from tests.conftest import api_data, api_error, set_current_user
from tests.test_assets import create_asset


def test_get_buy_checklist_returns_four_items_and_incomplete(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset = create_asset(client)

    response = client.get(f"/api/v1/assets/{asset['id']}/buy-checklist")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["asset_id"] == asset["id"]
    assert [item["id"] for item in data["items"]] == [
        "valuation",
        "news_overheated",
        "portfolio_concentration",
        "earnings_disclosure",
    ]
    assert all(item["checked"] is False for item in data["items"])
    assert data["memo"] is None
    assert data["checked_item_keys"] == []
    assert data["is_complete"] is False


def test_save_buy_checklist_note_round_trips(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)
    payload = {
        "memo": "Buy only after reviewing valuation.",
        "checked_item_keys": ["valuation", "news_overheated"],
    }

    save_response = client.put(
        f"/api/v1/assets/{asset['id']}/buy-checklist",
        json=payload,
    )
    get_response = client.get(f"/api/v1/assets/{asset['id']}/buy-checklist")

    assert save_response.status_code == 200
    assert get_response.status_code == 200
    data = cast(dict[str, Any], api_data(get_response))
    assert data["memo"] == "Buy only after reviewing valuation."
    assert data["checked_item_keys"] == ["valuation", "news_overheated"]
    assert [item["checked"] for item in data["items"]] == [
        True,
        True,
        False,
        False,
    ]
    assert data["is_complete"] is False
    assert data["decided_at"] is None


def test_other_user_cannot_read_buy_checklist_note(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)
    response = client.put(
        f"/api/v1/assets/{asset['id']}/buy-checklist",
        json={
            "memo": "Owner memo",
            "checked_item_keys": [
                "valuation",
                "news_overheated",
                "portfolio_concentration",
                "earnings_disclosure",
            ],
        },
    )
    assert response.status_code == 200

    set_current_user(2, "other@example.com")
    other_response = client.get(f"/api/v1/assets/{asset['id']}/buy-checklist")

    assert other_response.status_code == 200
    data = cast(dict[str, Any], api_data(other_response))
    assert data["memo"] is None
    assert data["checked_item_keys"] == []
    assert data["is_complete"] is False


def test_buy_checklist_is_complete_requires_memo_and_all_items(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset = create_asset(client)
    all_keys = [
        "valuation",
        "news_overheated",
        "portfolio_concentration",
        "earnings_disclosure",
    ]

    missing_memo_response = client.put(
        f"/api/v1/assets/{asset['id']}/buy-checklist",
        json={"memo": " ", "checked_item_keys": all_keys},
    )
    complete_response = client.put(
        f"/api/v1/assets/{asset['id']}/buy-checklist",
        json={"memo": "All checks reviewed.", "checked_item_keys": all_keys},
    )

    assert missing_memo_response.status_code == 200
    assert api_data(missing_memo_response)["is_complete"] is False
    assert api_data(missing_memo_response)["decided_at"] is None
    assert complete_response.status_code == 200
    assert api_data(complete_response)["is_complete"] is True
    assert api_data(complete_response)["decided_at"] is not None


def test_buy_checklist_decided_at_is_only_set_when_complete(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset = create_asset(client)
    all_keys = [
        "valuation",
        "news_overheated",
        "portfolio_concentration",
        "earnings_disclosure",
    ]

    incomplete_response = client.put(
        f"/api/v1/assets/{asset['id']}/buy-checklist",
        json={"memo": "Review started.", "checked_item_keys": ["valuation"]},
    )
    complete_response = client.put(
        f"/api/v1/assets/{asset['id']}/buy-checklist",
        json={"memo": "All checks reviewed.", "checked_item_keys": all_keys},
    )
    decided_at = api_data(complete_response)["decided_at"]
    second_complete_response = client.put(
        f"/api/v1/assets/{asset['id']}/buy-checklist",
        json={"memo": "Still reviewed.", "checked_item_keys": all_keys},
    )

    assert incomplete_response.status_code == 200
    assert api_data(incomplete_response)["decided_at"] is None
    assert complete_response.status_code == 200
    assert decided_at is not None
    assert second_complete_response.status_code == 200
    assert api_data(second_complete_response)["decided_at"] == decided_at


def test_buy_checklist_returns_404_when_asset_missing(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/assets/999/buy-checklist")

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }
