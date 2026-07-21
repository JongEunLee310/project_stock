from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi.testclient import TestClient

from app.domains.decision_logs.model import DecisionLog
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user


def _create_decision(
    client: TestClient,
    *,
    target_type: str = "SYMBOL",
    target_id: str = "AAPL",
    decision_type: str = "BUY_REVIEW",
    risks: tuple[str, ...] = (),
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/decision-logs",
        json={
            "target": {"type": target_type, "id": target_id},
            "decision_type": decision_type,
            "rationale": f"{target_id} 판단",
            "risks": [
                {"type": risk_type, "severity": "MEDIUM"}
                for risk_type in risks
            ],
        },
    )
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


def test_similar_ranks_target_type_and_overlapping_risks(
    client: TestClient,
) -> None:
    set_current_user(1)
    base = _create_decision(
        client,
        risks=("VALUATION", "MACRO"),
    )
    risk_only = _create_decision(
        client,
        target_id="TSLA",
        decision_type="SELL_REVIEW",
        risks=("VALUATION", "MACRO"),
    )
    same_type = _create_decision(
        client,
        target_id="MSFT",
        risks=("VALUATION",),
    )
    same_target = _create_decision(
        client,
        decision_type="WATCH",
    )
    strongest = _create_decision(
        client,
        risks=("VALUATION",),
    )

    response = client.get(f"/api/v1/decision-logs/{base['id']}/similar")

    assert response.status_code == 200
    items = cast(list[dict[str, Any]], api_data(response))
    assert [item["id"] for item in items] == [
        strongest["id"],
        same_target["id"],
        same_type["id"],
        risk_only["id"],
    ]
    assert items[0]["target"] == {
        "type": "SYMBOL",
        "id": "AAPL",
        "label": None,
    }
    assert items[0]["risks"] == ["VALUATION"]
    assert "evidence" not in items[0]


def test_similar_excludes_full_version_chain_and_other_users(
    client: TestClient,
) -> None:
    set_current_user(1)
    predecessor = _create_decision(client)
    base = _create_decision(client)
    successor = _create_decision(client)
    owned_candidate = _create_decision(client, target_id="MSFT")
    with TestingSessionLocal() as db:
        stored_predecessor = db.get(DecisionLog, predecessor["id"])
        stored_base = db.get(DecisionLog, base["id"])
        assert stored_predecessor is not None
        assert stored_base is not None
        stored_predecessor.superseded_by_id = base["id"]
        stored_base.superseded_by_id = successor["id"]
        db.commit()

    set_current_user(2, "other@example.com")
    _create_decision(client)
    set_current_user(1)

    response = client.get(f"/api/v1/decision-logs/{base['id']}/similar")

    assert response.status_code == 200
    assert [item["id"] for item in api_data(response)] == [owned_candidate["id"]]


def test_similar_uses_latest_tiebreaker_and_limit(client: TestClient) -> None:
    set_current_user(1)
    base = _create_decision(client)
    older = _create_decision(client, target_id="MSFT")
    newer = _create_decision(client, target_id="GOOG")
    newest = _create_decision(client, target_id="TSLA")
    with TestingSessionLocal() as db:
        now = datetime(2026, 7, 21, tzinfo=UTC)
        for decision_id, created_at in (
            (older["id"], now - timedelta(days=2)),
            (newer["id"], now - timedelta(days=1)),
            (newest["id"], now),
        ):
            decision = db.get(DecisionLog, decision_id)
            assert decision is not None
            decision.created_at = created_at
        db.commit()

    limited = client.get(
        f"/api/v1/decision-logs/{base['id']}/similar",
        params={"limit": 2},
    )
    invalid_low = client.get(
        f"/api/v1/decision-logs/{base['id']}/similar",
        params={"limit": 0},
    )
    invalid_high = client.get(
        f"/api/v1/decision-logs/{base['id']}/similar",
        params={"limit": 21},
    )

    assert limited.status_code == 200
    assert [item["id"] for item in api_data(limited)] == [
        newest["id"],
        newer["id"],
    ]
    assert invalid_low.status_code == 422
    assert invalid_high.status_code == 422


def test_similar_enforces_ownership_missing_and_empty_results(
    client: TestClient,
) -> None:
    set_current_user(1)
    base = _create_decision(client)
    empty = client.get(f"/api/v1/decision-logs/{base['id']}/similar")

    set_current_user(2, "other@example.com")
    forbidden = client.get(f"/api/v1/decision-logs/{base['id']}/similar")
    missing = client.get("/api/v1/decision-logs/999/similar")

    assert empty.status_code == 200
    assert api_data(empty) == []
    assert forbidden.status_code == 403
    assert api_error(forbidden)["code"] == "DECISION_LOG_FORBIDDEN"
    assert missing.status_code == 404
    assert api_error(missing)["code"] == "DECISION_LOG_NOT_FOUND"
