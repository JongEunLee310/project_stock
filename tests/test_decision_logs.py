from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.domains.decision_logs.model import DecisionLog, DecisionReviewTrigger
from app.domains.decision_logs.service import DecisionLogService
from app.main import app
from tests.conftest import (
    TestingSessionLocal,
    api_data,
    api_error,
    api_meta,
    engine,
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


def test_list_uses_offset_pagination(client: TestClient) -> None:
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
    assert list_response.status_code == 200
    assert [item["id"] for item in api_data(list_response)] == [first["id"]]
    assert second["target_id"] == "MSFT"
    assert api_meta(list_response) == {"page": 2, "size": 1, "total": 2}


def test_list_returns_lightweight_projection_and_truncates_summary(
    client: TestClient,
) -> None:
    set_current_user(1)
    created = create_decision_log(
        client,
        rationale="x" * 201,
        evidence=[{"type": "RESEARCH", "title": "Heavy nested evidence"}],
        risks=[
            {"type": "VALUATION", "severity": "HIGH"},
            {"type": "FOMO", "severity": "LOW"},
        ],
        review_triggers=[
            {
                "type": "DATE",
                "condition": {},
                "scheduled_at": "2026-08-03T00:00:00Z",
            },
            {
                "type": "DATE",
                "condition": {},
                "scheduled_at": "2026-08-01T00:00:00Z",
            },
        ],
    )

    response = client.get("/api/v1/decision-logs")

    assert response.status_code == 200
    item = api_data(response)[0]
    assert set(item) == {
        "id",
        "target",
        "decision_type",
        "summary",
        "risks",
        "confidence_level",
        "status",
        "review_at",
        "created_at",
    }
    assert item["id"] == created["id"]
    assert item["target"] == {"type": "SYMBOL", "id": "AAPL", "label": None}
    assert item["summary"] == "x" * 200
    assert item["risks"] == ["VALUATION", "FOMO"]
    assert item["review_at"] == "2026-08-01T00:00:00Z"
    assert "evidence" not in item
    assert "review_triggers" not in item


def test_list_filters_are_individually_and_jointly_applied(client: TestClient) -> None:
    set_current_user(1)
    apple = create_decision_log(
        client,
        target={"type": "SYMBOL", "id": "AAPL"},
        decision_type="BUY_REVIEW",
        risks=[{"type": "VALUATION", "severity": "HIGH"}],
        review_triggers=[
            {
                "type": "DATE",
                "condition": {},
                "scheduled_at": "2026-08-02T00:00:00Z",
            }
        ],
    )
    microsoft = create_decision_log(
        client,
        target={"type": "SYMBOL", "id": "MSFT"},
        decision_type="WATCH",
        risks=[{"type": "LIQUIDITY", "severity": "LOW"}],
        review_triggers=[
            {
                "type": "DATE",
                "condition": {},
                "scheduled_at": "2026-08-10T00:00:00Z",
            }
        ],
    )
    topic = create_decision_log(
        client,
        target={"type": "TOPIC", "id": "ai-capex"},
        decision_type="BUY_REVIEW",
        risks=[{"type": "VALUATION", "severity": "MEDIUM"}],
    )
    with TestingSessionLocal() as db:
        for decision_id in (apple["id"], topic["id"]):
            decision_log = db.get(DecisionLog, decision_id)
            assert decision_log is not None
            decision_log.status = "ACTIVE"
        db.commit()

    set_current_user(2, "other@example.com")
    create_decision_log(
        client,
        target={"type": "SYMBOL", "id": "AAPL"},
        decision_type="BUY_REVIEW",
        risks=[{"type": "VALUATION", "severity": "HIGH"}],
        review_triggers=[
            {
                "type": "DATE",
                "condition": {},
                "scheduled_at": "2026-08-01T00:00:00Z",
            }
        ],
    )
    set_current_user(1)

    cases = (
        ({"target_type": "TOPIC"}, {topic["id"]}),
        ({"symbol": "AAPL"}, {apple["id"]}),
        ({"decision_type": "BUY_REVIEW"}, {apple["id"], topic["id"]}),
        ({"status": "ACTIVE"}, {apple["id"], topic["id"]}),
        ({"risk_type": "LIQUIDITY"}, {microsoft["id"]}),
        ({"review_due_before": "2026-08-05T00:00:00Z"}, {apple["id"]}),
        (
            {
                "target_type": "SYMBOL",
                "symbol": "AAPL",
                "decision_type": "BUY_REVIEW",
                "status": "ACTIVE",
                "risk_type": "VALUATION",
                "review_due_before": "2026-08-05T00:00:00Z",
            },
            {apple["id"]},
        ),
    )
    for params, expected_ids in cases:
        response = client.get("/api/v1/decision-logs", params=params)
        assert response.status_code == 200
        assert {item["id"] for item in api_data(response)} == expected_ids
        assert api_meta(response)["total"] == len(expected_ids)


def test_list_rejects_invalid_enum_filters(client: TestClient) -> None:
    set_current_user(1)

    for params in (
        {"target_type": "INVALID"},
        {"decision_type": "INVALID"},
        {"status": "INVALID"},
    ):
        response = client.get("/api/v1/decision-logs", params=params)
        assert response.status_code == 422
        assert api_error(response)["code"] == "VALIDATION_ERROR"


def test_review_queue_returns_owned_due_dates_in_nearest_order(
    client: TestClient,
    monkeypatch: Any,
) -> None:
    now = datetime(2026, 8, 8, 12, tzinfo=UTC)
    monkeypatch.setattr(DecisionLogService, "_now", staticmethod(lambda: now))
    set_current_user(1)
    older = create_decision_log(
        client,
        target={"type": "SYMBOL", "id": "AAPL"},
        review_triggers=[
            {
                "type": "DATE",
                "condition": {},
                "scheduled_at": "2026-08-01T00:00:00Z",
            },
            {
                "type": "DATE",
                "condition": {},
                "scheduled_at": "2026-08-02T00:00:00Z",
            },
        ],
    )
    nearer = create_decision_log(
        client,
        target={"type": "SYMBOL", "id": "MSFT"},
        review_triggers=[
            {
                "type": "DATE",
                "condition": {},
                "scheduled_at": "2026-08-08T11:00:00Z",
            }
        ],
    )
    future = create_decision_log(
        client,
        target={"type": "SYMBOL", "id": "NVDA"},
        review_triggers=[
            {
                "type": "DATE",
                "condition": {},
                "scheduled_at": "2026-08-09T00:00:00Z",
            }
        ],
    )
    event_only = create_decision_log(
        client,
        target={"type": "TOPIC", "id": "rates"},
        review_triggers=[
            {
                "type": "EVENT",
                "condition": {},
                "scheduled_at": "2026-08-01T00:00:00Z",
            }
        ],
    )
    with TestingSessionLocal() as db:
        db.add(
            DecisionReviewTrigger(
                decision_id=event_only["id"],
                trigger_type="DATE",
                condition={},
                scheduled_at=now - timedelta(days=1),
                status="TRIGGERED",
            )
        )
        db.commit()

    set_current_user(2, "other@example.com")
    create_decision_log(
        client,
        review_triggers=[
            {
                "type": "DATE",
                "condition": {},
                "scheduled_at": "2026-08-08T10:00:00Z",
            }
        ],
    )
    set_current_user(1)

    response = client.get("/api/v1/decision-logs/review-queue")

    assert response.status_code == 200
    items = api_data(response)
    assert [item["id"] for item in items] == [older["id"], nearer["id"]]
    assert [item["review_at"] for item in items] == [
        "2026-08-01T00:00:00Z",
        "2026-08-08T11:00:00Z",
    ]
    assert api_meta(response) == {"page": 1, "size": 20, "total": 2}
    assert future["id"] not in {item["id"] for item in items}


def test_list_projection_uses_constant_query_count(client: TestClient) -> None:
    set_current_user(1)
    for symbol in ("AAPL", "MSFT", "NVDA"):
        create_decision_log(
            client,
            target={"type": "SYMBOL", "id": symbol},
            risks=[{"type": "VALUATION", "severity": "MEDIUM"}],
            review_triggers=[
                {
                    "type": "DATE",
                    "condition": {},
                    "scheduled_at": "2026-08-01T00:00:00Z",
                }
            ],
        )

    select_count = 0

    def count_selects(*args: Any) -> None:
        nonlocal select_count
        statement = str(args[2]).lstrip().upper()
        if statement.startswith("SELECT"):
            select_count += 1

    event.listen(engine, "before_cursor_execute", count_selects)
    try:
        response = client.get("/api/v1/decision-logs")
    finally:
        event.remove(engine, "before_cursor_execute", count_selects)

    assert response.status_code == 200
    assert len(api_data(response)) == 3
    assert select_count == 4


def test_list_rejects_invalid_sort(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/decision-logs", params={"sort": "symbol"})

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"


def test_overview_returns_empty_state_and_replaces_stats(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/decision-logs/overview")

    assert response.status_code == 200
    assert api_data(response) == {
        "total_count": 0,
        "created_this_week": 0,
        "review_due_count": 0,
        "active_count": 0,
        "decision_type_distribution": [],
        "as_of": api_data(response)["as_of"],
    }
    assert api_data(response)["as_of"].endswith("Z")
    assert "/api/v1/decision-logs/stats" not in app.openapi()["paths"]


def test_overview_aggregates_owned_decisions_at_boundaries(
    client: TestClient,
    monkeypatch: Any,
) -> None:
    now = datetime(2026, 8, 8, 12, tzinfo=UTC)
    monkeypatch.setattr(DecisionLogService, "_now", staticmethod(lambda: now))
    set_current_user(1)
    boundary = create_decision_log(
        client,
        target={"type": "SYMBOL", "id": "AAPL"},
        decision_type="BUY_REVIEW",
        review_triggers=[
            {
                "type": "DATE",
                "condition": {},
                "scheduled_at": "2026-08-08T11:00:00Z",
            }
        ],
    )
    recent = create_decision_log(
        client,
        target={"type": "SYMBOL", "id": "MSFT"},
        decision_type="WATCH",
        review_triggers=[
            {
                "type": "DATE",
                "condition": {},
                "scheduled_at": "2026-08-08T12:00:00Z",
            }
        ],
    )
    old = create_decision_log(
        client,
        target={"type": "TOPIC", "id": "ai-capex"},
        decision_type="WATCH",
    )
    set_current_user(2, "other@example.com")
    other = create_decision_log(
        client,
        target={"type": "SYMBOL", "id": "TSLA"},
        decision_type="SELL_REVIEW",
        review_triggers=[
            {
                "type": "DATE",
                "condition": {},
                "scheduled_at": "2026-08-01T00:00:00Z",
            }
        ],
    )

    with TestingSessionLocal() as db:
        for decision_id, created_at, status in (
            (boundary["id"], now - timedelta(days=7), "ACTIVE"),
            (recent["id"], now - timedelta(days=1), "REVIEW_DUE"),
            (old["id"], now - timedelta(days=7, microseconds=1), "DRAFT"),
            (other["id"], now, "ACTIVE"),
        ):
            decision_log = db.get(DecisionLog, decision_id)
            assert decision_log is not None
            decision_log.created_at = created_at
            decision_log.status = status
        db.add_all(
            [
                DecisionReviewTrigger(
                    decision_id=boundary["id"],
                    trigger_type="DATE",
                    condition={},
                    scheduled_at=now - timedelta(hours=2),
                    status="PENDING",
                ),
                DecisionReviewTrigger(
                    decision_id=old["id"],
                    trigger_type="EVENT",
                    condition={},
                    scheduled_at=now - timedelta(days=1),
                    status="PENDING",
                ),
                DecisionReviewTrigger(
                    decision_id=old["id"],
                    trigger_type="DATE",
                    condition={},
                    scheduled_at=now - timedelta(days=1),
                    status="TRIGGERED",
                ),
                DecisionReviewTrigger(
                    decision_id=old["id"],
                    trigger_type="DATE",
                    condition={},
                    scheduled_at=now + timedelta(days=1),
                    status="PENDING",
                ),
            ]
        )
        db.commit()

    set_current_user(1)
    response = client.get("/api/v1/decision-logs/overview")

    assert response.status_code == 200
    overview = api_data(response)
    assert overview["total_count"] == 3
    assert overview["created_this_week"] == 2
    assert overview["review_due_count"] == 2
    assert overview["active_count"] == 2
    assert overview["decision_type_distribution"] == [
        {"type": "WATCH", "count": 2, "share": 2 / 3},
        {"type": "BUY_REVIEW", "count": 1, "share": 1 / 3},
    ]
    assert sum(
        item["share"] for item in overview["decision_type_distribution"]
    ) == 1.0
    assert overview["as_of"] == "2026-08-08T12:00:00Z"


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
