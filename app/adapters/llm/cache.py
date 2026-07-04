import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel

from app.adapters.llm.privacy import CloudSafePayload
from app.adapters.llm.types import LLMTaskType


class RedisCacheStore(Protocol):
    def get(self, name: str) -> str | bytes | None: ...

    def set(self, name: str, value: str, ex: int) -> object: ...


@dataclass(frozen=True)
class CachedCompletion:
    output: dict[str, Any]
    provider: str
    model_name: str


class LLMResponseCache:
    def __init__(self, redis: RedisCacheStore, ttl_seconds: int) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def build_key(
        self,
        task_type: LLMTaskType,
        payload: CloudSafePayload,
        system_prompt: str,
        model_name: str,
        schema: type[BaseModel],
    ) -> str:
        payload_json = json.dumps(
            payload.as_payload(),
            sort_keys=True,
            ensure_ascii=False,
        )
        schema_json = json.dumps(schema.model_json_schema(), sort_keys=True)
        digest = hashlib.sha256(
            f"{payload_json}{system_prompt}{model_name}{schema_json}".encode("utf-8")
        ).hexdigest()
        date_key = datetime.now(UTC).strftime("%Y%m%d")
        return f"llm:cache:{task_type.value}:{date_key}:{digest}"

    def lookup(self, key: str) -> CachedCompletion | None:
        try:
            raw_value = self.redis.get(key)
        except Exception:
            return None
        if not raw_value:
            return None

        try:
            value = json.loads(raw_value)
        except (TypeError, ValueError, UnicodeDecodeError):
            return None

        if not isinstance(value, dict):
            return None
        output = value.get("output")
        provider = value.get("provider")
        model_name = value.get("model_name")
        if (
            not isinstance(output, dict)
            or not isinstance(provider, str)
            or not isinstance(model_name, str)
        ):
            return None
        return CachedCompletion(output=output, provider=provider, model_name=model_name)

    def store(
        self,
        key: str,
        output: dict[str, Any],
        provider: str,
        model_name: str,
    ) -> None:
        value = json.dumps(
            {
                "output": output,
                "provider": provider,
                "model_name": model_name,
            },
            ensure_ascii=False,
        )
        try:
            self.redis.set(key, value, ex=self.ttl_seconds)
        except Exception:
            return
