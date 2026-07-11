from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.news.model import NewsItem
from app.domains.prices.model import StockPriceBar
from app.domains.research_coverage.schema import (
    CoverageAxis,
    CoverageAxisName,
    CoverageStatus,
    ResearchCoverageResponse,
)


class ResearchCoverageService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.asset_repo = AssetRepository(db)

    def get_coverage(self, asset_id: int) -> ResearchCoverageResponse:
        asset = self.asset_repo.get_by_id(asset_id)
        if asset is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )

        news_count, news_last_updated_at = self._news_coverage(asset.id)
        price_count, price_last_updated_at = self._price_coverage(
            asset.symbol,
            asset.market,
        )
        return ResearchCoverageResponse(
            asset_id=asset.id,
            axes=[
                self._collected_axis(
                    CoverageAxisName.NEWS,
                    news_count,
                    news_last_updated_at,
                ),
                self._collected_axis(
                    CoverageAxisName.PRICE,
                    price_count,
                    price_last_updated_at,
                ),
                self._not_collected_axis(CoverageAxisName.EARNINGS),
                self._not_collected_axis(CoverageAxisName.VALUATION),
                self._not_collected_axis(CoverageAxisName.DISCLOSURE),
            ],
        )

    def _news_coverage(self, asset_id: int) -> tuple[int, datetime | None]:
        # updated_at reflects post-insert enrichment as well as initial collection.
        stmt = select(func.count(NewsItem.id), func.max(NewsItem.updated_at)).where(
            NewsItem.asset_id == asset_id
        )
        item_count, last_updated_at = self.db.execute(stmt).one()
        return item_count, last_updated_at

    def _price_coverage(
        self,
        symbol: str,
        market: str,
    ) -> tuple[int, datetime | None]:
        # Price upserts update existing bars without changing created_at.
        stmt = select(
            func.count(StockPriceBar.id),
            func.max(StockPriceBar.updated_at),
        ).where(
            StockPriceBar.symbol == symbol,
            StockPriceBar.market == market,
        )
        item_count, last_updated_at = self.db.execute(stmt).one()
        return item_count, last_updated_at

    @staticmethod
    def _collected_axis(
        axis: CoverageAxisName,
        item_count: int,
        last_updated_at: datetime | None,
    ) -> CoverageAxis:
        if item_count == 0:
            return ResearchCoverageService._not_collected_axis(axis)
        return CoverageAxis(
            axis=axis,
            status=CoverageStatus.COLLECTED,
            last_updated_at=last_updated_at,
            item_count=item_count,
        )

    @staticmethod
    def _not_collected_axis(axis: CoverageAxisName) -> CoverageAxis:
        return CoverageAxis(
            axis=axis,
            status=CoverageStatus.NOT_COLLECTED,
            last_updated_at=None,
            item_count=0,
        )
