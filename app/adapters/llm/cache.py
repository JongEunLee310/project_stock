import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel

from app.adapters.llm.privacy import CloudSafePayload
from app.adapters.llm.types import LLMTaskType


logger = logging.getLogger(__name__)

# Bump when prompt assembly, provider schema instructions, or cache envelope changes.
CACHE_SCHEMA_VERSION = "v1"


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
        digest_material = json.dumps(
            [
                payload.as_payload(),
                system_prompt,
                model_name,
                schema.model_json_schema(),
            ],
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(
            digest_material.encode("utf-8")
        ).hexdigest()
        date_key = datetime.now(UTC).strftime("%Y%m%d")
        return (
            f"llm:cache:{CACHE_SCHEMA_VERSION}:"
            f"{task_type.value}:{date_key}:{digest}"
        )

    def lookup(self, key: str) -> CachedCompletion | None:
        try:
            raw_value = self.redis.get(key)
        except Exception as exc:
            logger.warning(
                "LLM cache lookup failed key=%s error_type=%s",
                key,
                type(exc).__name__,
            )
            return None
        if not raw_value:
            return None

        try:
            value = json.loads(raw_value)
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            logger.warning(
                "LLM cache lookup decode failed key=%s error_type=%s",
                key,
                type(exc).__name__,
            )
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
        except Exception as exc:
            logger.warning(
                "LLM cache store failed key=%s error_type=%s",
                key,
                type(exc).__name__,
            )
            return
