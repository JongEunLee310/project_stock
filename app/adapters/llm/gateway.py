import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.adapters.llm.base import LLMClient, LLMMessage
from app.adapters.llm.budget import DailyCallBudget
from app.adapters.llm.cache import LLMResponseCache
from app.adapters.llm.escalation import EscalationPolicy, EscalationSignal
from app.adapters.llm.exceptions import LLMRoutingError
from app.adapters.llm.privacy import CloudSafePayload, PrivacyGate
from app.adapters.llm.router import LLMRouter
from app.adapters.llm.types import LLMTaskType


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
        escalation_signal: EscalationSignal | None = None,
    ) -> LLMCompletionResult:
        provider = self.router.resolve(task_type)
        escalated = False
        if (
            self.escalation_policy is not None
            and escalation_signal is not None
            and self.escalation_policy.should_escalate_before(
                escalation_signal,
                provider,
            )
        ):
            logger.info(
                "llm provider escalated before call",
                extra={
                    "task_type": task_type.value,
                    "from_provider": provider,
                    "to_provider": CLOUD,
                },
            )
            provider = CLOUD
            escalated = True

        first_provider = provider
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
                    escalated=escalated,
                )

        if provider == CLOUD and self.call_budget is not None:
            self.call_budget.consume()
        messages = self._build_messages(system_prompt, safe_payload)

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
        result_provider = client.provider_name
        result_model_name = client.model_name

        if (
            self.escalation_policy is not None
            and self.escalation_policy.should_verify_after(
                output,
                schema,
                first_provider,
            )
        ):
            verification = self._complete_cloud_verification(
                task_type,
                payload,
                schema,
                system_prompt,
            )
            if verification is not None:
                escalated = True
                verified_output, verified_provider, verified_model_name = verification
                if verified_output is not None:
                    output = verified_output
                    result_provider = verified_provider
                    result_model_name = verified_model_name

        return LLMCompletionResult(
            output=output,
            provider=result_provider,
            model_name=result_model_name,
            escalated=escalated,
        )

    def _complete_cloud_verification(
        self,
        task_type: LLMTaskType,
        payload: CloudSafePayload,
        schema: type[BaseModel],
        system_prompt: str,
    ) -> tuple[dict[str, Any] | None, str, str] | None:
        cloud_client = self.clients.get(CLOUD)
        if cloud_client is None:
            logger.warning(
                "llm cloud verification skipped because client is not configured",
                extra={"task_type": task_type.value, "provider": CLOUD},
            )
            return None

        logger.info(
            "llm cloud verification started",
            extra={"task_type": task_type.value, "provider": CLOUD},
        )
        try:
            safe_payload = self.privacy_gate.guard(payload)
            if self.call_budget is not None:
                self.call_budget.consume()
            messages = self._build_messages(system_prompt, safe_payload)
            output = cloud_client.complete_json(
                messages,
                schema,
                timeout=self.timeout_seconds,
            )
            schema.model_validate(output)
        except ValidationError:
            logger.warning(
                "llm cloud verification returned schema-invalid output",
                extra={"task_type": task_type.value, "provider": CLOUD},
            )
            return (None, cloud_client.provider_name, cloud_client.model_name)
        except Exception:
            logger.warning(
                "llm cloud verification failed",
                extra={"task_type": task_type.value, "provider": CLOUD},
            )
            return (None, cloud_client.provider_name, cloud_client.model_name)

        logger.info(
            "llm cloud verification completed",
            extra={"task_type": task_type.value, "provider": CLOUD},
        )
        return (output, cloud_client.provider_name, cloud_client.model_name)

    def _build_messages(
        self,
        system_prompt: str,
        payload: CloudSafePayload,
    ) -> list[LLMMessage]:
        return [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(
                role="user",
                content=json.dumps(payload.as_payload(), ensure_ascii=False),
            ),
        ]
