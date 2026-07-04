import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any, Protocol

from pydantic import BaseModel

from app.adapters.llm.privacy import CloudSafePayload
from app.adapters.llm.types import LLMTaskType


class RedisCache(Protocol):
    def get(self, name: str) -> str | None: ...

    def setex(self, name: str, time: int, value: str) -> object: ...


class LLMCache:
    def __init__(self, redis: RedisCache, ttl: int) -> None:
        self.redis = redis
        self.ttl = ttl

    def compute_key(
        self,
        task_type: LLMTaskType,
        user_id: int | None,
        payload: CloudSafePayload,
        system_prompt: str,
        schema: type[BaseModel],
        model_policy_version: str,
        on_date: date | None = None,
    ) -> str:
        bucket_date = on_date if on_date is not None else datetime.now(UTC).date()
        materials = {
            "task_type": task_type.value,
            "user_id": str(user_id) if user_id is not None else "none",
            "snapshot_hash": _sha256_json(payload.as_payload()),
            "prompt_version": _sha256_text(system_prompt),
            "model_policy_version": model_policy_version,
            "output_schema_version": _sha256_json(schema.model_json_schema()),
            "date": bucket_date.strftime("%Y%m%d"),
        }
        return f"llm:cache:{_sha256_json(materials)}"

    def get_cached(self, key: str) -> str | None:
        return self.redis.get(key)

    def put(self, key: str, value: str) -> None:
        self.redis.setex(key, self.ttl, value)


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _sha256_json(value: dict[str, Any]) -> str:
    return _sha256_text(_canonical_json(value))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
