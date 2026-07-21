import json
from typing import Any

from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.adapters.llm.base import LLMClient, LLMMessage
from app.adapters.llm.gateway import CLOUD, LOCAL, LLMGateway
from app.adapters.llm.privacy import DecisionAssistSnapshot, PrivacyGate
from app.adapters.llm.prompts.decision_assist import (
    build_decision_assist_system_prompt,
)
from app.adapters.llm.types import SensitivityLevel
from app.domains.decision_logs.assist_service import DecisionAssistService
from app.domains.decision_logs.schema import (
    DecisionAssistRequest,
    DecisionAssistResult,
)
from tests.conftest import api_data, api_error, set_current_user


ASSIST_PAYLOAD = {
    "target": {"type": "SYMBOL", "id": "AAPL"},
    "decision_type": "BUY_REVIEW",
    "thesis": "서비스 매출이 계속 성장할 것이다.",
    "rationale": "마진이 좋다.",
    "memo": "좋아 보이니 지금 꼭 사야 할지도 모른다.",
}

ASSIST_RESULT = {
    "structured_thesis": "서비스 매출 성장 지속 여부를 확인한다.",
    "structured_rationale": "마진 개선을 성장 지속의 근거로 검토한다.",
    "counter_arguments": ["서비스 성장률이 둔화될 수 있다."],
    "risk_candidates": [
        {"type": "VALUATION", "reason": "높은 밸류에이션을 점검해야 한다."}
    ],
    "bias_candidates": [
        {"type": "FOMO", "reason": "즉시 매수해야 한다는 표현을 점검해야 한다."}
    ],
    "vague_flags": [
        {"quote": "마진이 좋다", "suggestion": "비교 기간과 수치를 명시한다."}
    ],
}


class RecordingClient(LLMClient):
    def __init__(
        self,
        response: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = ASSIST_RESULT if response is None else response
        self.error = error
        self.messages: list[LLMMessage] = []
        self.schema: type[BaseModel] | None = None

    @property
    def provider_name(self) -> str:
        return "recording"

    @property
    def model_name(self) -> str:
        return "recording-model"

    def complete(
        self,
        messages: list[LLMMessage],
        timeout: float | None = None,
    ) -> str:
        raise NotImplementedError

    def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[BaseModel],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        self.messages = messages
        self.schema = schema
        if self.error is not None:
            raise self.error
        return self.response


def gateway_for(client: LLMClient) -> LLMGateway:
    return LLMGateway({CLOUD: client, LOCAL: client})


def test_assist_maps_all_suggestion_groups_and_uses_cloud_safe_snapshot() -> None:
    client = RecordingClient()
    service = DecisionAssistService(gateway_for(client))

    response = service.assist(7, DecisionAssistRequest.model_validate(ASSIST_PAYLOAD))

    assert response.model_dump() == ASSIST_RESULT
    assert client.schema is DecisionAssistResult
    assert len(client.messages) == 2
    transmitted = json.loads(client.messages[1].content)
    assert transmitted == {
        "target_type": "SYMBOL",
        "symbol": "AAPL",
        "decision_type": "BUY_REVIEW",
        "thesis": "서비스 매출이 계속 성장할 것이다.",
        "rationale": "마진이 좋다.",
        "memo": "좋아 보이니 지금 꼭 사야 할지도 모른다.",
    }
    assert "user_id" not in transmitted
    assert "target_id" not in transmitted


def test_decision_assist_snapshot_contains_only_whitelisted_fields() -> None:
    snapshot = DecisionAssistSnapshot(
        target_type="PORTFOLIO",
        symbol=None,
        decision_type=None,
        thesis=None,
        rationale=None,
        memo="현금 비중을 검토한다.",
    )

    assert snapshot.sensitivity is SensitivityLevel.AGGREGATED
    assert PrivacyGate().guard(snapshot) is snapshot
    assert snapshot.as_payload() == {
        "target_type": "PORTFOLIO",
        "symbol": None,
        "decision_type": None,
        "thesis": None,
        "rationale": None,
        "memo": "현금 비중을 검토한다.",
    }


def test_assist_does_not_send_non_symbol_target_id_to_llm() -> None:
    client = RecordingClient()
    service = DecisionAssistService(gateway_for(client))
    request = DecisionAssistRequest.model_validate(
        {
            "target": {"type": "PORTFOLIO", "id": "internal-portfolio-42"},
            "memo": "현금 비중을 검토한다.",
        }
    )

    service.assist(7, request)

    transmitted = json.loads(client.messages[1].content)
    assert transmitted["target_type"] == "PORTFOLIO"
    assert transmitted["symbol"] is None
    assert "internal-portfolio-42" not in client.messages[1].content


def test_assist_returns_empty_suggestions_when_llm_fails() -> None:
    service = DecisionAssistService(
        gateway_for(RecordingClient(error=RuntimeError("provider unavailable")))
    )

    response = service.assist(7, DecisionAssistRequest.model_validate(ASSIST_PAYLOAD))

    assert response.model_dump() == {
        "structured_thesis": None,
        "structured_rationale": None,
        "counter_arguments": [],
        "risk_candidates": [],
        "bias_candidates": [],
        "vague_flags": [],
    }


def test_assist_endpoint_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/v1/decision-logs/assist", json=ASSIST_PAYLOAD)

    assert response.status_code == 401


def test_assist_endpoint_rejects_invalid_input(client: TestClient) -> None:
    set_current_user(7)

    response = client.post(
        "/api/v1/decision-logs/assist",
        json={"target": {"type": "UNKNOWN", "id": "AAPL"}},
    )

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"


def test_assist_literal_route_returns_non_persistent_suggestions(
    client: TestClient,
    monkeypatch: Any,
) -> None:
    set_current_user(7)
    recording_client = RecordingClient()
    monkeypatch.setattr(
        "app.api.v1.endpoints.decision_logs.get_llm_gateway",
        lambda: gateway_for(recording_client),
    )

    response = client.post("/api/v1/decision-logs/assist", json=ASSIST_PAYLOAD)

    assert response.status_code == 200
    assert api_data(response) == ASSIST_RESULT


def test_decision_assist_prompt_preserves_user_decision_boundary() -> None:
    prompt = build_decision_assist_system_prompt()

    assert "do not make or finalize the decision" in prompt.lower()
    assert "check candidates" in prompt.lower()
    assert "only the user's supplied text" in prompt.lower()
    assert "vague" in prompt.lower()
