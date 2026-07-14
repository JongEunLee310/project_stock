from sqlalchemy.orm import Session

from app.adapters.disclosure.base import DisclosureProvider
from app.adapters.factory import get_disclosure_provider
from app.domains.news.categorizer import categorize
from app.domains.news.repository import NewsItemRepository
from app.domains.news.schema import (
    DisclosureItemProjection,
    NewsDisclosureResponse,
    NewsItemProjection,
)


class NewsDisclosureService:
    def __init__(
        self,
        db: Session,
        disclosure_provider: DisclosureProvider | None = None,
    ) -> None:
        self.news_repository = NewsItemRepository(db)
        self.disclosure_provider = (
            get_disclosure_provider()
            if disclosure_provider is None
            else disclosure_provider
        )

    def get_news_and_disclosures(
        self,
        asset_id: int,
        symbol: str,
        limit: int = 20,
    ) -> NewsDisclosureResponse:
        news_items = self.news_repository.list_by_asset_with_limit(asset_id, limit)
        disclosures = sorted(
            self.disclosure_provider.fetch([symbol]),
            key=lambda item: (
                float("-inf")
                if item.published_at is None
                else item.published_at.timestamp()
            ),
            reverse=True,
        )[:limit]
        return NewsDisclosureResponse(
            asset_id=asset_id,
            news=[NewsItemProjection.model_validate(item) for item in news_items],
            disclosures=[
                DisclosureItemProjection(
                    title=item.title,
                    url=item.url,
                    source=item.source,
                    published_at=item.published_at,
                    category=categorize(item.title, None),
                    impact_level=None,
                    summary=None,
                )
                for item in disclosures
            ],
        )
