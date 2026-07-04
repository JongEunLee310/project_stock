import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.adapters.llm.base import LLMClient, LLMMessage
from app.adapters.llm.budget import DailyCallBudget
from app.adapters.llm.cache import LLMResponseCache
from app.adapters.llm.exceptions import LLMRoutingError
from app.adapters.llm.privacy import CloudSafePayload, PrivacyGate
from app.adapters.llm.router import LLMRouter
from app.adapters.llm.types import LLMTaskType


CLOUD = "cloud"
LOCAL = "local"


@dataclass(frozen=True)
class LLMCompletionResult:
    output: dict[str, Any]
    provider: str
    model_name: str
    cached: bool = False


class LLMGateway:
    def __init__(
        self,
        clients: Mapping[str, LLMClient],
        router: LLMRouter | None = None,
        privacy_gate: PrivacyGate | None = None,
        timeout_seconds: float | None = None,
        call_budget: DailyCallBudget | None = None,
        response_cache: LLMResponseCache | None = None,
    ) -> None:
        self.clients = clients
        self.router = LLMRouter() if router is None else router
        self.privacy_gate = PrivacyGate() if privacy_gate is None else privacy_gate
        self.timeout_seconds = timeout_seconds
        self.call_budget = call_budget
        self.response_cache = response_cache

    def complete_json(
        self,
        task_type: LLMTaskType,
        payload: CloudSafePayload,
        schema: type[BaseModel],
        system_prompt: str,
    ) -> LLMCompletionResult:
        provider = self.router.resolve(task_type)
        client = self.clients.get(provider)
        if client is None:
            raise LLMRoutingError(f"LLM client is not configured: {provider}")

        safe_payload = (
            self.privacy_gate.guard(payload) if provider == CLOUD else payload
        )
        cache_key: str | None = None
        if provider == CLOUD and self.response_cache is not None:
            cache_key = self.response_cache.build_key(
                task_type,
                safe_payload,
                system_prompt,
                client.model_name,
                schema,
            )
            cached_completion = self.response_cache.lookup(cache_key)
            if cached_completion is not None:
                return LLMCompletionResult(
                    output=cached_completion.output,
                    provider=cached_completion.provider,
                    model_name=cached_completion.model_name,
                    cached=True,
                )

        if provider == CLOUD and self.call_budget is not None:
            self.call_budget.consume()
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(
                role="user",
                content=json.dumps(safe_payload.as_payload(), ensure_ascii=False),
            ),
        ]

        output = client.complete_json(messages, schema, timeout=self.timeout_seconds)
        if (
            output
            and provider == CLOUD
            and self.response_cache is not None
            and cache_key is not None
        ):
            self.response_cache.store(
                cache_key,
                output,
                client.provider_name,
                client.model_name,
            )
        return LLMCompletionResult(
            output=output,
            provider=client.provider_name,
            model_name=client.model_name,
        )
