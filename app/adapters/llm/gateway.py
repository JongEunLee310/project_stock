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
                "llm escalation provider override: task_type=%s from_provider=%s "
                "to_provider=%s",
                task_type.value,
                provider,
                CLOUD,
            )
            provider = CLOUD
            escalated = True
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
        if (
            self.escalation_policy is not None
            and self.escalation_policy.should_verify_after(output, schema, provider)
        ):
            cloud_client = self.clients.get(CLOUD)
            if cloud_client is None:
                # 재호출이 수행되지 않았으므로 escalated로 표시하지 않는다.
                logger.warning(
                    "llm escalation cloud verification skipped: task_type=%s "
                    "reason=cloud_client_missing",
                    task_type.value,
                )
            else:
                verification = self._verify_with_cloud(
                    cloud_client,
                    task_type,
                    payload,
                    schema,
                    system_prompt,
                )
                escalated = True
                if verification is not None:
                    output, client = verification
        return LLMCompletionResult(
            output=output,
            provider=client.provider_name,
            model_name=client.model_name,
            escalated=escalated,
        )

    def _verify_with_cloud(
        self,
        cloud_client: LLMClient,
        task_type: LLMTaskType,
        payload: CloudSafePayload,
        schema: type[BaseModel],
        system_prompt: str,
    ) -> tuple[dict[str, Any], LLMClient] | None:
        try:
            safe_payload = self.privacy_gate.guard(payload)
            if self.call_budget is not None:
                self.call_budget.consume()
            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(
                    role="user",
                    content=json.dumps(safe_payload.as_payload(), ensure_ascii=False),
                ),
            ]
            output = cloud_client.complete_json(
                messages,
                schema,
                timeout=self.timeout_seconds,
            )
            schema.model_validate(output)
        except ValidationError:
            logger.warning(
                "llm escalation cloud verification failed: task_type=%s "
                "reason=schema_validation",
                task_type.value,
            )
            return None
        except Exception:
            logger.warning(
                "llm escalation cloud verification failed: task_type=%s "
                "reason=exception",
                task_type.value,
                exc_info=True,
            )
            return None
        logger.info(
            "llm escalation cloud verification completed: task_type=%s provider=%s",
            task_type.value,
            cloud_client.provider_name,
        )
        return output, cloud_client
