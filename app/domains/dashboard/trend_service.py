from datetime import date, datetime, time, timedelta, timezone
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.alert_candidates.model import AlertCandidate
from app.domains.alert_candidates.types import AlertCandidateType, AlertImportance
from app.domains.alerts.model import Alert
from app.domains.dashboard.schema import (
    DashboardTrendSeriesResponse,
    TrendDataPoint,
    TrendSeries,
)
from app.domains.signals.model import Signal
from app.domains.signals.time import utc_now
from app.domains.signals.types import SignalType


RISK_ALERTS_KEY = "risk_alerts"
REVIEW_SIGNALS_KEY = "review_signals"
IMPORTANT_NEWS_KEY = "important_news"


class DashboardTrendService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_trends(self, user_id: int, days: int) -> DashboardTrendSeriesResponse:
        today = utc_now().date()
        start_date = today - timedelta(days=days - 1)
        dates = [start_date + timedelta(days=offset) for offset in range(days)]
        start_at = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        end_at = datetime.combine(today + timedelta(days=1), time.min, tzinfo=timezone.utc)

        risk_alerts = self._count_alerts_by_day(
            user_id=user_id,
            signal_types=[SignalType.RISK_ALERT.value, SignalType.THESIS_BROKEN.value],
            start_at=start_at,
            end_at=end_at,
        )
        review_signals = self._count_alerts_by_day(
            user_id=user_id,
            signal_types=[SignalType.SELL_REVIEW.value, SignalType.OVERHEATED.value],
            start_at=start_at,
            end_at=end_at,
        )
        important_news = self._count_important_news_by_day(
            user_id=user_id,
            start_at=start_at,
            end_at=end_at,
        )

        return DashboardTrendSeriesResponse(
            days=days,
            series=[
                self._build_series(RISK_ALERTS_KEY, risk_alerts, dates),
                self._build_series(REVIEW_SIGNALS_KEY, review_signals, dates),
                self._build_series(IMPORTANT_NEWS_KEY, important_news, dates),
            ],
        )

    def _count_alerts_by_day(
        self,
        *,
        user_id: int,
        signal_types: list[str],
        start_at: datetime,
        end_at: datetime,
    ) -> dict[str, int]:
        day_expr = func.date(Alert.created_at)
        stmt = (
            select(day_expr, func.count())
            .select_from(Alert)
            .join(Signal, Alert.signal_id == Signal.id)
            .where(
                Alert.user_id == user_id,
                Signal.signal_type.in_(signal_types),
                Alert.created_at >= start_at,
                Alert.created_at < end_at,
            )
            .group_by(day_expr)
        )
        return self._rows_to_counts(self.db.execute(stmt).all())

    def _count_important_news_by_day(
        self,
        *,
        user_id: int,
        start_at: datetime,
        end_at: datetime,
    ) -> dict[str, int]:
        day_expr = func.date(AlertCandidate.created_at)
        stmt = (
            select(day_expr, func.count())
            .select_from(AlertCandidate)
            .where(
                AlertCandidate.user_id == user_id,
                AlertCandidate.candidate_type.in_(
                    [
                        AlertCandidateType.NEWS_SURGE.value,
                        AlertCandidateType.DISCLOSURE.value,
                    ]
                ),
                AlertCandidate.importance == AlertImportance.HIGH.value,
                AlertCandidate.created_at >= start_at,
                AlertCandidate.created_at < end_at,
            )
            .group_by(day_expr)
        )
        return self._rows_to_counts(self.db.execute(stmt).all())

    def _build_series(
        self,
        key: str,
        counts_by_date: dict[str, int],
        dates: list[date],
    ) -> TrendSeries:
        return TrendSeries(
            key=key,
            data=[
                TrendDataPoint(
                    date=day.isoformat(),
                    count=counts_by_date.get(day.isoformat(), 0),
                )
                for day in dates
            ],
        )

    def _rows_to_counts(self, rows: Sequence[Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for day_value, count in rows:
            counts[self._date_key(day_value)] = int(count)
        return counts

    def _date_key(self, value: Any) -> str:
        if isinstance(value, date):
            return value.isoformat()
        return str(value)
