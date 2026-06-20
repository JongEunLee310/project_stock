from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.alert_candidates.schema import AlertCandidateCreate
from app.domains.alert_candidates.service import AlertCandidateService
from app.domains.alert_candidates.types import (
    AlertCandidateStatus,
    AlertCandidateType,
    AlertImportance,
)
from tests.conftest import (
    TestingSessionLocal,
    api_data,
    api_error,
    api_meta,
    set_current_user,
)


def create_alert_candidate_for_user(
    user_id: int,
    candidate_type: AlertCandidateType = AlertCandidateType.NEWS_SURGE,
    importance: AlertImportance = AlertImportance.MEDIUM,
    title: str = "News volume increased",
    asset_id: int | None = None,
) -> dict[str, Any]:
    db = TestingSessionLocal()
    try:
        candidate = AlertCandidateService(db).create_candidate(
            AlertCandidateCreate(
                user_id=user_id,
                candidate_type=candidate_type,
                importance=importance,
                title=title,
                message="Review before sending a notification.",
                asset_id=asset_id,
                evidence={"source": "test"},
            )
        )
        return {
            "id": candidate.id,
            "user_id": candidate.user_id,
            "candidate_type": candidate.candidate_type,
            "importance": candidate.importance,
            "status": candidate.status,
            "title": candidate.title,
        }
    finally:
        db.close()


def test_alert_candidate_service_can_create_all_candidate_types(
    db: Session,
) -> None:
    service = AlertCandidateService(db)

    created_types = {
        service.create_candidate(
            AlertCandidateCreate(
                user_id=1,
                candidate_type=candidate_type,
                importance=AlertImportance.LOW,
                title=f"{candidate_type.value} candidate",
            )
        ).candidate_type
        for candidate_type in AlertCandidateType
    }

    assert created_types == {
        candidate_type.value for candidate_type in AlertCandidateType
    }
    assert len(created_types) == 5


def test_list_alert_candidates_returns_only_current_users_candidates(
    client: TestClient,
) -> None:
    owner_candidate = create_alert_candidate_for_user(1, title="Owner candidate")
    create_alert_candidate_for_user(2, title="Other candidate")
    set_current_user(1)

    response = client.get("/api/v1/alert-candidates")

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert [item["id"] for item in data] == [owner_candidate["id"]]
    assert data[0]["user_id"] == 1
    assert data[0]["message"] == "Review before sending a notification."
    assert data[0]["evidence"] == {"source": "test"}
    assert api_meta(response) == {"page": 1, "size": 20, "total": 1}


def test_list_alert_candidates_uses_page_and_size(client: TestClient) -> None:
    create_alert_candidate_for_user(1, title="First candidate")
    second_candidate = create_alert_candidate_for_user(1, title="Second candidate")
    set_current_user(1)

    response = client.get("/api/v1/alert-candidates", params={"page": 1, "size": 1})

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert [item["id"] for item in data] == [second_candidate["id"]]
    assert api_meta(response) == {"page": 1, "size": 1, "total": 2}


def test_list_alert_candidates_supports_sort_values(client: TestClient) -> None:
    first_candidate = create_alert_candidate_for_user(1, title="First candidate")
    second_candidate = create_alert_candidate_for_user(1, title="Second candidate")
    set_current_user(1)

    response = client.get("/api/v1/alert-candidates", params={"sort": "id"})

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert [item["id"] for item in data] == [
        first_candidate["id"],
        second_candidate["id"],
    ]


def test_list_alert_candidates_rejects_invalid_sort(client: TestClient) -> None:
    set_current_user(1)

    response = client.get(
        "/api/v1/alert-candidates",
        params={"sort": "importance"},
    )

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"


def test_list_alert_candidates_filters_by_type_importance_and_status(
    client: TestClient,
) -> None:
    matched = create_alert_candidate_for_user(
        1,
        candidate_type=AlertCandidateType.PORTFOLIO_CONCENTRATION,
        importance=AlertImportance.HIGH,
        title="Portfolio concentration exceeded",
    )
    create_alert_candidate_for_user(
        1,
        candidate_type=AlertCandidateType.PRICE_MOVEMENT,
        importance=AlertImportance.HIGH,
        title="Price moved sharply",
    )
    read_candidate = create_alert_candidate_for_user(
        1,
        candidate_type=AlertCandidateType.PORTFOLIO_CONCENTRATION,
        importance=AlertImportance.HIGH,
        title="Already read concentration",
    )
    set_current_user(1)
    read_response = client.post(
        f"/api/v1/alert-candidates/{read_candidate['id']}/read"
    )
    assert read_response.status_code == 200

    response = client.get(
        "/api/v1/alert-candidates",
        params={
            "candidate_type": AlertCandidateType.PORTFOLIO_CONCENTRATION.value,
            "importance": AlertImportance.HIGH.value,
            "status": AlertCandidateStatus.UNREAD.value,
        },
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert [item["id"] for item in data] == [matched["id"]]
    assert data[0]["candidate_type"] == AlertCandidateType.PORTFOLIO_CONCENTRATION.value
    assert data[0]["importance"] == AlertImportance.HIGH.value
    assert data[0]["status"] == AlertCandidateStatus.UNREAD.value
    assert api_meta(response) == {"page": 1, "size": 20, "total": 1}


def test_mark_alert_candidate_read_and_confirm_update_status(
    client: TestClient,
) -> None:
    candidate = create_alert_candidate_for_user(1)
    set_current_user(1)

    read_response = client.post(f"/api/v1/alert-candidates/{candidate['id']}/read")
    confirm_response = client.post(
        f"/api/v1/alert-candidates/{candidate['id']}/confirm"
    )

    assert read_response.status_code == 200
    read_data = cast(dict[str, Any], api_data(read_response))
    assert read_data["status"] == AlertCandidateStatus.READ.value
    assert confirm_response.status_code == 200
    confirm_data = cast(dict[str, Any], api_data(confirm_response))
    assert confirm_data["status"] == AlertCandidateStatus.CONFIRMED.value


def test_alert_candidate_updates_return_404_for_other_user_or_missing_candidate(
    client: TestClient,
) -> None:
    candidate = create_alert_candidate_for_user(1)
    set_current_user(2, "other@example.com")

    other_user_response = client.post(
        f"/api/v1/alert-candidates/{candidate['id']}/read"
    )
    missing_response = client.post("/api/v1/alert-candidates/999/confirm")

    assert other_user_response.status_code == 404
    assert missing_response.status_code == 404
