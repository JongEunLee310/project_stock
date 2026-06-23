from pydantic import BaseModel

from app.core.schema import UtcDatetime


class AlertCreate(BaseModel):
    user_id: int
    signal_id: int
    dedup_key: str


class AlertResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    signal_id: int
    status: str
    created_at: UtcDatetime
