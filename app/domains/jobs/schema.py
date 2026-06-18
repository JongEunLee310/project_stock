from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JobRunCreate(BaseModel):
    job_type: str = Field(max_length=100)
    metadata: dict[str, Any] | None = None


class JobRunResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    job_type: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    created_at: datetime
