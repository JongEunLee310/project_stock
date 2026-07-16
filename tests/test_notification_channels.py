from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.domains.notification_channels.model import NotificationChannel
from app.domains.notification_channels.service import NotificationChannelService
from tests.conftest import api_data, api_error, set_current_user


def test_list_lazy_creates_default_app_channel(client: TestClient, db: Session) -> None:
    set_current_user(1)

    first_response = client.get("/api/v1/notification-channels")
    second_response = client.get("/api/v1/notification-channels")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_items = cast(list[dict[str, Any]], api_data(first_response))
    second_items = cast(list[dict[str, Any]], api_data(second_response))
    assert first_items == second_items
    assert first_items == [
        {
            "id": first_items[0]["id"],
            "user_id": 1,
            "channel_type": "APP",
            "configuration": {},
            "enabled": True,
            "verified_at": None,
        }
    ]


def test_list_channels_is_owner_scoped(client: TestClient, db: Session) -> None:
    db.add_all(
        [
            NotificationChannel(
                user_id=1,
                channel_type="EMAIL",
                configuration={"email": "owner@example.com"},
                enabled=True,
                verified_at=None,
            ),
            NotificationChannel(
                user_id=2,
                channel_type="EMAIL",
                configuration={"email": "other@example.com"},
                enabled=True,
                verified_at=None,
            ),
        ]
    )
    db.commit()
    set_current_user(1)

    response = client.get("/api/v1/notification-channels")

    assert response.status_code == 200
    items = cast(list[dict[str, Any]], api_data(response))
    assert {item["channel_type"] for item in items} == {"APP", "EMAIL"}
    assert {item["user_id"] for item in items} == {1}


def test_create_app_channel_and_reject_duplicate(client: TestClient) -> None:
    set_current_user(1)

    created_response = client.post(
        "/api/v1/notification-channels",
        json={"channel_type": "APP"},
    )
    duplicate_response = client.post(
        "/api/v1/notification-channels",
        json={"channel_type": "APP"},
    )

    assert created_response.status_code == 201
    created = cast(dict[str, Any], api_data(created_response))
    assert created["channel_type"] == "APP"
    assert created["configuration"] == {}
    assert created["verified_at"] is None
    assert duplicate_response.status_code == 422
    assert api_error(duplicate_response)["code"] == "VALIDATION_ERROR"


def test_create_email_placeholder(client: TestClient) -> None:
    set_current_user(1)

    response = client.post(
        "/api/v1/notification-channels",
        json={
            "channel_type": "EMAIL",
            "configuration": {"email": "notify@example.com"},
        },
    )

    assert response.status_code == 201
    created = cast(dict[str, Any], api_data(response))
    assert created["configuration"] == {"email": "notify@example.com"}
    assert created["enabled"] is True
    assert created["verified_at"] is None


@pytest.mark.parametrize(
    "configuration",
    [{}, {"email": "invalid"}, {"email": "valid@example.com", "extra": True}],
)
def test_create_email_rejects_invalid_configuration(
    client: TestClient,
    configuration: dict[str, Any],
) -> None:
    set_current_user(1)

    response = client.post(
        "/api/v1/notification-channels",
        json={"channel_type": "EMAIL", "configuration": configuration},
    )

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("channel_type", ["DISCORD", "SLACK"])
def test_create_rejects_deferred_channels(
    client: TestClient,
    channel_type: str,
) -> None:
    set_current_user(1)

    response = client.post(
        "/api/v1/notification-channels",
        json={"channel_type": channel_type, "configuration": {}},
    )

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"


def test_get_channel_reports_not_found_and_forbidden(db: Session) -> None:
    channel = NotificationChannel(
        user_id=2,
        channel_type="APP",
        configuration={},
        enabled=True,
        verified_at=None,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    service = NotificationChannelService(db)

    with pytest.raises(AppException) as forbidden:
        service.get_channel(channel.id, user_id=1)
    assert forbidden.value.status_code == 403
    assert forbidden.value.error_code.value == "NOTIFICATION_CHANNEL_FORBIDDEN"

    with pytest.raises(AppException) as not_found:
        service.get_channel(999999, user_id=1)
    assert not_found.value.status_code == 404
    assert not_found.value.error_code.value == "NOTIFICATION_CHANNEL_NOT_FOUND"
