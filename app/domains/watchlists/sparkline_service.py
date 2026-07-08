from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.prices.service import PriceSeriesService
from app.domains.watchlists.repository import WatchlistItemRepository
from app.domains.watchlists.schema import (
    AssetSparklineResponse,
    SparklineBar,
    WatchlistSparklineResponse,
)
from app.domains.watchlists.service import WatchlistService


class WatchlistSparklineService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.item_repo = WatchlistItemRepository(db)
        self.price_series_service = PriceSeriesService(db)
        self.watchlist_service = WatchlistService(db)

    def get_sparklines(
        self,
        watchlist_id: int,
        user_id: int,
        range_value: str = "1M",
    ) -> WatchlistSparklineResponse:
        watchlist = self.watchlist_service._get_owned_watchlist(watchlist_id, user_id)
        items = self.item_repo.list_by_watchlist(watchlist.id)
        asset_ids = [item.asset_id for item in items]
        assets = {asset.id: asset for asset in self.asset_repo.list_by_ids(asset_ids)}

        response_items: list[AssetSparklineResponse] = []
        for item in items:
            asset = assets.get(item.asset_id)
            if asset is None:
                continue
            try:
                series = self.price_series_service.get_series(
                    symbol=asset.symbol,
                    market=asset.market,
                    range_value=range_value,
                    interval="1d",
                )
            except AppException as exc:
                if (
                    exc.status_code == 404
                    and exc.error_code == ErrorCode.PRICE_SERIES_NOT_FOUND
                ):
                    continue
                raise
            response_items.append(
                AssetSparklineResponse(
                    symbol=asset.symbol,
                    bars=[
                        SparklineBar(date=bar.date, close=bar.close)
                        for bar in series.bars
                    ],
                )
            )

        return WatchlistSparklineResponse(items=response_items)
