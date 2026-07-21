from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.domains.decision_logs.model import DecisionLog
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user


def _create_decision(
    client: TestClient,
    *,
    activate: bool = True,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/decision-logs",
        json={
            "target": {"type": "SYMBOL", "id": "AAPL"},
            "decision_type": "BUY_REVIEW",
            "thesis": "서비스 매출이 계속 성장한다.",
            "rationale": "마진과 자사주 매입이 가설을 뒷받침한다.",
            "confidence_level": "HIGH",
            "evidence": [
                {
                    "type": "RESEARCH",
                    "id": "report-1",
                    "version": 2,
                    "title": "분기 리서치",
                    "summary": "서비스 마진이 개선됐다.",
                    "snapshot": {"margin": "0.32"},
                    "relationship": "SUPPORTING",
                }
            ],
            "risks": [
                {
                    "type": "VALUATION",
                    "description": "멀티플이 축소될 수 있다.",
                    "severity": "MEDIUM",
                }
            ],
            "review_triggers": [
                {
                    "type": "DATE",
                    "condition": {"reason": "earnings"},
                    "scheduled_at": "2026-08-21T00:00:00Z",
                }
            ],
        },
    )
    assert response.status_code == 201
    decision = cast(dict[str, Any], api_data(response))
    if activate:
        activate_response = client.post(
            f"/api/v1/decision-logs/{decision['id']}/activate",
            json={
                "snapshots": [
                    {"snapshot_type": "PRICE", "data": {"price": "225.50"}}
                ]
            },
        )
        assert activate_response.status_code == 200
    return decision


def test_revise_creates_linked_draft_with_copied_children_and_no_snapshots(
    client: TestClient,
) -> None:
    set_current_user(1)
    source = _create_decision(client)
    source_before = cast(
        dict[str, Any],
        api_data(client.get(f"/api/v1/decision-logs/{source['id']}")),
    )

    response = client.post(f"/api/v1/decision-logs/{source['id']}/revise")

    assert response.status_code == 200
    revised = cast(dict[str, Any], api_data(response))
    assert revised["id"] != source["id"]
    assert revised["status"] == "DRAFT"
    assert revised["superseded_by_id"] is None
    assert revised["decided_at"] is None
    assert revised["activated_at"] is None
    assert revised["reviewed_at"] is None
    assert revised["closed_at"] is None
    assert revised["snapshots"] == []

    for field in (
        "user_id",
        "target_type",
        "target_id",
        "symbol",
        "decision_type",
        "thesis",
        "rationale",
        "confidence_level",
    ):
        assert revised[field] == source_before[field]

    assert [{k: v for k, v in item.items() if k not in {"id", "created_at"}} for item in revised["evidence"]] == [
        {k: v for k, v in item.items() if k not in {"id", "created_at"}}
        for item in source_before["evidence"]
    ]
    assert [{k: v for k, v in item.items() if k not in {"id", "created_at"}} for item in revised["risks"]] == [
        {k: v for k, v in item.items() if k not in {"id", "created_at"}}
        for item in source_before["risks"]
    ]
    assert [{k: v for k, v in item.items() if k not in {"id", "created_at"}} for item in revised["review_triggers"]] == [
        {k: v for k, v in item.items() if k not in {"id", "created_at"}}
        for item in source_before["review_triggers"]
    ]
    assert {item["id"] for item in revised["evidence"]}.isdisjoint(
        item["id"] for item in source_before["evidence"]
    )
    assert {item["id"] for item in revised["risks"]}.isdisjoint(
        item["id"] for item in source_before["risks"]
    )
    assert {item["id"] for item in revised["review_triggers"]}.isdisjoint(
        item["id"] for item in source_before["review_triggers"]
    )

    source_after = cast(
        dict[str, Any],
        api_data(client.get(f"/api/v1/decision-logs/{source['id']}")),
    )
    assert source_after["superseded_by_id"] == revised["id"]
    for field in (
        "user_id",
        "target_type",
        "target_id",
        "symbol",
        "decision_type",
        "status",
        "thesis",
        "rationale",
        "confidence_level",
        "created_by",
        "decided_at",
        "activated_at",
        "reviewed_at",
        "closed_at",
        "evidence",
        "risks",
        "review_triggers",
        "snapshots",
    ):
        assert source_after[field] == source_before[field]


@pytest.mark.parametrize("status", ["DRAFT", "CANCELLED"])
def test_revise_rejects_invalid_source_status(
    client: TestClient,
    status: str,
) -> None:
    set_current_user(1)
    source = _create_decision(client, activate=False)
    if status == "CANCELLED":
        with TestingSessionLocal() as db:
            stored = db.get(DecisionLog, source["id"])
            assert stored is not None
            stored.status = status
            db.commit()

    response = client.post(f"/api/v1/decision-logs/{source['id']}/revise")

    assert response.status_code == 409
    assert api_error(response)["code"] == "DECISION_LOG_INVALID_STATE"


def test_revise_rejects_already_superseded_source(client: TestClient) -> None:
    set_current_user(1)
    source = _create_decision(client)
    first = client.post(f"/api/v1/decision-logs/{source['id']}/revise")
    assert first.status_code == 200

    response = client.post(f"/api/v1/decision-logs/{source['id']}/revise")

    assert response.status_code == 409
    assert api_error(response)["code"] == "DECISION_LOG_INVALID_STATE"


def test_revise_enforces_ownership_and_missing_source(client: TestClient) -> None:
    set_current_user(1)
    source = _create_decision(client)
    set_current_user(2, "other@example.com")

    forbidden = client.post(f"/api/v1/decision-logs/{source['id']}/revise")
    missing = client.post("/api/v1/decision-logs/999/revise")

    assert forbidden.status_code == 403
    assert api_error(forbidden)["code"] == "DECISION_LOG_FORBIDDEN"
    assert missing.status_code == 404
    assert api_error(missing)["code"] == "DECISION_LOG_NOT_FOUND"
