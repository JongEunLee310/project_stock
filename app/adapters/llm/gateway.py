import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from app.adapters.llm.base import LLMClient, LLMMessage
from app.adapters.llm.exceptions import LLMRoutingError
from app.adapters.llm.privacy import CloudSafePayload, PrivacyGate
from app.adapters.llm.router import LLMRouter
from app.adapters.llm.types import LLMTaskType


CLOUD = "cloud"
LOCAL = "local"


class LLMGateway:
    def __init__(
        self,
        clients: Mapping[str, LLMClient],
        router: LLMRouter | None = None,
        privacy_gate: PrivacyGate | None = None,
    ) -> None:
        self.clients = clients
        self.router = LLMRouter() if router is None else router
        self.privacy_gate = PrivacyGate() if privacy_gate is None else privacy_gate

    def complete_json(
        self,
        task_type: LLMTaskType,
        payload: CloudSafePayload,
        schema: type[BaseModel],
        system_prompt: str,
    ) -> dict[str, Any]:
        provider = self.router.resolve(task_type)
        client = self.clients.get(provider)
        if client is None:
            raise LLMRoutingError(f"LLM client is not configured: {provider}")

        safe_payload = (
            self.privacy_gate.guard(payload) if provider == CLOUD else payload
        )
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(
                role="user",
                content=json.dumps(safe_payload.as_payload(), ensure_ascii=False),
            ),
        ]

        return client.complete_json(messages, schema)
