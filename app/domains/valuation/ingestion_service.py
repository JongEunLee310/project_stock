from dataclasses import dataclass
import logging

from sqlalchemy.orm import Session

from app.adapters.market.base import ValuationProvider
from app.domains.valuation.repository import ValuationRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValuationIngestionResult:
    target_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    saved_count: int = 0


class ValuationIngestionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = ValuationRepository(db)

    def collect_and_save(
        self,
        provider: ValuationProvider,
        targets: list[tuple[str, str]],
    ) -> ValuationIngestionResult:
        success_count = failure_count = saved_count = 0
        for symbol, market in targets:
            normalized_symbol = symbol.upper()
            normalized_market = market.upper()
            try:
                result = provider.get_valuation(normalized_symbol, normalized_market)
                if result is None:
                    failure_count += 1
                    continue
                self.repository.upsert(normalized_symbol, normalized_market, result)
                success_count += 1
                saved_count += 1
            except Exception:
                self.db.rollback()
                logger.exception(
                    "Failed to collect valuation target",
                    extra={"symbol": normalized_symbol, "market": normalized_market},
                )
                failure_count += 1
        return ValuationIngestionResult(
            target_count=len(targets),
            success_count=success_count,
            failure_count=failure_count,
            saved_count=saved_count,
        )
