import json
import logging
from typing import Any, cast

import openai
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONObject
from pydantic import BaseModel

from app.adapters.llm.base import LLMClient, LLMMessage
from app.adapters.llm.exceptions import LLMCallError, LLMTimeoutError

logger = logging.getLogger(__name__)


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.model = model
        self.client = openai.OpenAI(api_key=api_key)

    def complete(
        self, messages: list[LLMMessage], timeout: float | None = None
    ) -> str:
        logger.info(
            "provider call started",
            extra={"provider": "openai", "operation": "chat.completions.create"},
        )
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=_to_openai_messages(messages),
                timeout=timeout,
            )
        except openai.APITimeoutError as exc:
            logger.warning(
                "provider call timed out",
                extra={"provider": "openai", "operation": "chat.completions.create"},
            )
            raise LLMTimeoutError("OpenAI request timed out") from exc
        except openai.OpenAIError as exc:
            logger.warning(
                "provider call failed",
                extra={"provider": "openai", "operation": "chat.completions.create"},
            )
            raise LLMCallError("OpenAI request failed") from exc

        logger.info(
            "provider call completed",
            extra={"provider": "openai", "operation": "chat.completions.create"},
        )
        content = completion.choices[0].message.content
        return content or ""

    def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[BaseModel],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        operation = "chat.completions.create_json"
        logger.info(
            "provider call started",
            extra={"provider": "openai", "operation": operation},
        )
        # Keep the schema instruction provider-owned by always prepending it.
        schema_message = LLMMessage(
            role="system",
            content=(
                "Return only a valid JSON object matching this JSON Schema: "
                f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
            ),
        )

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=_to_openai_messages([schema_message, *messages]),
                response_format=ResponseFormatJSONObject(type="json_object"),
                timeout=timeout,
            )
        except openai.APITimeoutError as exc:
            logger.warning(
                "provider call timed out",
                extra={"provider": "openai", "operation": operation},
            )
            raise LLMTimeoutError("OpenAI request timed out") from exc
        except openai.OpenAIError as exc:
            logger.warning(
                "provider call failed",
                extra={"provider": "openai", "operation": operation},
            )
            raise LLMCallError("OpenAI request failed") from exc

        content = completion.choices[0].message.content
        if not content:
            return {}

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.warning(
                "provider call returned invalid json",
                extra={"provider": "openai", "operation": operation},
            )
            raise LLMCallError("OpenAI returned invalid JSON") from exc

        if not isinstance(parsed, dict):
            logger.warning(
                "provider call returned non-object json",
                extra={"provider": "openai", "operation": operation},
            )
            raise LLMCallError("OpenAI returned JSON that is not an object")
        logger.info(
            "provider call completed",
            extra={"provider": "openai", "operation": operation},
        )
        return parsed


def _to_openai_messages(messages: list[LLMMessage]) -> list[ChatCompletionMessageParam]:
    return [
        cast(
            ChatCompletionMessageParam,
            {"role": message.role, "content": message.content},
        )
        for message in messages
    ]
