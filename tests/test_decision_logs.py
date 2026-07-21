from datetime import UTC, datetime
from typing import Any, cast

from fastapi.testclient import TestClient

from app.domains.decision_logs.model import DecisionLog
from tests.conftest import (
    TestingSessionLocal,
    api_data,
    api_error,
    api_meta,
    set_current_user,
)


def decision_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "target": {"type": "SYMBOL", "id": "AAPL", "label": "Apple"},
        "decision_type": "BUY_REVIEW",
        "thesis": "Services revenue will keep growing.",
        "rationale": "Margins and buybacks support the thesis.",
        "confidence_level": "HIGH",
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


def test_create_decision_log_round_trips_nested_contract(client: TestClient) -> None:
    set_current_user(1)

    data = create_decision_log(
        client,
        supporting_reasons=["Recurring revenue is growing."],
        counter_arguments=["Valuation is demanding."],
        evidence=[
            {
                "type": "RESEARCH",
                "id": "report-1",
                "version": 2,
                "title": "Quarterly research",
                "summary": "Services margin improved.",
                "snapshot": {"margin": 0.32},
                "relationship": "SUPPORTING",
            },
            {
                "type": "NEWS",
                "title": "Demand concern",
                "relationship": "CONTRADICTING",
            },
        ],
        risks=[
            {
                "type": "VALUATION",
                "severity": "MEDIUM",
                "description": "Multiple expansion may reverse.",
            }
        ],
        review_triggers=[
            {
                "type": "DATE",
                "condition": {},
                "scheduled_at": "2026-08-21T00:00:00Z",
            }
        ],
    )

    assert data["user_id"] == 1
    assert data["target_type"] == "SYMBOL"
    assert data["target_id"] == "AAPL"
    assert data["symbol"] == "AAPL"
    assert data["status"] == "DRAFT"
    assert data["created_by"] == "USER"
    assert data["decided_at"] is None
    assert data["activated_at"] is None
    assert data["created_at"].endswith("Z")
    assert data["updated_at"].endswith("Z")
    assert [item["relationship"] for item in data["evidence"]] == [
        "SUPPORTING",
        "CONTRADICTING",
        "SUPPORTING",
        "CONTRADICTING",
    ]
    assert [item["title"] for item in data["evidence"]] == [
        "Quarterly research",
        "Demand concern",
        "Recurring revenue is growing.",
        "Valuation is demanding.",
    ]
    assert data["risks"][0]["type"] == "VALUATION"
    assert data["review_triggers"][0]["type"] == "DATE"
    assert data["review_triggers"][0]["status"] == "PENDING"


def test_create_requires_target_and_maps_non_symbol_target(client: TestClient) -> None:
    set_current_user(1)

    missing_target = client.post(
        "/api/v1/decision-logs",
        json={"decision_type": "WATCH"},
    )
    created = create_decision_log(
        client,
        target={"type": "TOPIC", "id": "ai-capex"},
        decision_type="WATCH",
    )

    assert missing_target.status_code == 422
    assert api_error(missing_target)["code"] == "VALIDATION_ERROR"
    assert created["target_type"] == "TOPIC"
    assert created["target_id"] == "ai-capex"
    assert created["symbol"] is None


def test_get_decision_log_returns_nested_detail(client: TestClient) -> None:
    set_current_user(1)
    created = create_decision_log(
        client,
        evidence=[{"type": "USER_MEMO", "title": "Owner memo"}],
        risks=[{"type": "FOMO", "severity": "LOW"}],
    )

    response = client.get(f"/api/v1/decision-logs/{created['id']}")

    assert response.status_code == 200
    detail = cast(dict[str, Any], api_data(response))
    assert detail["evidence"] == created["evidence"]
    assert detail["risks"] == created["risks"]
    assert detail["review_triggers"] == []
    assert detail["snapshots"] == []


def test_patch_updates_draft_and_rejects_active(client: TestClient) -> None:
    set_current_user(1)
    created = create_decision_log(client)

    patch_response = client.patch(
        f"/api/v1/decision-logs/{created['id']}",
        json={
            "target": {"type": "SYMBOL", "id": "MSFT"},
            "rationale": "Updated while drafting.",
            "confidence_level": "MEDIUM",
        },
    )
    assert patch_response.status_code == 200
    updated = cast(dict[str, Any], api_data(patch_response))
    assert updated["target_id"] == "MSFT"
    assert updated["symbol"] == "MSFT"
    assert updated["rationale"] == "Updated while drafting."

    activate_response = client.post(
        f"/api/v1/decision-logs/{created['id']}/activate",
        json={},
    )
    assert activate_response.status_code == 200
    rejected = client.patch(
        f"/api/v1/decision-logs/{created['id']}",
        json={"rationale": "Too late."},
    )
    assert rejected.status_code == 409
    assert api_error(rejected)["code"] == "DECISION_LOG_INVALID_STATE"


def test_activate_transitions_and_persists_snapshots(client: TestClient) -> None:
    set_current_user(1)
    created = create_decision_log(
        client,
        review_triggers=[
            {
                "type": "DATE",
                "condition": {"reason": "earnings"},
                "scheduled_at": "2026-08-21T00:00:00Z",
            },
            {"type": "EVENT", "condition": {"event": "guidance_change"}},
        ],
    )

    response = client.post(
        f"/api/v1/decision-logs/{created['id']}/activate",
        json={
            "snapshots": [
                {"snapshot_type": "PRICE", "data": {"price": "225.50"}},
                {"snapshot_type": "VALUATION", "data": {"forward_per": 28}},
            ]
        },
    )

    assert response.status_code == 200
    activated = cast(dict[str, Any], api_data(response))
    assert activated["status"] == "ACTIVE"
    assert activated["activated_at"].endswith("Z")
    assert activated["decided_at"] == activated["activated_at"]
    assert activated["review_triggers"][0]["status"] == "PENDING"
    assert activated["review_triggers"][0]["scheduled_at"] == "2026-08-21T00:00:00Z"

    detail_response = client.get(f"/api/v1/decision-logs/{created['id']}")
    detail = cast(dict[str, Any], api_data(detail_response))
    assert [item["snapshot_type"] for item in detail["snapshots"]] == [
        "PRICE",
        "VALUATION",
    ]
    assert all(item["captured_at"].endswith("Z") for item in detail["snapshots"])

    repeated = client.post(
        f"/api/v1/decision-logs/{created['id']}/activate",
    )
    assert repeated.status_code == 409
    assert api_error(repeated)["code"] == "DECISION_LOG_INVALID_STATE"


def test_list_uses_offset_pagination_and_keeps_stats(client: TestClient) -> None:
    set_current_user(1)
    first = create_decision_log(
        client,
        target={"type": "SYMBOL", "id": "AAPL"},
        decision_type="BUY_REVIEW",
    )
    second = create_decision_log(
        client,
        target={"type": "SYMBOL", "id": "MSFT"},
        decision_type="WATCH",
    )
    set_current_user(2, "other@example.com")
    create_decision_log(client, target={"type": "SYMBOL", "id": "TSLA"})
    set_current_user(1)

    list_response = client.get(
        "/api/v1/decision-logs",
        params={"page": 2, "size": 1, "sort": "-created_at"},
    )
    stats_response = client.get("/api/v1/decision-logs/stats")

    assert list_response.status_code == 200
    assert api_data(list_response) == [first]
    assert second["target_id"] == "MSFT"
    assert api_meta(list_response) == {"page": 2, "size": 1, "total": 2}
    assert api_data(stats_response)["decision_type_counts"] == {
        "BUY_REVIEW": 1,
        "WATCH": 1,
    }


def test_list_rejects_invalid_sort(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/decision-logs", params={"sort": "symbol"})

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"


def test_stats_keeps_recent_reviewed_scope_and_sort(client: TestClient) -> None:
    set_current_user(1)
    older = create_decision_log(
        client,
        target={"type": "SYMBOL", "id": "AAPL"},
        rationale="Older review",
    )
    newer = create_decision_log(
        client,
        target={"type": "SYMBOL", "id": "MSFT"},
        rationale="Newer review",
    )
    set_current_user(2, "other@example.com")
    other = create_decision_log(
        client,
        target={"type": "SYMBOL", "id": "TSLA"},
    )

    with TestingSessionLocal() as db:
        for decision_id, reviewed_at in (
            (older["id"], datetime(2026, 8, 1, tzinfo=UTC)),
            (newer["id"], datetime(2026, 8, 2, tzinfo=UTC)),
            (other["id"], datetime(2026, 8, 3, tzinfo=UTC)),
        ):
            decision_log = db.get(DecisionLog, decision_id)
            assert decision_log is not None
            decision_log.reviewed_at = reviewed_at
        db.commit()

    set_current_user(1)
    response = client.get("/api/v1/decision-logs/stats")

    assert response.status_code == 200
    recent_reviewed = api_data(response)["recent_reviewed"]
    assert [item["id"] for item in recent_reviewed] == [newer["id"], older["id"]]


def test_all_item_routes_enforce_ownership(client: TestClient) -> None:
    set_current_user(1)
    created = create_decision_log(client)
    set_current_user(2, "other@example.com")

    get_response = client.get(f"/api/v1/decision-logs/{created['id']}")
    patch_response = client.patch(
        f"/api/v1/decision-logs/{created['id']}",
        json={"rationale": "No access."},
    )
    activate_response = client.post(
        f"/api/v1/decision-logs/{created['id']}/activate",
        json={},
    )

    for response in (get_response, patch_response, activate_response):
        assert response.status_code == 403
        assert api_error(response)["code"] == "DECISION_LOG_FORBIDDEN"


def test_get_decision_log_returns_not_found(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/decision-logs/999")

    assert response.status_code == 404
    assert api_error(response)["code"] == "DECISION_LOG_NOT_FOUND"


def test_nested_enum_validation_uses_standard_error(client: TestClient) -> None:
    set_current_user(1)

    nested_response = client.post(
        "/api/v1/decision-logs",
        json=decision_payload(
            risks=[{"type": "VALUATION", "severity": "CRITICAL"}],
        ),
    )
    decision_type_response = client.post(
        "/api/v1/decision-logs",
        json=decision_payload(decision_type="INVALID"),
    )
    confidence_response = client.post(
        "/api/v1/decision-logs",
        json=decision_payload(confidence_level="VERY_HIGH"),
    )

    for response in (nested_response, decision_type_response, confidence_response):
        assert response.status_code == 422
        assert api_error(response)["code"] == "VALIDATION_ERROR"


def test_decision_log_response_uses_snake_case_fields(client: TestClient) -> None:
    set_current_user(1)

    data = create_decision_log(client)

    assert "target_type" in data
    assert "confidence_level" in data
    assert "review_triggers" in data
    assert "targetType" not in data
    assert "confidenceLevel" not in data
    assert "reviewTriggers" not in data
