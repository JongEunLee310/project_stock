from decimal import Decimal
from typing import TypedDict

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.earnings.schema import (
    EarningsQuarter,
    EarningsSummaryResponse,
    SegmentGrowth,
)


class _QuarterTemplate(TypedDict):
    period: str
    revenue: str
    operating_income: str
    eps: str
    revenue_yoy_percent: str | None
    eps_estimate: str | None


class _SegmentTemplate(TypedDict):
    name: str
    revenue_share_percent: str
    yoy_growth_percent: str


class _EarningsTemplate(TypedDict):
    quarters: tuple[_QuarterTemplate, ...]
    guidance: str | None
    segments: tuple[_SegmentTemplate, ...]


_TEMPLATES: tuple[_EarningsTemplate, ...] = (
    {
        "quarters": (
            {"period": "2025Q2", "revenue": "94800", "operating_income": "28440", "eps": "1.48", "revenue_yoy_percent": "8.2", "eps_estimate": "1.42"},
            {"period": "2025Q3", "revenue": "97200", "operating_income": "28200", "eps": "1.41", "revenue_yoy_percent": "7.1", "eps_estimate": "1.46"},
            {"period": "2025Q4", "revenue": "101500", "operating_income": "31465", "eps": "1.62", "revenue_yoy_percent": "9.4", "eps_estimate": None},
            {"period": "2026Q1", "revenue": "104300", "operating_income": "33376", "eps": "1.71", "revenue_yoy_percent": "10.3", "eps_estimate": "1.65"},
        ),
        "guidance": "다음 분기 매출은 전년 동기 대비 한 자릿수 후반 성장하고 영업이익률은 안정적으로 유지될 전망입니다.",
        "segments": (
            {"name": "플랫폼", "revenue_share_percent": "62", "yoy_growth_percent": "12.4"},
            {"name": "서비스", "revenue_share_percent": "38", "yoy_growth_percent": "7.2"},
        ),
    },
    {
        "quarters": (
            {"period": "2025Q2", "revenue": "28600", "operating_income": "3146", "eps": "0.82", "revenue_yoy_percent": "4.1", "eps_estimate": "0.79"},
            {"period": "2025Q3", "revenue": "27900", "operating_income": "2511", "eps": "0.68", "revenue_yoy_percent": "-1.8", "eps_estimate": "0.73"},
            {"period": "2025Q4", "revenue": "30100", "operating_income": "3311", "eps": "0.88", "revenue_yoy_percent": None, "eps_estimate": None},
            {"period": "2026Q1", "revenue": "31500", "operating_income": "3780", "eps": "0.96", "revenue_yoy_percent": "6.7", "eps_estimate": "0.91"},
        ),
        "guidance": None,
        "segments": (
            {"name": "국내", "revenue_share_percent": "55", "yoy_growth_percent": "3.8"},
            {"name": "해외", "revenue_share_percent": "45", "yoy_growth_percent": "10.5"},
        ),
    },
)


class EarningsService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)

    def get_summary(self, asset_id: int) -> EarningsSummaryResponse:
        asset = self.asset_repo.get_by_id(asset_id)
        if asset is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )

        template = _TEMPLATES[asset.id % len(_TEMPLATES)]
        return EarningsSummaryResponse(
            asset_id=asset.id,
            quarters=[self._quarter_from_template(item) for item in template["quarters"]],
            guidance=template["guidance"],
            segments=[SegmentGrowth.model_validate(item) for item in template["segments"]],
        )

    @staticmethod
    def _quarter_from_template(template: _QuarterTemplate) -> EarningsQuarter:
        revenue = Decimal(template["revenue"])
        operating_income = Decimal(template["operating_income"])
        eps = Decimal(template["eps"])
        estimate = (
            Decimal(template["eps_estimate"])
            if template["eps_estimate"] is not None
            else None
        )
        surprise = None
        if estimate is not None and estimate != 0:
            surprise = ((eps - estimate) / abs(estimate) * 100).quantize(
                Decimal("0.01")
            )
        return EarningsQuarter(
            period=template["period"],
            revenue=revenue,
            operating_income=operating_income,
            eps=eps,
            revenue_yoy_percent=(
                Decimal(template["revenue_yoy_percent"])
                if template["revenue_yoy_percent"] is not None
                else None
            ),
            operating_margin_percent=(
                operating_income / revenue * 100
            ).quantize(Decimal("0.01")),
            eps_estimate=estimate,
            eps_surprise_percent=surprise,
        )
