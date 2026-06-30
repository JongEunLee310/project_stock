from decimal import Decimal
from typing import Any, ClassVar, Sequence

from pydantic import BaseModel, ConfigDict

from app.adapters.llm.exceptions import CloudBoundaryViolationError
from app.adapters.llm.types import SensitivityLevel
from app.domains.portfolios.model import Portfolio, Position


ZERO = Decimal("0")
POSITION_COUNT_SMALL_MAX = 5
POSITION_COUNT_MEDIUM_MAX = 15
LOW_SHARE_MAX = Decimal("0.25")
MEDIUM_SHARE_MAX = Decimal("0.40")


class CloudSafePayload(BaseModel):
    sensitivity: ClassVar[SensitivityLevel]

    model_config = ConfigDict(frozen=True)

    def as_payload(self) -> dict[str, Any]:
        return self.model_dump()


class PortfolioConcentrationSnapshot(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.AGGREGATED

    position_count_band: str
    largest_position_band: str
    cash_band: str
    is_concentrated: bool


def to_concentration_snapshot(
    portfolio: Portfolio,
    positions: Sequence[Position],
) -> PortfolioConcentrationSnapshot:
    position_values = [_position_value(position) for position in positions]
    positive_position_values = [
        position_value for position_value in position_values if position_value > ZERO
    ]
    cash_balance = max(portfolio.cash_balance, ZERO)
    total_value = cash_balance + sum(positive_position_values, ZERO)
    largest_position_share = _share(
        max(positive_position_values, default=ZERO),
        total_value,
    )
    cash_share = _share(cash_balance, total_value)

    return PortfolioConcentrationSnapshot(
        position_count_band=_position_count_band(len(positions)),
        largest_position_band=_share_band(largest_position_share),
        cash_band=_share_band(cash_share),
        is_concentrated=largest_position_share > portfolio.concentration_threshold,
    )


class PrivacyGate:
    CLOUD_ALLOWED: ClassVar[frozenset[SensitivityLevel]] = frozenset(
        {SensitivityLevel.AGGREGATED, SensitivityLevel.PUBLIC}
    )

    def guard(self, payload: object) -> CloudSafePayload:
        if not isinstance(payload, CloudSafePayload):
            raise CloudBoundaryViolationError("payload is not CloudSafe")

        if payload.sensitivity not in self.CLOUD_ALLOWED:
            raise CloudBoundaryViolationError(
                f"payload sensitivity is not allowed: {payload.sensitivity.value}"
            )

        return payload


def _position_value(position: Position) -> Decimal:
    return position.quantity * position.avg_buy_price


def _share(value: Decimal, total: Decimal) -> Decimal:
    if total <= ZERO:
        return ZERO
    return value / total


def _position_count_band(position_count: int) -> str:
    if position_count <= POSITION_COUNT_SMALL_MAX:
        return "1-5"
    if position_count <= POSITION_COUNT_MEDIUM_MAX:
        return "6-15"
    return "16+"


def _share_band(share: Decimal) -> str:
    if share < LOW_SHARE_MAX:
        return "0-25%"
    if share < MEDIUM_SHARE_MAX:
        return "25-40%"
    return "40%+"
