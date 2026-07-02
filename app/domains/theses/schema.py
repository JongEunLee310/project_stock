from pydantic import BaseModel, computed_field, field_validator

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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def title(self) -> str:
        title = next(
            (line.strip() for line in self.summary.splitlines() if line.strip()),
            "",
        )
        return title or "Investment thesis"
