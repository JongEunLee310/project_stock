from dataclasses import dataclass
import logging

from sqlalchemy.orm import Session

from app.adapters.market.base import EarningsProvider
from app.domains.earnings.repository import EarningsRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EarningsIngestionResult:
    target_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    saved_count: int = 0
    report_success_count: int = 0
    report_failure_count: int = 0
    event_success_count: int = 0
    event_failure_count: int = 0


class EarningsIngestionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = EarningsRepository(db)

    def collect_and_save(
        self,
        provider: EarningsProvider,
        targets: list[tuple[str, str]],
    ) -> EarningsIngestionResult:
        success_count = failure_count = saved_count = 0
        report_success_count = report_failure_count = 0
        event_success_count = event_failure_count = 0
        for symbol, market in targets:
            normalized_symbol = symbol.upper()
            normalized_market = market.upper()
            reports_saved = False
            try:
                reports = provider.get_quarterly_earnings(
                    normalized_symbol, normalized_market
                )
                if not reports:
                    failure_count += 1
                    report_failure_count += 1
                    continue
                for report in reports[:8]:
                    self.repository.upsert(
                        normalized_symbol, normalized_market, report
                    )
                    saved_count += 1
                report_success_count += 1
                reports_saved = True
                events = provider.get_earnings_events(
                    normalized_symbol, normalized_market
                )
                if not events:
                    failure_count += 1
                    event_failure_count += 1
                    continue
                for event in events:
                    self.repository.upsert_event(
                        normalized_symbol, normalized_market, event
                    )
                    saved_count += 1
                event_success_count += 1
                success_count += 1
            except Exception:
                self.db.rollback()
                logger.exception(
                    "Failed to collect earnings target",
                    extra={"symbol": normalized_symbol, "market": normalized_market},
                )
                failure_count += 1
                if reports_saved:
                    event_failure_count += 1
                else:
                    report_failure_count += 1
        return EarningsIngestionResult(
            target_count=len(targets),
            success_count=success_count,
            failure_count=failure_count,
            saved_count=saved_count,
            report_success_count=report_success_count,
            report_failure_count=report_failure_count,
            event_success_count=event_success_count,
            event_failure_count=event_failure_count,
        )
