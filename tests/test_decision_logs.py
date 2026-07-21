from typing import Any, cast

from fastapi.testclient import TestClient

from tests.conftest import api_data, api_error, api_meta, set_current_user


def decision_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "target_type": "SYMBOL",
        "target_id": "AAPL",
        "symbol": "AAPL",
        "decision_type": "BUY_REVIEW",
        "thesis": "Services revenue will keep growing.",
        "rationale": "Margins and buybacks support the thesis.",
        "confidence_level": "HIGH",
        "created_by": "USER",
        "decided_at": "2026-06-26T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def create_decision_log(
    client: TestClient,
    **overrides: Any,
) -> dict[str, Any]:
    response = client.post("/api/v1/decision-logs", json=decision_payload(**overrides))
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


def test_create_decision_log_round_trips_contract_fields(client: TestClient) -> None:
    set_current_user(1)

    data = create_decision_log(client)

    assert data["id"] == 1
    assert data["user_id"] == 1
    assert data["target_type"] == "SYMBOL"
    assert data["target_id"] == "AAPL"
    assert data["symbol"] == "AAPL"
    assert data["decision_type"] == "BUY_REVIEW"
    assert data["status"] == "DRAFT"
    assert data["thesis"] == "Services revenue will keep growing."
    assert data["rationale"] == "Margins and buybacks support the thesis."
    assert data["confidence_level"] == "HIGH"
    assert data["created_by"] == "USER"
    assert data["superseded_by_id"] is None
    assert data["decided_at"] == "2026-06-26T00:00:00Z"
    assert data["activated_at"] is None
    assert data["reviewed_at"] is None
    assert data["closed_at"] is None
    assert data["created_at"].endswith("Z")
    assert data["updated_at"].endswith("Z")


def test_create_decision_log_uses_defaults(client: TestClient) -> None:
    set_current_user(1)

    response = client.post(
        "/api/v1/decision-logs",
        json={
            "target_type": "SYMBOL",
            "target_id": "MSFT",
            "symbol": "MSFT",
            "decision_type": "WATCH",
        },
    )

    assert response.status_code == 201
    data = cast(dict[str, Any], api_data(response))
    assert data["status"] == "DRAFT"
    assert data["created_by"] == "USER"
    assert data["decided_at"] is None


def test_get_decision_log_returns_owned_record(client: TestClient) -> None:
    set_current_user(1)
    decision_log = create_decision_log(client)

    response = client.get(f"/api/v1/decision-logs/{decision_log['id']}")

    assert response.status_code == 200
    assert api_data(response) == decision_log


def test_list_decision_logs_returns_only_current_user_and_paginates(
    client: TestClient,
) -> None:
    set_current_user(1)
    first = create_decision_log(
        client,
        target_id="AAPL",
        symbol="AAPL",
        decided_at="2026-06-24T00:00:00Z",
    )
    second = create_decision_log(
        client,
        target_id="MSFT",
        symbol="MSFT",
        decided_at="2026-06-25T00:00:00Z",
    )
    set_current_user(2, "other@example.com")
    create_decision_log(
        client,
        target_id="TSLA",
        symbol="TSLA",
        decided_at="2026-06-26T00:00:00Z",
    )
    set_current_user(1)

    response = client.get(
        "/api/v1/decision-logs",
        params={"page": 2, "size": 1, "sort": "-decided_at"},
    )

    assert response.status_code == 200
    assert api_data(response) == [first]
    assert second["symbol"] == "MSFT"
    assert api_meta(response) == {"page": 2, "size": 1, "total": 2}


def test_list_decision_logs_supports_created_at_sort(client: TestClient) -> None:
    set_current_user(1)
    first = create_decision_log(client, target_id="AAPL", symbol="AAPL")
    second = create_decision_log(client, target_id="MSFT", symbol="MSFT")

    response = client.get(
        "/api/v1/decision-logs",
        params={"sort": "-created_at"},
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert [item["id"] for item in data] == [second["id"], first["id"]]


def test_list_decision_logs_rejects_invalid_sort(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/decision-logs", params={"sort": "symbol"})

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"


def test_get_decision_log_stats_counts_types_and_total(client: TestClient) -> None:
    set_current_user(1)
    create_decision_log(client, target_id="AAPL", decision_type="BUY_REVIEW")
    create_decision_log(client, target_id="MSFT", decision_type="BUY_REVIEW")
    create_decision_log(client, target_id="NVDA", decision_type="WATCH")
    create_decision_log(client, target_id="TSLA", decision_type="SELL_REVIEW")

    response = client.get("/api/v1/decision-logs/stats")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["decision_type_counts"] == {
        "BUY_REVIEW": 2,
        "WATCH": 1,
        "SELL_REVIEW": 1,
    }
    assert data["total"] == 4


def test_get_decision_log_stats_recent_reviewed_is_scoped_and_sorted(
    client: TestClient,
) -> None:
    set_current_user(1)
    owner_reviewed = create_decision_log(
        client,
        target_id="AAPL",
        symbol="AAPL",
        rationale="Owner rationale",
    )
    response = client.patch(
        f"/api/v1/decision-logs/{owner_reviewed['id']}",
        json={"status": "REVIEWED", "reviewed_at": "2026-06-27T00:00:00Z"},
    )
    assert response.status_code == 200

    set_current_user(2, "other@example.com")
    other = create_decision_log(client, target_id="TSLA", symbol="TSLA")
    response = client.patch(
        f"/api/v1/decision-logs/{other['id']}",
        json={"status": "REVIEWED", "reviewed_at": "2026-06-28T00:00:00Z"},
    )
    assert response.status_code == 200

    set_current_user(1)
    response = client.get("/api/v1/decision-logs/stats")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["recent_reviewed"] == [
        {
            "id": owner_reviewed["id"],
            "symbol": "AAPL",
            "decision_type": "BUY_REVIEW",
            "rationale": "Owner rationale",
            "reviewed_at": "2026-06-27T00:00:00Z",
        }
    ]


def test_patch_decision_log_stamps_reviewed_and_closed_at(
    client: TestClient,
) -> None:
    set_current_user(1)
    decision_log = create_decision_log(client)

    reviewed_response = client.patch(
        f"/api/v1/decision-logs/{decision_log['id']}",
        json={"status": "REVIEWED"},
    )
    assert reviewed_response.status_code == 200
    reviewed = cast(dict[str, Any], api_data(reviewed_response))
    assert reviewed["status"] == "REVIEWED"
    assert reviewed["reviewed_at"].endswith("Z")

    closed_response = client.patch(
        f"/api/v1/decision-logs/{decision_log['id']}",
        json={"status": "CLOSED", "rationale": "Closed after review."},
    )
    assert closed_response.status_code == 200
    closed = cast(dict[str, Any], api_data(closed_response))
    assert closed["status"] == "CLOSED"
    assert closed["rationale"] == "Closed after review."
    assert closed["reviewed_at"] == reviewed["reviewed_at"]
    assert closed["closed_at"].endswith("Z")


def test_get_and_patch_decision_log_block_other_users(client: TestClient) -> None:
    set_current_user(1)
    decision_log = create_decision_log(client)
    set_current_user(2, "other@example.com")

    get_response = client.get(f"/api/v1/decision-logs/{decision_log['id']}")
    patch_response = client.patch(
        f"/api/v1/decision-logs/{decision_log['id']}",
        json={"rationale": "No access."},
    )

    assert get_response.status_code == 403
    assert api_error(get_response)["code"] == "DECISION_LOG_FORBIDDEN"
    assert patch_response.status_code == 403
    assert api_error(patch_response)["code"] == "DECISION_LOG_FORBIDDEN"


def test_get_decision_log_returns_not_found(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/decision-logs/999")

    assert response.status_code == 404
    assert api_error(response)["code"] == "DECISION_LOG_NOT_FOUND"


def test_decision_log_validation_rejects_enum_values(client: TestClient) -> None:
    set_current_user(1)

    decision_type_response = client.post(
        "/api/v1/decision-logs",
        json=decision_payload(decision_type="INVALID"),
    )
    confidence_response = client.post(
        "/api/v1/decision-logs",
        json=decision_payload(confidence_level="VERY_HIGH"),
    )

    assert decision_type_response.status_code == 422
    assert api_error(decision_type_response)["code"] == "VALIDATION_ERROR"
    assert confidence_response.status_code == 422
    assert api_error(confidence_response)["code"] == "VALIDATION_ERROR"


def test_decision_log_response_uses_snake_case_fields(client: TestClient) -> None:
    set_current_user(1)

    data = create_decision_log(client)

    assert "target_type" in data
    assert "confidence_level" in data
    assert "superseded_by_id" in data
    assert "targetType" not in data
    assert "confidenceLevel" not in data
    assert "supersededById" not in data
