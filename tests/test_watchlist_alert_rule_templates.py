from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.domains.watchlists.alert_rule_service import WatchlistAlertRuleService
from app.domains.watchlists.repository import WatchlistRepository
from app.domains.watchlists.schema import (
    WatchlistAlertRuleTemplateApply,
    WatchlistAlertRuleTemplateBulkRequest,
)
from app.domains.watchlists.types import WatchlistAlertTemplateType
from tests.conftest import api_data, api_error, set_current_user


# Enum values are sourced from app/domains/watchlists/types.py.
TEMPLATE_TYPES = [
    WatchlistAlertTemplateType.PRICE_SPIKE,
    WatchlistAlertTemplateType.NEWS_RISK_HIGH,
    WatchlistAlertTemplateType.AI_JUDGMENT_CHANGE,
    WatchlistAlertTemplateType.THEME_OVERHEAT,
]


def create_watchlist(db: Session, user_id: int = 1, name: str = "Core") -> int:
    return WatchlistRepository(db).create(user_id=user_id, name=name).id


def bulk_request(
    templates: list[tuple[WatchlistAlertTemplateType, bool]],
) -> WatchlistAlertRuleTemplateBulkRequest:
    return WatchlistAlertRuleTemplateBulkRequest(
        templates=[
            WatchlistAlertRuleTemplateApply(
                template_type=template_type.value,
                is_active=is_active,
            )
            for template_type, is_active in templates
        ]
    )


def status_by_type(items: list[Any]) -> dict[str, bool]:
    return {item.template_type: item.is_active for item in items}


def api_status_by_type(items: list[dict[str, Any]]) -> dict[str, bool]:
    return {item["template_type"]: item["is_active"] for item in items}


def test_get_template_statuses_returns_four_inactive_defaults(db: Session) -> None:
    watchlist_id = create_watchlist(db)

    result = WatchlistAlertRuleService(db).get_template_statuses(watchlist_id, user_id=1)

    assert [item.template_type for item in result] == [
        template_type.value for template_type in TEMPLATE_TYPES
    ]
    assert status_by_type(result) == {
        template_type.value: False for template_type in TEMPLATE_TYPES
    }


def test_get_template_statuses_marks_only_existing_active_rules(
    db: Session,
) -> None:
    watchlist_id = create_watchlist(db)
    service = WatchlistAlertRuleService(db)
    service.apply_templates(
        watchlist_id,
        user_id=1,
        data=bulk_request([(WatchlistAlertTemplateType.NEWS_RISK_HIGH, True)]),
    )

    result = service.get_template_statuses(watchlist_id, user_id=1)

    assert status_by_type(result) == {
        WatchlistAlertTemplateType.PRICE_SPIKE.value: False,
        WatchlistAlertTemplateType.NEWS_RISK_HIGH.value: True,
        WatchlistAlertTemplateType.AI_JUDGMENT_CHANGE.value: False,
        WatchlistAlertTemplateType.THEME_OVERHEAT.value: False,
    }


def test_apply_templates_upserts_single_template_and_keeps_defaults(
    db: Session,
) -> None:
    watchlist_id = create_watchlist(db)

    result = WatchlistAlertRuleService(db).apply_templates(
        watchlist_id,
        user_id=1,
        data=bulk_request([(WatchlistAlertTemplateType.PRICE_SPIKE, True)]),
    )

    assert status_by_type(result) == {
        WatchlistAlertTemplateType.PRICE_SPIKE.value: True,
        WatchlistAlertTemplateType.NEWS_RISK_HIGH.value: False,
        WatchlistAlertTemplateType.AI_JUDGMENT_CHANGE.value: False,
        WatchlistAlertTemplateType.THEME_OVERHEAT.value: False,
    }


def test_apply_templates_upserts_all_templates_with_mixed_values(
    db: Session,
) -> None:
    watchlist_id = create_watchlist(db)

    result = WatchlistAlertRuleService(db).apply_templates(
        watchlist_id,
        user_id=1,
        data=bulk_request(
            [
                (WatchlistAlertTemplateType.PRICE_SPIKE, True),
                (WatchlistAlertTemplateType.NEWS_RISK_HIGH, False),
                (WatchlistAlertTemplateType.AI_JUDGMENT_CHANGE, True),
                (WatchlistAlertTemplateType.THEME_OVERHEAT, False),
            ]
        ),
    )

    assert status_by_type(result) == {
        WatchlistAlertTemplateType.PRICE_SPIKE.value: True,
        WatchlistAlertTemplateType.NEWS_RISK_HIGH.value: False,
        WatchlistAlertTemplateType.AI_JUDGMENT_CHANGE.value: True,
        WatchlistAlertTemplateType.THEME_OVERHEAT.value: False,
    }


def test_apply_templates_updates_duplicate_template_without_unique_violation(
    db: Session,
) -> None:
    watchlist_id = create_watchlist(db)
    service = WatchlistAlertRuleService(db)
    service.apply_templates(
        watchlist_id,
        user_id=1,
        data=bulk_request([(WatchlistAlertTemplateType.THEME_OVERHEAT, True)]),
    )

    result = service.apply_templates(
        watchlist_id,
        user_id=1,
        data=bulk_request([(WatchlistAlertTemplateType.THEME_OVERHEAT, False)]),
    )

    assert status_by_type(result)[WatchlistAlertTemplateType.THEME_OVERHEAT.value] is False


def test_apply_templates_rejects_invalid_template_type(db: Session) -> None:
    watchlist_id = create_watchlist(db)

    try:
        WatchlistAlertRuleService(db).apply_templates(
            watchlist_id,
            user_id=1,
            data=WatchlistAlertRuleTemplateBulkRequest(
                templates=[
                    WatchlistAlertRuleTemplateApply(
                        template_type="UNKNOWN",
                        is_active=True,
                    )
                ]
            ),
        )
    except AppException as exc:
        assert exc.status_code == 422
        assert exc.error_code.value == "VALIDATION_ERROR"
    else:
        raise AssertionError("Expected invalid template type to raise AppException")


def test_apply_templates_validates_all_templates_before_upsert(db: Session) -> None:
    watchlist_id = create_watchlist(db)
    service = WatchlistAlertRuleService(db)

    try:
        service.apply_templates(
            watchlist_id,
            user_id=1,
            data=WatchlistAlertRuleTemplateBulkRequest(
                templates=[
                    WatchlistAlertRuleTemplateApply(
                        template_type=WatchlistAlertTemplateType.PRICE_SPIKE.value,
                        is_active=True,
                    ),
                    WatchlistAlertRuleTemplateApply(
                        template_type="UNKNOWN",
                        is_active=True,
                    ),
                ]
            ),
        )
    except AppException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("Expected invalid template type to raise AppException")

    result = service.get_template_statuses(watchlist_id, user_id=1)
    assert status_by_type(result) == {
        template_type.value: False for template_type in TEMPLATE_TYPES
    }


def test_get_template_statuses_rejects_forbidden_watchlist(db: Session) -> None:
    watchlist_id = create_watchlist(db, user_id=2)

    try:
        WatchlistAlertRuleService(db).get_template_statuses(watchlist_id, user_id=1)
    except AppException as exc:
        assert exc.status_code == 403
        assert exc.error_code.value == "WATCHLIST_FORBIDDEN"
    else:
        raise AssertionError("Expected forbidden watchlist to raise AppException")


def test_get_template_statuses_rejects_missing_watchlist(db: Session) -> None:
    try:
        WatchlistAlertRuleService(db).get_template_statuses(999, user_id=1)
    except AppException as exc:
        assert exc.status_code == 404
        assert exc.error_code.value == "WATCHLIST_NOT_FOUND"
    else:
        raise AssertionError("Expected missing watchlist to raise AppException")


def test_get_alert_rule_templates_endpoint_returns_enveloped_statuses(
    client: TestClient,
) -> None:
    set_current_user(1)
    create_response = client.post("/api/v1/watchlists", json={"name": "Core"})
    assert create_response.status_code == 201
    watchlist = cast(dict[str, Any], api_data(create_response))

    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/alert-rule-templates"
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert [item["template_type"] for item in data] == [
        template_type.value for template_type in TEMPLATE_TYPES
    ]
    assert all(item["is_active"] is False for item in data)
    assert all("label" in item for item in data)
    assert all("condition_description" in item for item in data)


def test_put_alert_rule_templates_endpoint_upserts_and_returns_all_statuses(
    client: TestClient,
) -> None:
    set_current_user(1)
    create_response = client.post("/api/v1/watchlists", json={"name": "Core"})
    assert create_response.status_code == 201
    watchlist = cast(dict[str, Any], api_data(create_response))

    response = client.put(
        f"/api/v1/watchlists/{watchlist['id']}/alert-rule-templates",
        json={
            "templates": [
                {
                    "template_type": WatchlistAlertTemplateType.PRICE_SPIKE.value,
                    "is_active": True,
                },
                {
                    "template_type": WatchlistAlertTemplateType.AI_JUDGMENT_CHANGE.value,
                    "is_active": True,
                },
            ]
        },
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert api_status_by_type(data) == {
        WatchlistAlertTemplateType.PRICE_SPIKE.value: True,
        WatchlistAlertTemplateType.NEWS_RISK_HIGH.value: False,
        WatchlistAlertTemplateType.AI_JUDGMENT_CHANGE.value: True,
        WatchlistAlertTemplateType.THEME_OVERHEAT.value: False,
    }


def test_put_alert_rule_templates_endpoint_rejects_invalid_template_type(
    client: TestClient,
) -> None:
    set_current_user(1)
    create_response = client.post("/api/v1/watchlists", json={"name": "Core"})
    assert create_response.status_code == 201
    watchlist = cast(dict[str, Any], api_data(create_response))

    response = client.put(
        f"/api/v1/watchlists/{watchlist['id']}/alert-rule-templates",
        json={"templates": [{"template_type": "UNKNOWN", "is_active": True}]},
    )

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"
