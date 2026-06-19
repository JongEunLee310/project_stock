from datetime import datetime

from pydantic import BaseModel


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
    created_at: datetime
