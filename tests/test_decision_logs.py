from typing import Any, cast

from fastapi.testclient import TestClient

from tests.conftest import api_data, api_error, api_meta, set_current_user


def decision_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "decision_type": "BUY_CONSIDER",
        "summary": "Earnings setup is attractive.",
        "reason": "Services margin and buybacks support the thesis.",
        "risk_note": "Valuation remains elevated.",
        "action_plan": "Review after earnings.",
        "confidence_score": 72,
        "target_price": "220.0000",
        "stop_loss_price": "180.0000",
        "valuation_snapshot": {"pe": 28},
        "news_snapshot": {"headline_count": 3},
        "portfolio_snapshot": {"weight": "0.12"},
        "ai_analysis_snapshot": {"rating": "positive"},
        "cognitive_risks": ["confirmation_bias"],
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
    assert data["ticker"] == "AAPL"
    assert data["company_name"] == "Apple Inc."
    assert data["decision_type"] == "BUY_CONSIDER"
    assert data["decision_status"] == "OPEN"
    assert data["summary"] == "Earnings setup is attractive."
    assert data["reason"] == "Services margin and buybacks support the thesis."
    assert data["risk_note"] == "Valuation remains elevated."
    assert data["action_plan"] == "Review after earnings."
    assert data["confidence_score"] == 72
    assert data["target_price"] == "220.0000"
    assert data["stop_loss_price"] == "180.0000"
    assert data["valuation_snapshot"] == {"pe": 28}
    assert data["news_snapshot"] == {"headline_count": 3}
    assert data["portfolio_snapshot"] == {"weight": "0.12"}
    assert data["ai_analysis_snapshot"] == {"rating": "positive"}
    assert data["cognitive_risks"] == ["confirmation_bias"]
    assert data["created_by"] == "USER"
    assert data["decided_at"] == "2026-06-26T00:00:00Z"
    assert data["reviewed_at"] is None
    assert data["closed_at"] is None
    assert data["created_at"].endswith("Z")
    assert data["updated_at"].endswith("Z")


def test_create_decision_log_uses_defaults(client: TestClient) -> None:
    set_current_user(1)

    response = client.post(
        "/api/v1/decision-logs",
        json={"ticker": "MSFT", "decision_type": "WATCH"},
    )

    assert response.status_code == 201
    data = cast(dict[str, Any], api_data(response))
    assert data["decision_status"] == "OPEN"
    assert data["created_by"] == "USER"
    assert data["cognitive_risks"] == []
    assert data["decided_at"].endswith("Z")


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
        ticker="AAPL",
        decided_at="2026-06-24T00:00:00Z",
    )
    second = create_decision_log(
        client,
        ticker="MSFT",
        decided_at="2026-06-25T00:00:00Z",
    )
    set_current_user(2, "other@example.com")
    create_decision_log(client, ticker="TSLA", decided_at="2026-06-26T00:00:00Z")
    set_current_user(1)

    response = client.get(
        "/api/v1/decision-logs",
        params={"page": 2, "size": 1, "sort": "-decided_at"},
    )

    assert response.status_code == 200
    assert api_data(response) == [first]
    assert second["ticker"] == "MSFT"
    assert api_meta(response) == {"page": 2, "size": 1, "total": 2}


def test_list_decision_logs_supports_created_at_sort(client: TestClient) -> None:
    set_current_user(1)
    first = create_decision_log(client, ticker="AAPL")
    second = create_decision_log(client, ticker="MSFT")

    response = client.get(
        "/api/v1/decision-logs",
        params={"sort": "-created_at"},
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert [item["id"] for item in data] == [second["id"], first["id"]]


def test_list_decision_logs_rejects_invalid_sort(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/decision-logs", params={"sort": "ticker"})

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"


def test_patch_decision_log_stamps_reviewed_and_closed_at(
    client: TestClient,
) -> None:
    set_current_user(1)
    decision_log = create_decision_log(client)

    reviewed_response = client.patch(
        f"/api/v1/decision-logs/{decision_log['id']}",
        json={"decision_status": "REVIEWED"},
    )
    assert reviewed_response.status_code == 200
    reviewed = cast(dict[str, Any], api_data(reviewed_response))
    assert reviewed["decision_status"] == "REVIEWED"
    assert reviewed["reviewed_at"].endswith("Z")

    closed_response = client.patch(
        f"/api/v1/decision-logs/{decision_log['id']}",
        json={"decision_status": "CLOSED", "summary": "Closed after review."},
    )
    assert closed_response.status_code == 200
    closed = cast(dict[str, Any], api_data(closed_response))
    assert closed["decision_status"] == "CLOSED"
    assert closed["summary"] == "Closed after review."
    assert closed["reviewed_at"] == reviewed["reviewed_at"]
    assert closed["closed_at"].endswith("Z")


def test_patch_decision_log_prefers_explicit_lifecycle_timestamp(
    client: TestClient,
) -> None:
    set_current_user(1)
    decision_log = create_decision_log(client)

    response = client.patch(
        f"/api/v1/decision-logs/{decision_log['id']}",
        json={
            "decision_status": "REVIEWED",
            "reviewed_at": "2026-06-27T00:00:00Z",
        },
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["reviewed_at"] == "2026-06-27T00:00:00Z"


def test_get_decision_log_blocks_other_users(client: TestClient) -> None:
    set_current_user(1)
    decision_log = create_decision_log(client)
    set_current_user(2, "other@example.com")

    response = client.get(f"/api/v1/decision-logs/{decision_log['id']}")

    assert response.status_code == 403
    assert api_error(response) == {
        "code": "DECISION_LOG_FORBIDDEN",
        "message": "의사결정 기록 접근 권한이 없습니다.",
    }


def test_patch_decision_log_blocks_other_users(client: TestClient) -> None:
    set_current_user(1)
    decision_log = create_decision_log(client)
    set_current_user(2, "other@example.com")

    response = client.patch(
        f"/api/v1/decision-logs/{decision_log['id']}",
        json={"summary": "No access."},
    )

    assert response.status_code == 403
    assert api_error(response)["code"] == "DECISION_LOG_FORBIDDEN"


def test_get_decision_log_returns_not_found(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/decision-logs/999")

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "DECISION_LOG_NOT_FOUND",
        "message": "의사결정 기록을 찾을 수 없습니다.",
    }


def test_decision_log_validation_rejects_enum_and_confidence(
    client: TestClient,
) -> None:
    set_current_user(1)

    enum_response = client.post(
        "/api/v1/decision-logs",
        json=decision_payload(decision_type="INVALID"),
    )
    confidence_response = client.post(
        "/api/v1/decision-logs",
        json=decision_payload(confidence_score=101),
    )

    assert enum_response.status_code == 422
    assert api_error(enum_response)["code"] == "VALIDATION_ERROR"
    assert confidence_response.status_code == 422
    assert api_error(confidence_response)["code"] == "VALIDATION_ERROR"


def test_decision_log_response_uses_snake_case_fields(client: TestClient) -> None:
    set_current_user(1)

    data = create_decision_log(client)

    assert "target_price" in data
    assert "stop_loss_price" in data
    assert "cognitive_risks" in data
    assert "targetPrice" not in data
    assert "stopLossPrice" not in data
    assert "cognitiveRisks" not in data
