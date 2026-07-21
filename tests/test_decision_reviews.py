from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.domains.decision_logs.model import DecisionLog
from app.domains.decision_logs.service import DecisionLogService
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user


def _create_decision(client: TestClient, *, activate: bool = True) -> dict[str, Any]:
    response = client.post(
        "/api/v1/decision-logs",
        json={
            "target": {"type": "SYMBOL", "id": "AAPL"},
            "decision_type": "BUY_REVIEW",
            "thesis": "서비스 매출이 계속 성장한다.",
        },
    )
    assert response.status_code == 201
    decision = cast(dict[str, Any], api_data(response))
    if activate:
        activate_response = client.post(
            f"/api/v1/decision-logs/{decision['id']}/activate",
            json={},
        )
        assert activate_response.status_code == 200
    return decision


def _review_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "outcome_status": "THESIS_PARTIALLY_CONFIRMED",
        "thesis_result": "PARTIALLY_CONFIRMED",
        "process_quality": {
            "evidence_quality": 4,
            "counter_argument_review": 3,
        },
        "result_metrics": {
            "return_rate": "0.12",
            "benchmark_return_rate": "0.08",
        },
        "what_went_well": "반대 근거를 사전에 기록했다.",
        "what_was_missed": "환율 영향을 과소평가했다.",
        "what_to_change": "환율 민감도를 별도로 확인한다.",
    }
    payload.update(overrides)
    return payload


def test_create_review_separates_quality_and_result_and_marks_reviewed(
    client: TestClient,
) -> None:
    set_current_user(1)
    decision = _create_decision(client)
    reviewed_at = datetime(2026, 8, 21, 12, 30, tzinfo=UTC)

    with patch.object(DecisionLogService, "_now", return_value=reviewed_at):
        response = client.post(
            f"/api/v1/decision-logs/{decision['id']}/reviews",
            json=_review_payload(),
        )

    assert response.status_code == 201
    review = cast(dict[str, Any], api_data(response))
    assert review["decision_id"] == decision["id"]
    assert review["process_quality"] == {
        "evidence_quality": 4,
        "counter_argument_review": 3,
    }
    assert review["result_metrics"] == {
        "return_rate": "0.12",
        "benchmark_return_rate": "0.08",
    }
    assert review["reviewed_at"] == "2026-08-21T12:30:00Z"
    assert review["created_at"].endswith("Z")
    assert review["updated_at"].endswith("Z")

    with TestingSessionLocal() as db:
        stored = db.get(DecisionLog, decision["id"])
        assert stored is not None
        assert stored.status == "REVIEWED"
        assert stored.reviewed_at is not None
        assert stored.reviewed_at.replace(tzinfo=UTC) == reviewed_at


def test_create_review_rejects_draft_decision(client: TestClient) -> None:
    set_current_user(1)
    decision = _create_decision(client, activate=False)

    response = client.post(
        f"/api/v1/decision-logs/{decision['id']}/reviews",
        json=_review_payload(),
    )

    assert response.status_code == 409
    assert api_error(response)["code"] == "DECISION_LOG_INVALID_STATE"


def test_list_reviews_returns_multiple_reviews_newest_first(
    client: TestClient,
) -> None:
    set_current_user(1)
    decision = _create_decision(client)
    first_at = datetime(2026, 8, 21, 12, tzinfo=UTC)
    second_at = datetime(2026, 9, 21, 12, tzinfo=UTC)

    with patch.object(
        DecisionLogService,
        "_now",
        side_effect=[first_at, second_at],
    ):
        first_response = client.post(
            f"/api/v1/decision-logs/{decision['id']}/reviews",
            json=_review_payload(outcome_status="INSUFFICIENT_TIME"),
        )
        second_response = client.post(
            f"/api/v1/decision-logs/{decision['id']}/reviews",
            json=_review_payload(
                outcome_status="THESIS_CONFIRMED",
                thesis_result="CONFIRMED",
            ),
        )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    response = client.get(f"/api/v1/decision-logs/{decision['id']}/reviews")
    assert response.status_code == 200
    reviews = cast(list[dict[str, Any]], api_data(response))
    assert [review["outcome_status"] for review in reviews] == [
        "THESIS_CONFIRMED",
        "INSUFFICIENT_TIME",
    ]
    assert [review["reviewed_at"] for review in reviews] == [
        "2026-09-21T12:00:00Z",
        "2026-08-21T12:00:00Z",
    ]

    with TestingSessionLocal() as db:
        stored = db.get(DecisionLog, decision["id"])
        assert stored is not None
        assert stored.reviewed_at is not None
        assert stored.reviewed_at.replace(tzinfo=UTC) == first_at


def test_review_routes_enforce_ownership_and_missing_decision(
    client: TestClient,
) -> None:
    set_current_user(1)
    decision = _create_decision(client)
    set_current_user(2, "other@example.com")

    responses = (
        client.post(
            f"/api/v1/decision-logs/{decision['id']}/reviews",
            json=_review_payload(),
        ),
        client.get(f"/api/v1/decision-logs/{decision['id']}/reviews"),
    )
    for response in responses:
        assert response.status_code == 403
        assert api_error(response)["code"] == "DECISION_LOG_FORBIDDEN"

    missing_response = client.get("/api/v1/decision-logs/999/reviews")
    assert missing_response.status_code == 404
    assert api_error(missing_response)["code"] == "DECISION_LOG_NOT_FOUND"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("outcome_status", "UNKNOWN"),
        ("thesis_result", "UNKNOWN"),
    ],
)
def test_create_review_rejects_invalid_enums(
    client: TestClient,
    field: str,
    value: str,
) -> None:
    set_current_user(1)
    decision = _create_decision(client)

    response = client.post(
        f"/api/v1/decision-logs/{decision['id']}/reviews",
        json=_review_payload(**{field: value}),
    )

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"
