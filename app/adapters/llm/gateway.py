import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.adapters.llm.base import LLMClient, LLMMessage
from app.adapters.llm.budget import DailyCallBudget
from app.adapters.llm.cache import LLMResponseCache
from app.adapters.llm.escalation import EscalationPolicy, EscalationTrigger
from app.adapters.llm.exceptions import CloudBoundaryViolationError, LLMRoutingError
from app.adapters.llm.privacy import CloudSafePayload, PrivacyGate
from app.adapters.llm.router import LLMRouter
from app.adapters.llm.types import LLMTaskType, RiskLevel


CLOUD = "cloud"
LOCAL = "local"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMCompletionResult:
    output: dict[str, Any]
    provider: str
    model_name: str
    cached: bool = False
    escalated: bool = False
    escalation_trigger: str | None = None


class LLMGateway:
    def __init__(
        self,
        clients: Mapping[str, LLMClient],
        router: LLMRouter | None = None,
        privacy_gate: PrivacyGate | None = None,
        timeout_seconds: float | None = None,
        call_budget: DailyCallBudget | None = None,
        response_cache: LLMResponseCache | None = None,
        escalation_policy: EscalationPolicy | None = None,
    ) -> None:
        self.clients = clients
        self.router = LLMRouter() if router is None else router
        self.privacy_gate = PrivacyGate() if privacy_gate is None else privacy_gate
        self.timeout_seconds = timeout_seconds
        self.call_budget = call_budget
        self.response_cache = response_cache
        self.escalation_policy = escalation_policy

    def complete_json(
        self,
        task_type: LLMTaskType,
        payload: CloudSafePayload,
        schema: type[BaseModel],
        system_prompt: str,
        *,
        risk_level: RiskLevel = RiskLevel.LOW,
    ) -> LLMCompletionResult:
        provider = self.router.resolve(task_type)
        if provider == CLOUD:
            return self._complete_cloud_json(task_type, payload, schema, system_prompt)

        policy = self.escalation_policy
        if policy is not None:
            pre_call_trigger = policy.evaluate_pre_call(risk_level)
            if pre_call_trigger is not None and self._can_escalate(payload):
                return self._complete_escalated_cloud_json(
                    task_type,
                    payload,
                    schema,
                    system_prompt,
                    pre_call_trigger,
                )

        result = self._complete_provider_json(provider, payload, schema, system_prompt)
        if policy is None:
            return result

        post_call_trigger = policy.evaluate_post_call(result.output, schema)
        if post_call_trigger is None or not self._can_escalate(payload):
            return result

        return self._complete_escalated_cloud_json(
            task_type,
            payload,
            schema,
            system_prompt,
            post_call_trigger,
        )

    def _complete_escalated_cloud_json(
        self,
        task_type: LLMTaskType,
        payload: CloudSafePayload,
        schema: type[BaseModel],
        system_prompt: str,
        trigger: EscalationTrigger,
    ) -> LLMCompletionResult:
        logger.warning(
            "Escalating LLM task %s from local to cloud: %s",
            task_type.value,
            trigger.value,
        )
        result = self._complete_cloud_json(task_type, payload, schema, system_prompt)
        return LLMCompletionResult(
            output=result.output,
            provider=result.provider,
            model_name=result.model_name,
            cached=result.cached,
            escalated=True,
            escalation_trigger=trigger.value,
        )

    def _can_escalate(self, payload: CloudSafePayload) -> bool:
        try:
            self.privacy_gate.guard(payload)
        except CloudBoundaryViolationError:
            return False
        return True

    def _complete_cloud_json(
        self,
        task_type: LLMTaskType,
        payload: CloudSafePayload,
        schema: type[BaseModel],
        system_prompt: str,
    ) -> LLMCompletionResult:
        safe_payload = self.privacy_gate.guard(payload)
        client = self._get_client(CLOUD)
        cache_key: str | None = None
        if self.response_cache is not None:
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

        if self.call_budget is not None:
            self.call_budget.consume()
        output = self._call_client(client, safe_payload, schema, system_prompt)
        if output and self.response_cache is not None and cache_key is not None:
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

    def _complete_provider_json(
        self,
        provider: str,
        payload: CloudSafePayload,
        schema: type[BaseModel],
        system_prompt: str,
    ) -> LLMCompletionResult:
        client = self._get_client(provider)
        output = self._call_client(client, payload, schema, system_prompt)
        return LLMCompletionResult(
            output=output,
            provider=client.provider_name,
            model_name=client.model_name,
        )

    def _get_client(self, provider: str) -> LLMClient:
        client = self.clients.get(provider)
        if client is None:
            raise LLMRoutingError(f"LLM client is not configured: {provider}")
        return client

    def _call_client(
        self,
        client: LLMClient,
        payload: CloudSafePayload,
        schema: type[BaseModel],
        system_prompt: str,
    ) -> dict[str, Any]:
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(
                role="user",
                content=json.dumps(payload.as_payload(), ensure_ascii=False),
            ),
        ]
        return client.complete_json(messages, schema, timeout=self.timeout_seconds)
