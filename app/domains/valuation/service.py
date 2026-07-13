from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.model import Asset
from app.domains.assets.repository import AssetRepository
from app.domains.earnings.repository import EarningsRepository
from app.domains.prices.repository import PriceBarRepository
from app.domains.valuation.history import (
    build_per_series,
    build_ttm_eps_series,
    median_and_percentile,
)
from app.domains.valuation.model import ValuationSnapshot
from app.domains.valuation.repository import ValuationRepository
from app.domains.valuation.schema import (
    ValuationMetric,
    ValuationMetricName,
    ValuationMetricsResponse,
    ValuationProfile,
)

_METRIC_FIELDS: tuple[tuple[ValuationMetricName, str], ...] = (
    (ValuationMetricName.PER, "per"),
    (ValuationMetricName.FORWARD_PER, "forward_per"),
    (ValuationMetricName.PSR, "psr"),
    (ValuationMetricName.PBR, "pbr"),
    (ValuationMetricName.EV_EBITDA, "ev_ebitda"),
    (ValuationMetricName.PEG, "peg"),
    (ValuationMetricName.FCF_YIELD, "fcf_yield"),
)
_HIGHLIGHTED_METRICS = {
    ValuationProfile.FINANCIAL: (ValuationMetricName.PBR, ValuationMetricName.PER),
    ValuationProfile.DEFICIT: (ValuationMetricName.PSR, ValuationMetricName.FCF_YIELD),
    ValuationProfile.GENERAL: (
        ValuationMetricName.PER,
        ValuationMetricName.PBR,
        ValuationMetricName.EV_EBITDA,
    ),
}


class ValuationService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.valuation_repo = ValuationRepository(db)
        self.price_repo = PriceBarRepository(db)
        self.earnings_repo = EarningsRepository(db)

    def get_metrics(self, asset_id: int) -> ValuationMetricsResponse:
        asset = self.asset_repo.get_by_id(asset_id)
        if asset is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )
        snapshot = self.valuation_repo.get_latest(asset.symbol, asset.market)
        profile = self._profile(asset, snapshot)
        history_metrics = self._per_history(asset)
        return ValuationMetricsResponse(
            asset_id=asset.id,
            profile=profile,
            highlighted_metrics=list(_HIGHLIGHTED_METRICS[profile]),
            metrics=[
                ValuationMetric(
                    metric=metric,
                    value=self._value(snapshot, field),
                    five_year_median=(
                        history_metrics[0]
                        if metric is ValuationMetricName.PER and history_metrics
                        else None
                    ),
                    percentile=(
                        history_metrics[1]
                        if metric is ValuationMetricName.PER and history_metrics
                        else None
                    ),
                )
                for metric, field in _METRIC_FIELDS
            ],
        )

    def _per_history(self, asset: Asset) -> tuple[Decimal, int] | None:
        closes = self.price_repo.get_daily_closes(
            asset.symbol,
            asset.market,
            start=_five_years_ago(date.today()),
        )
        reports = self.earnings_repo.get_recent(asset.symbol, asset.market, limit=8)
        return median_and_percentile(
            build_per_series(closes, build_ttm_eps_series(reports))
        )

    @staticmethod
    def _profile(asset: Asset, snapshot: ValuationSnapshot | None) -> ValuationProfile:
        if asset.sector == "Financial Services":
            return ValuationProfile.FINANCIAL
        if snapshot is not None and snapshot.per is None and snapshot.forward_per is None:
            return ValuationProfile.DEFICIT
        return ValuationProfile.GENERAL

    @staticmethod
    def _value(snapshot: ValuationSnapshot | None, field: str) -> Decimal | None:
        return getattr(snapshot, field) if snapshot is not None else None


def _five_years_ago(today: date) -> date:
    try:
        return today.replace(year=today.year - 5)
    except ValueError:
        return today.replace(year=today.year - 5, day=28)
