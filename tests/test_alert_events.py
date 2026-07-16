from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.alert_events.model import AlertEvent
from app.domains.alert_rules.model import AlertRule
from tests.conftest import api_data, api_error, api_meta, set_current_user


def seed_alert_events(db: Session) -> list[AlertEvent]:
    now = datetime.now(UTC)
    rules = [
        AlertRule(
            user_id=user_id,
            name=f"rule-{index}",
            source="USER",
            template_type="NEWS_RISK_HIGH",
            target_type=target_type,
            target_id=target_id,
            condition={"metric": "NEWS_RISK", "operator": "GTE", "value": "HIGH"},
            severity=severity,
            channels=["APP"],
            enabled=True,
            cooldown_seconds=3600,
            delivery_policy="ONCE_PER_TRANSITION",
        )
        for index, (user_id, target_type, target_id, severity) in enumerate(
            [
                (1, "SYMBOL", "AAPL", "HIGH"),
                (1, "WATCHLIST", "7", "MEDIUM"),
                (1, "SYMBOL", "MSFT", "HIGH"),
                (2, "SYMBOL", "NVDA", "CRITICAL"),
            ]
        )
    ]
    db.add_all(rules)
    db.flush()
    events = [
        AlertEvent(
            rule_id=rules[0].id,
            user_id=1,
            target_type="SYMBOL",
            target_id="AAPL",
            title="Apple risk increased",
            message="News risk reached high.",
            severity="HIGH",
            triggered_value={"current": "HIGH", "threshold": "HIGH", "previous": "MEDIUM"},
            evidence=[{"kind": "NEWS", "headline": "Supply concern"}],
            dedup_key="owner-aapl-high",
            read_at=None,
            triggered_at=now,
        ),
        AlertEvent(
            rule_id=rules[1].id,
            user_id=1,
            target_type="WATCHLIST",
            target_id="7",
            title="Watchlist judgment changed",
            message="AI judgment changed.",
            severity="MEDIUM",
            triggered_value={"current": "HOLD", "previous": "BUY"},
            evidence=[{"kind": "SIGNAL", "signal_id": 10}],
            dedup_key="owner-watchlist-change",
            read_at=now - timedelta(minutes=30),
            triggered_at=now - timedelta(hours=1),
        ),
        AlertEvent(
            rule_id=rules[2].id,
            user_id=1,
            target_type="SYMBOL",
            target_id="MSFT",
            title="Older unread event",
            message="An older event.",
            severity="HIGH",
            triggered_value={"current": "HIGH"},
            evidence=[],
            dedup_key="owner-msft-high",
            read_at=None,
            triggered_at=now - timedelta(hours=2),
        ),
        AlertEvent(
            rule_id=rules[3].id,
            user_id=2,
            target_type="SYMBOL",
            target_id="NVDA",
            title="Other user's event",
            message="Private event.",
            severity="CRITICAL",
            triggered_value={"current": "CRITICAL"},
            evidence=[],
            dedup_key="other-nvda-critical",
            read_at=None,
            triggered_at=now + timedelta(minutes=1),
        ),
    ]
    db.add_all(events)
    db.commit()
    for event in events:
        db.refresh(event)
    return events


def test_list_filters_paginates_and_sorts_owner_events(
    client: TestClient,
    db: Session,
) -> None:
    events = seed_alert_events(db)
    set_current_user(1)

    response = client.get(
        "/api/v1/alert-events",
        params={
            "severity": "HIGH",
            "read": False,
            "target_type": "SYMBOL",
            "sort": "triggered_at",
            "page": 2,
            "size": 1,
        },
    )

    assert response.status_code == 200
    assert api_meta(response) == {"page": 2, "size": 1, "total": 2}
    items = cast(list[dict[str, Any]], api_data(response))
    assert [item["id"] for item in items] == [events[0].id]
    assert items[0]["read_at"] is None
    assert "triggered_value" not in items[0]
    assert "evidence" not in items[0]


def test_list_defaults_to_newest_first(client: TestClient, db: Session) -> None:
    events = seed_alert_events(db)
    set_current_user(1)

    response = client.get("/api/v1/alert-events")

    assert response.status_code == 200
    assert [item["id"] for item in api_data(response)] == [
        events[0].id,
        events[1].id,
        events[2].id,
    ]


def test_detail_includes_triggered_value_and_evidence(
    client: TestClient,
    db: Session,
) -> None:
    event = seed_alert_events(db)[0]
    set_current_user(1)

    response = client.get(f"/api/v1/alert-events/{event.id}")

    assert response.status_code == 200
    detail = cast(dict[str, Any], api_data(response))
    assert detail["triggered_value"] == {
        "current": "HIGH",
        "threshold": "HIGH",
        "previous": "MEDIUM",
    }
    assert detail["evidence"] == [{"kind": "NEWS", "headline": "Supply concern"}]


def test_single_and_bulk_read_set_read_at(client: TestClient, db: Session) -> None:
    events = seed_alert_events(db)
    set_current_user(1)

    single_response = client.post(f"/api/v1/alert-events/{events[0].id}/read")
    bulk_response = client.post(
        "/api/v1/alert-events/read",
        json={"alert_ids": [events[1].id, events[2].id]},
    )

    assert single_response.status_code == 200
    assert api_data(single_response)["read_at"] is not None
    assert bulk_response.status_code == 200
    assert [item["id"] for item in api_data(bulk_response)] == [
        events[1].id,
        events[2].id,
    ]
    assert all(item["read_at"] is not None for item in api_data(bulk_response))


def test_detail_and_read_distinguish_forbidden_from_not_found(
    client: TestClient,
    db: Session,
) -> None:
    other_event = seed_alert_events(db)[3]
    set_current_user(1)

    for response in (
        client.get(f"/api/v1/alert-events/{other_event.id}"),
        client.post(f"/api/v1/alert-events/{other_event.id}/read"),
        client.post("/api/v1/alert-events/read", json={"alert_ids": [other_event.id]}),
    ):
        assert response.status_code == 403
        assert api_error(response)["code"] == "ALERT_EVENT_FORBIDDEN"

    for response in (
        client.get("/api/v1/alert-events/999999"),
        client.post("/api/v1/alert-events/999999/read"),
        client.post("/api/v1/alert-events/read", json={"alert_ids": [999999]}),
    ):
        assert response.status_code == 404
        assert api_error(response)["code"] == "ALERT_EVENT_NOT_FOUND"
