from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.benchmark.schema import (
    BenchmarkComparisonResponse,
    BenchmarkPoint,
    BenchmarkRange,
    BenchmarkSeries,
    BenchmarkSeriesKind,
)

_END_DATE = date(2026, 7, 10)
_POINT_COUNTS: dict[str, int] = {
    BenchmarkRange.ONE_MONTH.value: 21,
    BenchmarkRange.THREE_MONTHS.value: 63,
    BenchmarkRange.SIX_MONTHS.value: 126,
    BenchmarkRange.ONE_YEAR.value: 252,
}


class BenchmarkService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)

    def get_comparison(
        self,
        asset_id: int,
        range_: BenchmarkRange,
    ) -> BenchmarkComparisonResponse:
        asset = self.asset_repo.get_by_id(asset_id)
        if asset is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )

        dates = self._business_dates(_POINT_COUNTS[range_.value])
        return BenchmarkComparisonResponse(
            asset_id=asset.id,
            range=range_,
            series=[
                self._series(
                    kind=BenchmarkSeriesKind.ASSET,
                    label=asset.symbol,
                    dates=dates,
                    asset_id=asset.id,
                    range_=range_,
                ),
                self._series(
                    kind=BenchmarkSeriesKind.INDEX,
                    label="NASDAQ 100",
                    dates=dates,
                    asset_id=asset.id,
                    range_=range_,
                ),
                self._series(
                    kind=BenchmarkSeriesKind.SECTOR_ETF,
                    label="XLK",
                    dates=dates,
                    asset_id=asset.id,
                    range_=range_,
                ),
            ],
        )

    @staticmethod
    def _business_dates(count: int) -> list[date]:
        dates: list[date] = []
        current = _END_DATE
        while len(dates) < count:
            if current.weekday() < 5:
                dates.append(current)
            current -= timedelta(days=1)
        return list(reversed(dates))

    @staticmethod
    def _series(
        *,
        kind: BenchmarkSeriesKind,
        label: str,
        dates: list[date],
        asset_id: int,
        range_: BenchmarkRange,
    ) -> BenchmarkSeries:
        kind_index = list(BenchmarkSeriesKind).index(kind)
        range_index = list(BenchmarkRange).index(range_)
        slope = Decimal("0.035") + Decimal(kind_index) * Decimal("0.009")
        slope += Decimal((asset_id + range_index) % 7) * Decimal("0.002")
        volatility = Decimal("0.04") + Decimal(kind_index) * Decimal("0.01")
        points = [
            BenchmarkPoint(
                date=point_date,
                return_percent=BenchmarkService._return_percent(
                    index,
                    slope,
                    volatility,
                    asset_id,
                    kind_index,
                ),
            )
            for index, point_date in enumerate(dates)
        ]
        return BenchmarkSeries(kind=kind, label=label, points=points)

    @staticmethod
    def _return_percent(
        index: int,
        slope: Decimal,
        volatility: Decimal,
        asset_id: int,
        kind_index: int,
    ) -> Decimal:
        if index == 0:
            return Decimal("0")
        wave = Decimal((index + asset_id + kind_index) % 9 - 4) * volatility
        return (Decimal(index) * slope + wave).quantize(Decimal("0.01"))
