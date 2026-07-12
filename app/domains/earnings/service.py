from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.earnings.model import EarningsReport
from app.domains.earnings.repository import EarningsRepository
from app.domains.earnings.schema import EarningsQuarter, EarningsSummaryResponse

_PERCENT_PRECISION = Decimal("0.01")


class EarningsService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.earnings_repo = EarningsRepository(db)

    def get_summary(self, asset_id: int) -> EarningsSummaryResponse:
        asset = self.asset_repo.get_by_id(asset_id)
        if asset is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )

        reports = self.earnings_repo.get_recent(asset.symbol, asset.market, 8)
        by_period = {report.period: report for report in reports}
        complete_reports = [
            report
            for report in reports
            if report.revenue is not None
            and report.revenue != 0
            and report.operating_income is not None
            and report.eps is not None
        ][:4]
        quarters = [
            self._quarter(report, by_period)
            for report in reversed(complete_reports)
        ]
        return EarningsSummaryResponse(
            asset_id=asset.id,
            quarters=quarters,
            guidance=None,
            segments=[],
        )

    @staticmethod
    def _quarter(
        report: EarningsReport,
        by_period: dict[str, EarningsReport],
    ) -> EarningsQuarter:
        assert report.revenue is not None
        assert report.operating_income is not None
        assert report.eps is not None
        previous = by_period.get(_previous_year_period(report.period))
        revenue_yoy = None
        if (
            previous is not None
            and previous.revenue is not None
            and previous.revenue != 0
        ):
            revenue_yoy = (
                (report.revenue / previous.revenue - 1) * 100
            ).quantize(_PERCENT_PRECISION)
        surprise = None
        if report.eps_estimate is not None and report.eps_estimate != 0:
            surprise = (
                (report.eps - report.eps_estimate)
                / abs(report.eps_estimate)
                * 100
            ).quantize(_PERCENT_PRECISION)
        return EarningsQuarter(
            period=report.period,
            revenue=report.revenue,
            operating_income=report.operating_income,
            eps=report.eps,
            revenue_yoy_percent=revenue_yoy,
            operating_margin_percent=(
                report.operating_income / report.revenue * 100
            ).quantize(_PERCENT_PRECISION),
            eps_estimate=report.eps_estimate,
            eps_surprise_percent=surprise,
        )


def _previous_year_period(period: str) -> str:
    return f"{int(period[:4]) - 1}{period[4:]}"
