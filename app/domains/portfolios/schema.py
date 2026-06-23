from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.core.schema import UtcDatetime

from app.domains.signals.schema import SignalResponse


class PortfolioCreate(BaseModel):
    name: str = Field(max_length=255)
    concentration_threshold: Decimal = Field(
        default=Decimal("0.4"),
        gt=Decimal("0"),
        le=Decimal("1"),
    )
    cash_balance: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))


class PortfolioResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    name: str
    concentration_threshold: Decimal
    cash_balance: Decimal
    created_at: UtcDatetime


class PositionCreate(BaseModel):
    asset_id: int
    quantity: Decimal
    avg_buy_price: Decimal


class PositionUpdate(BaseModel):
    quantity: Decimal | None = None
    avg_buy_price: Decimal | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> Self:
        if self.quantity is None and self.avg_buy_price is None:
            raise ValueError("quantity 또는 avg_buy_price 중 하나는 필요합니다.")
        return self


class PositionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    portfolio_id: int
    asset_id: int
    quantity: Decimal
    avg_buy_price: Decimal
    created_at: UtcDatetime


class PositionWeight(BaseModel):
    asset_id: int
    quantity: Decimal
    avg_buy_price: Decimal
    cost_value: Decimal
    market_value: Decimal
    cost_weight: Decimal
    weight: Decimal
    exceeds_threshold: bool


class SectorWeight(BaseModel):
    sector: str
    market_value: Decimal
    weight: Decimal
    exceeds_threshold: bool


class PortfolioSummaryResponse(BaseModel):
    portfolio_id: int
    concentration_threshold: Decimal
    total_cost_value: Decimal
    total_value: Decimal
    cash_balance: Decimal
    cash_weight: Decimal
    has_sector_concentration: bool
    positions: list[PositionWeight]
    sector_weights: list[SectorWeight]


class PortfolioCheckResponse(BaseModel):
    summary: PortfolioSummaryResponse
    created_signals: list[SignalResponse]
