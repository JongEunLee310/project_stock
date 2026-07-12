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
from app.domains.benchmark.sector_map import resolve_sector_etf
from app.domains.prices.repository import PriceBarRepository

_RANGE_DELTAS: dict[BenchmarkRange, timedelta] = {
    BenchmarkRange.ONE_MONTH: timedelta(days=31),
    BenchmarkRange.THREE_MONTHS: timedelta(days=92),
    BenchmarkRange.SIX_MONTHS: timedelta(days=183),
    BenchmarkRange.ONE_YEAR: timedelta(days=366),
}
_PERCENT_QUANTUM = Decimal("0.01")


class BenchmarkService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.price_repo = PriceBarRepository(db)

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

        sector_symbol, sector_market, sector_label = resolve_sector_etf(asset.sector)
        series_specs = [
            (BenchmarkSeriesKind.ASSET, asset.symbol, asset.symbol, asset.market),
            (BenchmarkSeriesKind.INDEX, "NASDAQ 100", "QQQ", "NASDAQ"),
            (
                BenchmarkSeriesKind.SECTOR_ETF,
                sector_label,
                sector_symbol,
                sector_market,
            ),
        ]
        closes_by_kind = {
            kind: dict(self.price_repo.get_daily_closes(symbol, market, start=None))
            for kind, _, symbol, market in series_specs
        }
        dates = self._common_dates(closes_by_kind, range_)

        return BenchmarkComparisonResponse(
            asset_id=asset.id,
            range=range_,
            series=[
                self._series(kind, label, dates, closes_by_kind[kind])
                for kind, label, _, _ in series_specs
            ],
        )

    @staticmethod
    def _common_dates(
        closes_by_kind: dict[BenchmarkSeriesKind, dict[date, Decimal]],
        range_: BenchmarkRange,
    ) -> list[date]:
        common_dates = set.intersection(
            *(set(closes) for closes in closes_by_kind.values())
        )
        if not common_dates:
            return []
        reference_date = max(common_dates)
        start_date = reference_date - _RANGE_DELTAS[range_]
        return sorted(point_date for point_date in common_dates if point_date >= start_date)

    @staticmethod
    def _series(
        kind: BenchmarkSeriesKind,
        label: str,
        dates: list[date],
        closes: dict[date, Decimal],
    ) -> BenchmarkSeries:
        if not dates:
            return BenchmarkSeries(kind=kind, label=label, points=[])
        initial_close = closes[dates[0]]
        points = [
            BenchmarkPoint(
                date=point_date,
                return_percent=(
                    (closes[point_date] / initial_close - Decimal("1"))
                    * Decimal("100")
                ).quantize(_PERCENT_QUANTUM),
            )
            for point_date in dates
        ]
        return BenchmarkSeries(kind=kind, label=label, points=points)
