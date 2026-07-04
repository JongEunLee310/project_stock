import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel

from app.adapters.llm.base import LLMClient, LLMMessage
from app.adapters.llm.budget import DailyCallBudget
from app.adapters.llm.cache import LLMCache
from app.adapters.llm.exceptions import LLMRoutingError
from app.adapters.llm.privacy import CloudSafePayload, PrivacyGate
from app.adapters.llm.router import LLM_MODEL_POLICY_VERSION, LLMRouter
from app.adapters.llm.types import CachePolicy, LLMTaskType


CLOUD = "cloud"
LOCAL = "local"


@dataclass(frozen=True)
class LLMCompletionResult:
    output: dict[str, Any]
    provider: str
    model_name: str
    cache_hit: bool = False


class LLMGateway:
    def __init__(
        self,
        clients: Mapping[str, LLMClient],
        router: LLMRouter | None = None,
        privacy_gate: PrivacyGate | None = None,
        timeout_seconds: float | None = None,
        call_budget: DailyCallBudget | None = None,
        cache: LLMCache | None = None,
    ) -> None:
        self.clients = clients
        self.router = LLMRouter() if router is None else router
        self.privacy_gate = PrivacyGate() if privacy_gate is None else privacy_gate
        self.timeout_seconds = timeout_seconds
        self.call_budget = call_budget
        self.cache = cache

    def complete_json(
        self,
        task_type: LLMTaskType,
        payload: CloudSafePayload,
        schema: type[BaseModel],
        system_prompt: str,
        cache_policy: CachePolicy = CachePolicy.BYPASS,
        user_id: int | None = None,
    ) -> LLMCompletionResult:
        provider = self.router.resolve(task_type)
        client = self.clients.get(provider)
        if client is None:
            raise LLMRoutingError(f"LLM client is not configured: {provider}")

        safe_payload = (
            self.privacy_gate.guard(payload) if provider == CLOUD else payload
        )
        cache_key: str | None = None
        if cache_policy != CachePolicy.BYPASS and self.cache is not None:
            cache_key = self.cache.compute_key(
                task_type,
                user_id,
                safe_payload,
                system_prompt,
                schema,
                LLM_MODEL_POLICY_VERSION,
            )
            cached = self.cache.get_cached(cache_key)
            if cached is not None:
                envelope = cast(dict[str, Any], json.loads(cached))
                return LLMCompletionResult(
                    output=cast(dict[str, Any], envelope["output"]),
                    provider=cast(str, envelope["provider"]),
                    model_name=cast(str, envelope["model_name"]),
                    cache_hit=True,
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
        result = LLMCompletionResult(
            output=output,
            provider=client.provider_name,
            model_name=client.model_name,
        )
        if cache_policy == CachePolicy.READ_WRITE and self.cache is not None:
            if cache_key is None:
                cache_key = self.cache.compute_key(
                    task_type,
                    user_id,
                    safe_payload,
                    system_prompt,
                    schema,
                    LLM_MODEL_POLICY_VERSION,
                )
            self.cache.put(
                cache_key,
                json.dumps(
                    {
                        "output": result.output,
                        "provider": result.provider,
                        "model_name": result.model_name,
                    },
                    ensure_ascii=False,
                ),
            )
        return result
