from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.domains.signals.repository import SignalRepository
from app.domains.signals.time import as_utc, utc_now
from app.domains.signals.types import SignalType
from app.domains.watchlists.repository import WatchlistItemRepository
from app.domains.watchlists.schema import (
    WatchlistSummaryTrendDataPoint,
    WatchlistSummaryTrendResponse,
    WatchlistSummaryTrendSeries,
)
from app.domains.watchlists.service import WatchlistService

WATCHLIST_TOTAL_KEY = "watchlist_total"
RISK_INCREASING_KEY = "risk_increasing"


class WatchlistSummaryTrendService:
    def __init__(self, db: Session) -> None:
        self.item_repo = WatchlistItemRepository(db)
        self.signal_repo = SignalRepository(db)
        self.watchlist_service = WatchlistService(db)

    def get_trends(
        self,
        watchlist_id: int,
        user_id: int,
        days: int,
    ) -> WatchlistSummaryTrendResponse:
        watchlist = self.watchlist_service._get_owned_watchlist(watchlist_id, user_id)
        now = utc_now()
        today = now.date()
        start_date = today - timedelta(days=days - 1)
        dates = [start_date + timedelta(days=offset) for offset in range(days)]

        items = self.item_repo.list_by_watchlist(watchlist.id)
        item_snapshots = [(item.asset_id, item.created_at) for item in items]
        asset_ids = [asset_id for asset_id, _ in item_snapshots]

        total_by_date: dict[str, int] = {}
        risk_by_date: dict[str, int] = {}
        for day in dates:
            as_of = self._as_of_at(day, today, now)
            total_by_date[day.isoformat()] = sum(
                1 for _, created_at in item_snapshots if as_utc(created_at) <= as_utc(as_of)
            )
            risk_by_date[day.isoformat()] = (
                self.signal_repo.count_assets_with_active_signal_as_of(
                    asset_ids,
                    SignalType.RISK_ALERT.value,
                    as_of,
                )
            )

        return WatchlistSummaryTrendResponse(
            days=days,
            series=[
                self._build_series(WATCHLIST_TOTAL_KEY, total_by_date, dates),
                self._build_series(RISK_INCREASING_KEY, risk_by_date, dates),
            ],
        )

    def _as_of_at(self, day: date, today: date, now: datetime) -> datetime:
        if day == today:
            return now
        return datetime.combine(day + timedelta(days=1), time.min, tzinfo=timezone.utc)

    def _build_series(
        self,
        key: str,
        counts_by_date: dict[str, int],
        dates: list[date],
    ) -> WatchlistSummaryTrendSeries:
        return WatchlistSummaryTrendSeries(
            key=key,
            data=[
                WatchlistSummaryTrendDataPoint(
                    date=day.isoformat(),
                    count=counts_by_date.get(day.isoformat(), 0),
                )
                for day in dates
            ],
        )
