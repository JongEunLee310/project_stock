from decimal import Decimal
from typing import TypedDict

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.valuation.schema import (
    ValuationMetric,
    ValuationMetricName,
    ValuationMetricsResponse,
    ValuationProfile,
)


class _MetricTemplate(TypedDict):
    metric: ValuationMetricName
    value: str | None
    five_year_median: str | None
    percentile: int | None


class _ValuationTemplate(TypedDict):
    profile: ValuationProfile
    highlighted_metrics: tuple[ValuationMetricName, ...]
    metrics: tuple[_MetricTemplate, ...]


_TEMPLATES: tuple[_ValuationTemplate, ...] = (
    {
        "profile": ValuationProfile.HIGH_GROWTH,
        "highlighted_metrics": (
            ValuationMetricName.FORWARD_PER,
            ValuationMetricName.PSR,
            ValuationMetricName.PEG,
        ),
        "metrics": (
            {"metric": ValuationMetricName.PER, "value": "42.8", "five_year_median": "38.5", "percentile": 68},
            {"metric": ValuationMetricName.FORWARD_PER, "value": "31.4", "five_year_median": "34.1", "percentile": 42},
            {"metric": ValuationMetricName.PSR, "value": "8.7", "five_year_median": "7.9", "percentile": 61},
            {"metric": ValuationMetricName.PBR, "value": "12.2", "five_year_median": "10.8", "percentile": 65},
            {"metric": ValuationMetricName.EV_EBITDA, "value": "24.6", "five_year_median": "22.9", "percentile": 57},
            {"metric": ValuationMetricName.PEG, "value": "1.6", "five_year_median": "1.9", "percentile": 35},
            {"metric": ValuationMetricName.FCF_YIELD, "value": "2.8", "five_year_median": "2.5", "percentile": 54},
        ),
    },
    {
        "profile": ValuationProfile.GENERAL,
        "highlighted_metrics": (
            ValuationMetricName.PER,
            ValuationMetricName.PBR,
            ValuationMetricName.EV_EBITDA,
        ),
        "metrics": (
            {"metric": ValuationMetricName.PER, "value": "18.3", "five_year_median": "20.1", "percentile": 37},
            {"metric": ValuationMetricName.FORWARD_PER, "value": "16.9", "five_year_median": "18.4", "percentile": 34},
            {"metric": ValuationMetricName.PSR, "value": "2.4", "five_year_median": "2.7", "percentile": 31},
            {"metric": ValuationMetricName.PBR, "value": "3.1", "five_year_median": "3.4", "percentile": 39},
            {"metric": ValuationMetricName.EV_EBITDA, "value": "11.7", "five_year_median": "12.8", "percentile": 33},
            {"metric": ValuationMetricName.PEG, "value": "1.2", "five_year_median": "1.4", "percentile": 28},
            {"metric": ValuationMetricName.FCF_YIELD, "value": "5.4", "five_year_median": "4.8", "percentile": 63},
        ),
    },
    {
        "profile": ValuationProfile.DEFICIT,
        "highlighted_metrics": (
            ValuationMetricName.PSR,
            ValuationMetricName.FCF_YIELD,
        ),
        "metrics": (
            {"metric": ValuationMetricName.PER, "value": None, "five_year_median": None, "percentile": None},
            {"metric": ValuationMetricName.FORWARD_PER, "value": None, "five_year_median": None, "percentile": None},
            {"metric": ValuationMetricName.PSR, "value": "5.6", "five_year_median": "7.2", "percentile": 24},
            {"metric": ValuationMetricName.PBR, "value": "4.8", "five_year_median": "6.1", "percentile": 29},
            {"metric": ValuationMetricName.EV_EBITDA, "value": None, "five_year_median": None, "percentile": None},
            {"metric": ValuationMetricName.PEG, "value": None, "five_year_median": None, "percentile": None},
            {"metric": ValuationMetricName.FCF_YIELD, "value": "-3.2", "five_year_median": "-5.1", "percentile": 71},
        ),
    },
)


class ValuationService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)

    def get_metrics(self, asset_id: int) -> ValuationMetricsResponse:
        asset = self.asset_repo.get_by_id(asset_id)
        if asset is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )

        template = _TEMPLATES[asset.id % len(_TEMPLATES)]
        return ValuationMetricsResponse(
            asset_id=asset.id,
            profile=template["profile"],
            highlighted_metrics=list(template["highlighted_metrics"]),
            metrics=[self._metric_from_template(item) for item in template["metrics"]],
        )

    @staticmethod
    def _metric_from_template(template: _MetricTemplate) -> ValuationMetric:
        return ValuationMetric(
            metric=template["metric"],
            value=Decimal(template["value"]) if template["value"] is not None else None,
            five_year_median=(
                Decimal(template["five_year_median"])
                if template["five_year_median"] is not None
                else None
            ),
            percentile=template["percentile"],
        )
