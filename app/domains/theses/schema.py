from pydantic import BaseModel, field_validator

from app.core.schema import UtcDatetime


class ThesisCreate(BaseModel):
    asset_id: int
    summary: str
    risk_factors: str | None = None
    invalidation_conditions: str | None = None


class ThesisUpdate(BaseModel):
    summary: str | None = None
    risk_factors: str | None = None
    invalidation_conditions: str | None = None

    @field_validator("summary")
    @classmethod
    def summary_must_not_be_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("summary는 null일 수 없습니다.")
        return value


class ThesisResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    asset_id: int
    summary: str
    risk_factors: str | None
    invalidation_conditions: str | None
    is_active: bool
    created_at: UtcDatetime
