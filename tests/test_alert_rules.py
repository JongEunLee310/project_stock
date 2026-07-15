from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.alert_events.model import AlertEvent
from app.domains.alert_rules.model import AlertRule
from app.domains.alert_rules.service import validate_condition
from app.core.exceptions import AppException
from tests.conftest import api_data, api_error, api_meta, set_current_user


def create_rule(client: TestClient, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "template_type": "NEWS_RISK_HIGH",
        "target_id": "AAPL",
    }
    payload.update(overrides)
    response = client.post("/api/v1/alert-rules", json=payload)
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


def test_template_catalog_matches_design(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/alert-rules/templates")

    assert response.status_code == 200
    templates = cast(list[dict[str, Any]], api_data(response))
    assert [item["template_type"] for item in templates] == [
        "HOLDING_NEWS_RISK",
        "WATCHLIST_AI_JUDGMENT",
        "EARNINGS_D3",
        "POSITION_WEIGHT_OVER",
        "NEWS_RISK_HIGH",
        "TOPIC_IMPACT_SURGE",
    ]
    assert [item["label"] for item in templates] == [
        "보유 종목 위험 증가",
        "관심 종목 AI 판단 변경",
        "실적 발표 3일 전",
        "단일 종목 비중 초과",
        "뉴스 위험도 High 이상",
        "토픽 영향도 급등",
    ]
    assert templates[-1]["is_active"] is False
    assert all(item["channels"] == ["APP"] for item in templates)
    assert templates[0]["target_type"] == "PORTFOLIO"
    assert templates[1]["condition"] == {
        "metric": "AI_JUDGMENT_CHANGED",
        "operator": "CHANGED",
        "value": None,
    }
    assert templates[2]["condition"] == {
        "metric": "EARNINGS_DATE",
        "operator": "LTE",
        "value": 3,
    }
    assert templates[3]["condition"] == {
        "metric": "POSITION_WEIGHT",
        "operator": "GTE",
        "value": 0.15,
    }


@pytest.mark.parametrize(
    "condition",
    [
        {"metric": "NEWS_RISK", "operator": "GTE", "value": "HIGH"},
        {"metric": "PRICE_CHANGE_1D", "operator": "LTE", "value": -3.0},
        {"metric": "SIGNAL_CHANGED", "operator": "CHANGED", "value": None},
        {"metric": "THEME_HEAT", "operator": "EQ", "value": "OVERHEATED"},
        {"metric": "POSITION_WEIGHT", "operator": "GTE", "value": 0.15},
        {"metric": "EARNINGS_DATE", "operator": "LTE", "value": 3},
        {
            "all": [
                {"metric": "NEWS_RISK", "operator": "GTE", "value": "HIGH"},
                {"metric": "POSITION_WEIGHT", "operator": "GTE", "value": 0.1},
            ]
        },
    ],
)
def test_validate_condition_accepts_supported_combinations(
    condition: dict[str, Any],
) -> None:
    validate_condition(condition)


@pytest.mark.parametrize(
    "condition",
    [
        {"metric": "UNKNOWN", "operator": "EQ", "value": 1},
        {"metric": "NEWS_RISK", "operator": "CHANGED", "value": "HIGH"},
        {"metric": "NEWS_RISK", "operator": "GTE", "value": "CRITICAL"},
        {"metric": "SIGNAL_CHANGED", "operator": "EQ", "value": None},
        {"metric": "POSITION_WEIGHT", "operator": "GTE", "value": 1.1},
        {"metric": "PRICE_CHANGE_1D", "operator": "GTE", "value": "NaN"},
        {"metric": "EARNINGS_DATE", "operator": "LTE", "value": -1},
        {"metric": "TOPIC_IMPACT_SCORE", "operator": "GTE", "value": 80},
        {"any": [{"metric": "NEWS_RISK", "operator": "EQ", "value": "HIGH"}]},
        {"all": []},
        {"all": [{"metric": "NEWS_RISK", "operator": "EQ", "value": "HIGH"}], "x": 1},
    ],
)
def test_validate_condition_rejects_unsupported_combinations(
    condition: dict[str, Any],
) -> None:
    with pytest.raises(AppException) as exc_info:
        validate_condition(condition)
    assert exc_info.value.status_code == 422
    assert exc_info.value.error_code.value == "VALIDATION_ERROR"


def test_rule_crud_pause_resume_and_filters(client: TestClient) -> None:
    set_current_user(1)
    rule = create_rule(client)

    assert rule["name"] == "뉴스 위험도 High 이상"
    assert rule["source"] == "USER"
    assert rule["target_type"] == "SYMBOL"
    assert rule["target_id"] == "AAPL"
    assert rule["condition"] == {
        "metric": "NEWS_RISK",
        "operator": "GTE",
        "value": "HIGH",
    }
    assert rule["enabled"] is True
    assert rule["status"] == "ACTIVE"

    patch_response = client.patch(
        f"/api/v1/alert-rules/{rule['id']}",
        json={
            "name": "Apple news risk",
            "severity": "CRITICAL",
            "channels": ["APP", "EMAIL"],
            "condition": {"metric": "NEWS_RISK", "operator": "EQ", "value": "HIGH"},
        },
    )
    assert patch_response.status_code == 200
    updated = cast(dict[str, Any], api_data(patch_response))
    assert updated["name"] == "Apple news risk"
    assert updated["severity"] == "CRITICAL"
    assert updated["channels"] == ["APP", "EMAIL"]

    pause_response = client.post(f"/api/v1/alert-rules/{rule['id']}/pause")
    assert pause_response.status_code == 200
    assert api_data(pause_response)["status"] == "PAUSED"

    paused_list = client.get("/api/v1/alert-rules?status=PAUSED&target_type=SYMBOL")
    assert paused_list.status_code == 200
    assert [item["id"] for item in api_data(paused_list)] == [rule["id"]]
    assert api_meta(paused_list) == {"page": 1, "size": 20, "total": 1}

    resume_response = client.post(f"/api/v1/alert-rules/{rule['id']}/resume")
    assert resume_response.status_code == 200
    assert api_data(resume_response)["status"] == "ACTIVE"

    delete_response = client.delete(f"/api/v1/alert-rules/{rule['id']}")
    assert delete_response.status_code == 204
    list_response = client.get("/api/v1/alert-rules")
    assert api_data(list_response) == []


def test_create_rejects_invalid_condition_and_inactive_template(client: TestClient) -> None:
    set_current_user(1)

    invalid_condition = client.post(
        "/api/v1/alert-rules",
        json={
            "template_type": "NEWS_RISK_HIGH",
            "target_id": "AAPL",
            "condition": {"metric": "NEWS_RISK", "operator": "CHANGED", "value": "HIGH"},
        },
    )
    inactive_template = client.post(
        "/api/v1/alert-rules",
        json={"template_type": "TOPIC_IMPACT_SURGE", "target_id": "ai"},
    )

    assert invalid_condition.status_code == 422
    assert api_error(invalid_condition)["code"] == "VALIDATION_ERROR"
    assert inactive_template.status_code == 422
    assert api_error(inactive_template)["code"] == "VALIDATION_ERROR"


def test_update_rejects_null_for_non_nullable_fields(client: TestClient) -> None:
    set_current_user(1)
    rule = create_rule(client)

    response = client.patch(
        f"/api/v1/alert-rules/{rule['id']}",
        json={"name": None},
    )

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"


def test_rule_mutations_block_other_user(client: TestClient) -> None:
    set_current_user(1)
    rule = create_rule(client)
    set_current_user(2, "other@example.com")

    for response in (
        client.patch(f"/api/v1/alert-rules/{rule['id']}", json={"name": "Denied"}),
        client.post(f"/api/v1/alert-rules/{rule['id']}/pause"),
        client.post(f"/api/v1/alert-rules/{rule['id']}/resume"),
        client.delete(f"/api/v1/alert-rules/{rule['id']}"),
    ):
        assert response.status_code == 403
        assert api_error(response)["code"] == "ALERT_RULE_FORBIDDEN"


def test_delete_system_rule_is_forbidden(client: TestClient, db: Session) -> None:
    rule = AlertRule(
        user_id=1,
        name="System rule",
        source="SYSTEM",
        template_type="NEWS_RISK_HIGH",
        target_type="SYMBOL",
        target_id="AAPL",
        condition={"metric": "NEWS_RISK", "operator": "GTE", "value": "HIGH"},
        severity="HIGH",
        channels=["APP"],
        enabled=True,
        cooldown_seconds=3600,
        delivery_policy="ONCE_PER_TRANSITION",
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    set_current_user(1)

    response = client.delete(f"/api/v1/alert-rules/{rule.id}")

    assert response.status_code == 403
    assert api_error(response)["code"] == "ALERT_RULE_FORBIDDEN"


def test_alert_overview_counts_are_owner_scoped(client: TestClient, db: Session) -> None:
    now = datetime.now(UTC)
    rules = [
        AlertRule(
            user_id=user_id,
            name=f"rule-{index}",
            source="USER",
            template_type="NEWS_RISK_HIGH",
            target_type="SYMBOL",
            target_id="AAPL",
            condition={"metric": "NEWS_RISK", "operator": "GTE", "value": "HIGH"},
            severity="HIGH",
            channels=["APP"],
            enabled=enabled,
            cooldown_seconds=3600,
            delivery_policy="ONCE_PER_TRANSITION",
        )
        for index, (user_id, enabled) in enumerate([(1, True), (1, False), (2, True)])
    ]
    db.add_all(rules)
    db.flush()
    db.add_all(
        [
            AlertEvent(
                rule_id=rules[0].id,
                user_id=1,
                target_type="SYMBOL",
                target_id="AAPL",
                title="high unread today",
                message="message",
                severity="HIGH",
                triggered_value={},
                evidence=[],
                dedup_key="today-high",
                read_at=None,
                triggered_at=now,
            ),
            AlertEvent(
                rule_id=rules[0].id,
                user_id=1,
                target_type="SYMBOL",
                target_id="AAPL",
                title="low read today",
                message="message",
                severity="LOW",
                triggered_value={},
                evidence=[],
                dedup_key="today-low",
                read_at=now,
                triggered_at=now,
            ),
            AlertEvent(
                rule_id=rules[0].id,
                user_id=1,
                target_type="SYMBOL",
                target_id="AAPL",
                title="critical unread old",
                message="message",
                severity="CRITICAL",
                triggered_value={},
                evidence=[],
                dedup_key="old-critical",
                read_at=None,
                triggered_at=now - timedelta(days=2),
            ),
            AlertEvent(
                rule_id=rules[2].id,
                user_id=2,
                target_type="SYMBOL",
                target_id="MSFT",
                title="other user",
                message="message",
                severity="HIGH",
                triggered_value={},
                evidence=[],
                dedup_key="other",
                read_at=None,
                triggered_at=now,
            ),
        ]
    )
    db.commit()
    set_current_user(1)

    response = client.get("/api/v1/alerts/overview")

    assert response.status_code == 200
    overview = cast(dict[str, Any], api_data(response))
    assert overview == {
        "active_rule_count": 1,
        "triggered_today_count": 2,
        "high_severity_count": 2,
        "paused_rule_count": 1,
        "unread_count": 2,
        "as_of": overview["as_of"],
    }
    assert overview["as_of"].endswith("Z")
