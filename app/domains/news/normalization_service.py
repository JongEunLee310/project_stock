import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.domains.assets.repository import AssetRepository
from app.domains.ingestion.schema import DataQualityStatus
from app.domains.news.model import NewsItem
from app.domains.news.normalizer import NewsNormalizer
from app.domains.news.repository import NewsItemRepository
from app.domains.news.validator import NewsValidator
from app.domains.raw_news.model import RawNewsEvent
from app.domains.raw_news.repository import RawNewsEventRepository

logger = logging.getLogger(__name__)


class NewsNormalizationService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.news_repo = NewsItemRepository(db)
        self.raw_news_repo = RawNewsEventRepository(db)
        self.normalizer = NewsNormalizer()
        self.validator = NewsValidator()

    def normalize_event(self, event: RawNewsEvent) -> NewsItem | None:
        if event.symbol is None or event.market is None:
            logger.warning(
                "Skipping news normalization without symbol or market",
                extra={"raw_news_event_id": event.id},
            )
            return None

        symbol = self.normalizer.canonicalize_symbol(event.symbol)
        market = self.normalizer.canonicalize_market(event.market)
        asset = self.asset_repo.get_by_symbol_market(symbol, market)
        if asset is None:
            logger.warning(
                "Skipping news normalization for unresolved asset",
                extra={
                    "raw_news_event_id": event.id,
                    "symbol": symbol,
                    "market": market,
                },
            )
            return None

        data = self.normalizer.to_news_item_create(event, asset.id)
        validation = self.validator.validate(data, now=datetime.now(UTC))
        if validation.status == DataQualityStatus.INVALID:
            logger.warning(
                "Marking news normalization failed due to invalid data",
                extra={
                    "raw_news_event_id": event.id,
                    "validation_reasons": [reason.value for reason in validation.reasons],
                },
            )
            self.raw_news_repo.mark_failed(event.id)
            return None

        if self.news_repo.exists_by_url(data.url):
            self.raw_news_repo.mark_normalized(event.id)
            return None

        item = self.news_repo.create(data)
        self.raw_news_repo.mark_normalized(event.id)
        return item
