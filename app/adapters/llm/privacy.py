from decimal import Decimal
from collections.abc import Mapping
from typing import Any, ClassVar, Sequence

from pydantic import BaseModel, ConfigDict

from app.adapters.llm.exceptions import CloudBoundaryViolationError
from app.adapters.llm.types import SensitivityLevel
from app.domains.portfolios.model import Portfolio, Position
from app.domains.portfolios.schema import PortfolioSummaryResponse
from app.domains.dashboard.schema import DashboardSummaryResponse


ZERO = Decimal("0")
POSITION_COUNT_SMALL_MAX = 5
POSITION_COUNT_MEDIUM_MAX = 15
LOW_SHARE_MAX = Decimal("0.25")
MEDIUM_SHARE_MAX = Decimal("0.40")


class CloudSafePayload(BaseModel):
    sensitivity: ClassVar[SensitivityLevel]

    model_config = ConfigDict(frozen=True)

    def as_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class PortfolioConcentrationSnapshot(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.AGGREGATED

    position_count_band: str
    largest_position_band: str
    cash_band: str
    is_concentrated: bool


class PortfolioBriefingPosition(BaseModel):
    symbol: str
    sector: str
    weight: Decimal
    daily_change_percent: Decimal


class SectorWeightView(BaseModel):
    sector: str
    weight: Decimal


class RiskExposureView(BaseModel):
    code: str
    label: str
    level: str
    description: str


class WatchlistHighlight(BaseModel):
    symbol: str
    status: str
    per: Decimal | None = None
    peg: Decimal | None = None
    daily_change_percent: Decimal


class PortfolioBriefingSnapshot(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.AGGREGATED

    positions: list[PortfolioBriefingPosition]
    sector_weights: list[SectorWeightView]
    largest_position_weight: Decimal
    is_concentrated: bool
    concentration_threshold: Decimal
    cash_weight: Decimal
    day_change_percent: Decimal
    risk_exposures: list[RiskExposureView]


class DashboardBriefingSnapshot(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.AGGREGATED

    risk_alert_count: int
    important_news_count: int
    review_signal_count: int
    cash_weight: Decimal | None
    watchlist_highlights: list[WatchlistHighlight]


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


def to_briefing_snapshot(
    summary: PortfolioSummaryResponse,
    symbol_by_asset_id: Mapping[int, str],
    sector_by_asset_id: Mapping[int, str],
    daily_change_by_asset_id: Mapping[int, Decimal],
) -> PortfolioBriefingSnapshot:
    largest_position_weight = max(
        (position.weight for position in summary.positions),
        default=ZERO,
    )
    return PortfolioBriefingSnapshot(
        positions=[
            PortfolioBriefingPosition(
                symbol=symbol_by_asset_id.get(position.asset_id, str(position.asset_id)),
                sector=sector_by_asset_id.get(position.asset_id, "UNKNOWN"),
                weight=position.weight,
                daily_change_percent=daily_change_by_asset_id.get(
                    position.asset_id,
                    ZERO,
                ),
            )
            for position in summary.positions
        ],
        sector_weights=[
            SectorWeightView(sector=sector_weight.sector, weight=sector_weight.weight)
            for sector_weight in summary.sector_weights
        ],
        largest_position_weight=largest_position_weight,
        is_concentrated=largest_position_weight > summary.concentration_threshold,
        concentration_threshold=summary.concentration_threshold,
        cash_weight=summary.cash_weight,
        day_change_percent=summary.day_change_percent,
        risk_exposures=[
            RiskExposureView(
                code=risk_exposure.code,
                label=risk_exposure.label,
                level=risk_exposure.level,
                description=risk_exposure.description,
            )
            for risk_exposure in summary.risk_exposures
        ],
    )


def to_dashboard_snapshot(
    summary: DashboardSummaryResponse,
    highlights: Sequence[WatchlistHighlight],
) -> DashboardBriefingSnapshot:
    return DashboardBriefingSnapshot(
        risk_alert_count=summary.risk_alert_count,
        important_news_count=summary.important_news_count,
        review_signal_count=summary.review_signal_count,
        cash_weight=Decimal(summary.cash_weight) if summary.cash_weight is not None else None,
        watchlist_highlights=list(highlights),
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
