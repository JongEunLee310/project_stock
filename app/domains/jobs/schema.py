from typing import Any

from pydantic import BaseModel, Field

from app.core.schema import UtcDatetime


class JobRunCreate(BaseModel):
    job_type: str = Field(max_length=100)
    metadata: dict[str, Any] | None = None


class JobRunResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    job_type: str
    status: str
    started_at: UtcDatetime | None
    finished_at: UtcDatetime | None
    error_message: str | None
    created_at: UtcDatetime
