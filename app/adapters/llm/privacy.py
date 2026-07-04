from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar, Sequence

from pydantic import BaseModel, ConfigDict

from app.adapters.llm.exceptions import CloudBoundaryViolationError
from app.adapters.llm.types import LLMTaskType, SensitivityLevel
from app.domains.dashboard.schema import DashboardSummaryResponse
from app.domains.llm_context.schema import (
    DataQualityStatus,
    LLMContextBundle,
)
from app.domains.portfolios.model import Portfolio, Position
from app.domains.portfolios.schema import PortfolioSummaryResponse


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


class NewsSummarySnapshot(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.PUBLIC

    title: str
    body: str


class ThesisConflictSnapshot(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.AGGREGATED

    thesis_summary: str
    invalidation_conditions: str
    news_summary: str
    news_positive_factors: list[str]
    news_negative_factors: list[str]


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


class WatchlistObservationSnapshot(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.AGGREGATED

    watchlist_id: int
    item_count: int
    items: list[WatchlistHighlight]


class ContextBundleProjectionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ContextBundleDataQualityProjection(ContextBundleProjectionModel):
    price_data_status: DataQualityStatus
    news_data_status: DataQualityStatus
    portfolio_data_status: DataQualityStatus
    warnings: list[str]


class ContextBundlePriceSnapshotProjection(ContextBundleProjectionModel):
    close: float | None
    return_1d: float | None
    return_5d: float | None
    return_20d: float | None
    drawdown_from_52w_high: float | None
    volume_vs_20d_avg: float | None


class ContextBundlePortfolioContextProjection(ContextBundleProjectionModel):
    holding: bool
    weight: float | None
    unrealized_return: float | None


class ContextBundleRecentNewsProjection(ContextBundleProjectionModel):
    title: str
    summary: str
    source: str
    published_at: datetime
    trust_level: str


class ContextBundleSignalProjection(ContextBundleProjectionModel):
    type: str
    severity: str
    reason: str


class ContextBundleSymbolCardProjection(ContextBundleProjectionModel):
    symbol: str
    market: str
    display_name: str
    price_snapshot: ContextBundlePriceSnapshotProjection
    portfolio_context: ContextBundlePortfolioContextProjection | None
    recent_news: list[ContextBundleRecentNewsProjection]
    signals: list[ContextBundleSignalProjection]


class ContextBundlePortfolioSummaryProjection(ContextBundleProjectionModel):
    cash_ratio: float | None
    top_holding_weight: float | None
    concentration_risk: str


class ContextBundleRecentDecisionProjection(ContextBundleProjectionModel):
    symbol: str
    decision_type: str
    reason: str
    created_at: datetime


class ContextBundleOutputContractProjection(ContextBundleProjectionModel):
    format: str
    required_fields: list[str]


class ContextBundleSnapshot(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.AGGREGATED

    task_type: LLMTaskType
    as_of: datetime
    user_intent: str
    symbols: list[str]
    data_quality: ContextBundleDataQualityProjection
    symbol_cards: list[ContextBundleSymbolCardProjection]
    portfolio_summary: ContextBundlePortfolioSummaryProjection | None
    user_rules: list[str]
    recent_decisions: list[ContextBundleRecentDecisionProjection]
    output_contract: ContextBundleOutputContractProjection


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


def to_watchlist_observation_snapshot(
    watchlist_id: int,
    items: Sequence[WatchlistHighlight],
) -> WatchlistObservationSnapshot:
    return WatchlistObservationSnapshot(
        watchlist_id=watchlist_id,
        item_count=len(items),
        items=list(items),
    )


def to_context_bundle_snapshot(bundle: LLMContextBundle) -> ContextBundleSnapshot:
    return ContextBundleSnapshot(
        task_type=bundle.task_type,
        as_of=bundle.as_of,
        user_intent=bundle.user_intent,
        symbols=list(bundle.symbols),
        data_quality=ContextBundleDataQualityProjection.model_validate(
            bundle.data_quality
        ),
        symbol_cards=[
            ContextBundleSymbolCardProjection(
                symbol=card.symbol,
                market=card.market,
                display_name=card.display_name,
                price_snapshot=ContextBundlePriceSnapshotProjection.model_validate(
                    card.price_snapshot
                ),
                portfolio_context=(
                    ContextBundlePortfolioContextProjection(
                        holding=card.portfolio_context.holding,
                        weight=card.portfolio_context.weight,
                        unrealized_return=card.portfolio_context.unrealized_return,
                    )
                    if card.portfolio_context is not None
                    else None
                ),
                recent_news=[
                    ContextBundleRecentNewsProjection.model_validate(news_item)
                    for news_item in card.recent_news
                ],
                signals=[
                    ContextBundleSignalProjection.model_validate(signal)
                    for signal in card.signals
                ],
            )
            for card in bundle.symbol_cards
        ],
        portfolio_summary=(
            ContextBundlePortfolioSummaryProjection.model_validate(
                bundle.portfolio_summary
            )
            if bundle.portfolio_summary is not None
            else None
        ),
        user_rules=list(bundle.user_rules),
        recent_decisions=[
            ContextBundleRecentDecisionProjection.model_validate(decision)
            for decision in bundle.recent_decisions
        ],
        output_contract=ContextBundleOutputContractProjection.model_validate(
            bundle.output_contract
        ),
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
