from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.model import Asset
from app.domains.assets.repository import AssetRepository
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
        return ValuationMetricsResponse(
            asset_id=asset.id,
            profile=profile,
            highlighted_metrics=list(_HIGHLIGHTED_METRICS[profile]),
            metrics=[
                ValuationMetric(
                    metric=metric,
                    value=self._value(snapshot, field),
                    five_year_median=None,
                    percentile=None,
                )
                for metric, field in _METRIC_FIELDS
            ],
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
