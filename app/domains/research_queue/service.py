import json
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.domains.research_queue.repository import ResearchQueueRepository
from app.domains.research_queue.schema import (
    ResearchQueueFilter,
    ResearchQueueItemProjection,
    ResearchQueueSummaryProjection,
    ResearchStatus,
)
from app.domains.research_summary.service import ResearchSummaryService
from app.domains.signals.time import as_utc, utc_now
from app.domains.signals.types import WATCHLIST_STATUS_PRIORITY

_RISK_SIGNAL_TYPES = {"RISK_ALERT", "THESIS_BROKEN"}
_NEEDS_RESEARCH_STATUSES = {
    ResearchStatus.NEEDS_ATTENTION,
    ResearchStatus.INSUFFICIENT,
    ResearchStatus.COLLECTING,
    ResearchStatus.PENDING_ANALYSIS,
}


class ResearchQueueService:
    def __init__(self, db: Session) -> None:
        self.repository = ResearchQueueRepository(db)
        self.summary_service = ResearchSummaryService(db)

    def list_queue(
        self,
        filter: str | None,
        offset: int,
        limit: int,
    ) -> tuple[
        list[ResearchQueueItemProjection],
        ResearchQueueSummaryProjection,
        int,
    ]:
        now = utc_now()
        today_start = datetime.combine(now.date(), datetime.min.time(), tzinfo=UTC)
        assets = self.repository.list_active_assets()
        asset_ids = [asset.id for asset in assets]
        presence_by_id = self.repository.get_data_presence_by_assets(assets)
        signal_types_by_id = self.repository.get_active_signal_types_by_assets(asset_ids)
        signal_reasons_by_id = self.repository.get_top_signal_reason_by_assets(asset_ids)
        report_factors_by_id = self.repository.get_latest_report_negative_factors(asset_ids)
        upcoming_asset_ids = (
            self.repository.get_earnings_upcoming_assets(assets)
            if filter == ResearchQueueFilter.EARNINGS_UPCOMING.value
            else set()
        )

        items: list[ResearchQueueItemProjection] = []
        for asset in assets:
            presence = presence_by_id[asset.id]
            signal_types = signal_types_by_id.get(asset.id, set())
            completeness = self._derive_completeness(
                presence.has_news,
                presence.has_price,
                presence.has_earnings,
                presence.has_valuation,
            )
            last_updated_at = self._derive_last_updated_at(
                presence.latest_news_at,
                presence.latest_report_at,
                presence.latest_signal_at,
            )
            summary = self.summary_service.get_summary(asset.id)
            items.append(
                ResearchQueueItemProjection(
                    asset_id=asset.id,
                    symbol=asset.symbol,
                    name=asset.name,
                    market=asset.market,
                    research_status=self._derive_status(
                        completeness,
                        signal_types,
                        last_updated_at,
                        now,
                    ),
                    completeness_pct=completeness,
                    stance=summary.stance,
                    headline=summary.headline,
                    key_issue=self._derive_key_issue(
                        signal_reasons_by_id.get(asset.id),
                        report_factors_by_id.get(asset.id),
                    ),
                    last_updated_at=last_updated_at,
                    signal_type=self._top_signal_type(signal_types),
                )
            )

        summary_projection = self._build_summary(items, today_start)
        filtered_items = self._apply_filter(
            items,
            filter,
            upcoming_asset_ids,
            today_start,
        )
        total = len(filtered_items)
        return filtered_items[offset : offset + limit], summary_projection, total

    def _derive_status(
        self,
        completeness_pct: int,
        active_signal_types: set[str],
        last_updated_at: datetime | None,
        now: datetime,
    ) -> ResearchStatus:
        if active_signal_types & _RISK_SIGNAL_TYPES:
            return ResearchStatus.NEEDS_ATTENTION
        if completeness_pct < 30:
            return ResearchStatus.INSUFFICIENT
        if completeness_pct < 70:
            return ResearchStatus.COLLECTING
        if last_updated_at is None:
            return ResearchStatus.PENDING_ANALYSIS
        if (
            as_utc(last_updated_at) < as_utc(now) - timedelta(days=30)
        ):
            return ResearchStatus.STALE
        return ResearchStatus.ANALYZED

    def _derive_completeness(
        self,
        has_news: bool,
        has_price: bool,
        has_earnings: bool,
        has_valuation: bool,
    ) -> int:
        return 25 * sum((has_news, has_price, has_earnings, has_valuation))

    def _derive_key_issue(
        self,
        top_signal_reason: str | None,
        latest_report_negative_factors: str | None,
    ) -> str | None:
        if top_signal_reason:
            return self._first_sentence(top_signal_reason)
        if not latest_report_negative_factors:
            return None
        try:
            factors = json.loads(latest_report_negative_factors)
        except (json.JSONDecodeError, TypeError):
            factors = [latest_report_negative_factors]
        if not isinstance(factors, list) or not factors or not isinstance(factors[0], str):
            return None
        return self._first_sentence(factors[0])

    def _derive_last_updated_at(
        self,
        news_at: datetime | None,
        report_at: datetime | None,
        signal_at: datetime | None,
    ) -> datetime | None:
        values = [value for value in (news_at, report_at, signal_at) if value is not None]
        return max(values, key=as_utc) if values else None

    def _build_summary(
        self,
        items: list[ResearchQueueItemProjection],
        today_start: datetime,
    ) -> ResearchQueueSummaryProjection:
        return ResearchQueueSummaryProjection(
            total_research_count=len(items),
            needs_attention_count=sum(
                item.research_status == ResearchStatus.NEEDS_ATTENTION for item in items
            ),
            updated_today_count=sum(
                item.last_updated_at is not None
                and as_utc(item.last_updated_at) >= today_start
                for item in items
            ),
            insufficient_count=sum(
                item.research_status == ResearchStatus.INSUFFICIENT for item in items
            ),
        )

    def _apply_filter(
        self,
        items: list[ResearchQueueItemProjection],
        filter: str | None,
        upcoming_asset_ids: set[int],
        today_start: datetime,
    ) -> list[ResearchQueueItemProjection]:
        if filter is None:
            return items
        if filter == ResearchQueueFilter.NEEDS_RESEARCH.value:
            return [item for item in items if item.research_status in _NEEDS_RESEARCH_STATUSES]
        if filter == ResearchQueueFilter.RISK_INCREASING.value:
            return [item for item in items if item.research_status == ResearchStatus.NEEDS_ATTENTION]
        if filter == ResearchQueueFilter.EARNINGS_UPCOMING.value:
            return [item for item in items if item.asset_id in upcoming_asset_ids]
        if filter == ResearchQueueFilter.RECENTLY_UPDATED.value:
            return [
                item
                for item in items
                if item.last_updated_at is not None
                and as_utc(item.last_updated_at) >= today_start
            ]
        return []

    @staticmethod
    def _top_signal_type(signal_types: set[str]) -> str | None:
        for signal_type in WATCHLIST_STATUS_PRIORITY:
            if signal_type.value in signal_types:
                return signal_type.value
        return None

    @staticmethod
    def _first_sentence(value: str) -> str:
        stripped = value.strip()
        terminators = [index for mark in ".!?。！？" if (index := stripped.find(mark)) >= 0]
        return stripped[: min(terminators) + 1] if terminators else stripped
