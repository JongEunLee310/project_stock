from dataclasses import dataclass
import logging

from sqlalchemy.orm import Session

from app.adapters.news.base import NewsAdapter
from app.domains.raw_news.service import RawNewsService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    target_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    received_count: int = 0
    saved_count: int = 0
    skipped_count: int = 0


class NewsIngestionService:
    def __init__(self, db: Session) -> None:
        self.raw_news_service = RawNewsService(db)

    def collect_and_save(
        self,
        adapter: NewsAdapter,
        targets: list[tuple[str, str, str]],
    ) -> IngestionResult:
        result = IngestionResult(target_count=len(targets))
        for symbol, market, name in targets:
            result = self._collect_target(adapter, symbol, market, name, result)
        return result

    def _collect_target(
        self,
        adapter: NewsAdapter,
        symbol: str,
        market: str,
        name: str,
        result: IngestionResult,
    ) -> IngestionResult:
        normalized_symbol = symbol.upper()
        normalized_market = market.upper()
        try:
            entries = adapter.fetch_query(name, normalized_market)
        except Exception:
            logger.exception(
                "Failed to collect news target",
                extra={
                    "symbol": normalized_symbol,
                    "market": normalized_market,
                    "company_name": name,
                },
            )
            return IngestionResult(
                target_count=result.target_count,
                success_count=result.success_count,
                failure_count=result.failure_count + 1,
                received_count=result.received_count,
                saved_count=result.saved_count,
                skipped_count=result.skipped_count,
            )

        saved_count = 0
        skipped_count = 0
        for entry in entries:
            event = self.raw_news_service.save_with_symbol(
                entry,
                normalized_symbol,
                normalized_market,
            )
            if event is None:
                skipped_count += 1
            else:
                saved_count += 1

        return IngestionResult(
            target_count=result.target_count,
            success_count=result.success_count + 1,
            failure_count=result.failure_count,
            received_count=result.received_count + len(entries),
            saved_count=result.saved_count + saved_count,
            skipped_count=result.skipped_count + skipped_count,
        )
