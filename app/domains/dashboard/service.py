from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domains.alert_candidates.model import AlertCandidate
from app.domains.alert_candidates.types import (
    AlertCandidateStatus,
    AlertCandidateType,
    AlertImportance,
)
from app.domains.alerts.model import Alert
from app.domains.alerts.types import AlertStatus
from app.domains.dashboard.schema import DashboardSummaryResponse
from app.domains.portfolios.model import Portfolio, Position
from app.domains.signals.model import Signal
from app.domains.signals.time import utc_now
from app.domains.signals.types import SignalType


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_summary(self, user_id: int) -> DashboardSummaryResponse:
        return DashboardSummaryResponse(
            risk_alert_count=self._count_risk_alerts(user_id),
            important_news_count=self._count_important_news(user_id),
            review_signal_count=self._count_review_signals(user_id),
            cash_weight=self._get_cash_weight(user_id),
        )

    def _count_risk_alerts(self, user_id: int) -> int:
        """사용자 alerts 중 status=UNREAD이고 연결 signal type이 RISK_ALERT 또는 THESIS_BROKEN인 개수."""
        stmt = (
            select(func.count())
            .select_from(Alert)
            .join(Signal, Alert.signal_id == Signal.id)
            .where(
                Alert.user_id == user_id,
                Alert.status == AlertStatus.UNREAD.value,
                Signal.signal_type.in_(
                    [SignalType.RISK_ALERT.value, SignalType.THESIS_BROKEN.value]
                ),
            )
        )
        return int(self.db.scalar(stmt) or 0)

    def _count_important_news(self, user_id: int) -> int:
        """alert_candidates 중 type이 NEWS_SURGE/DISCLOSURE이고 importance=HIGH이며 status=UNREAD인 개수."""
        stmt = (
            select(func.count())
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
                AlertCandidate.status == AlertCandidateStatus.UNREAD.value,
            )
        )
        return int(self.db.scalar(stmt) or 0)

    def _count_review_signals(self, user_id: int) -> int:
        """사용자 alerts에 연결된 signal 중 type이 SELL_REVIEW/OVERHEATED이고 활성(미만료)인 개수.

        signals 테이블에는 user_id가 없으므로, 해당 사용자의 alerts를 통해 signal에 접근한다.
        alerts → signal 조인으로 사용자 귀속 판단.
        """
        now = utc_now()
        active_clause = or_(Signal.expires_at.is_(None), Signal.expires_at > now)
        stmt = (
            select(func.count())
            .select_from(Alert)
            .join(Signal, Alert.signal_id == Signal.id)
            .where(
                Alert.user_id == user_id,
                Signal.signal_type.in_(
                    [SignalType.SELL_REVIEW.value, SignalType.OVERHEATED.value]
                ),
                active_clause,
            )
        )
        return int(self.db.scalar(stmt) or 0)

    def _get_cash_weight(self, user_id: int) -> str | None:
        """사용자 첫 번째 포트폴리오의 현금 비중.

        cash_weight = cash_balance / (sum(quantity * avg_buy_price) + cash_balance)
        시장가 API 호출 없이 원가 기준으로 계산.
        포트폴리오가 없으면 null 반환.
        """
        portfolio = self.db.scalars(
            select(Portfolio)
            .where(Portfolio.user_id == user_id)
            .order_by(Portfolio.id)
            .limit(1)
        ).first()
        if portfolio is None:
            return None

        cost_sum_row = self.db.scalar(
            select(func.coalesce(func.sum(Position.quantity * Position.avg_buy_price), 0))
            .where(Position.portfolio_id == portfolio.id)
        )
        cost_total = Decimal(str(cost_sum_row or 0))
        total = cost_total + portfolio.cash_balance
        if total == 0:
            return str(Decimal("0"))
        weight = portfolio.cash_balance / total
        return str(weight.quantize(Decimal("0.0001")))
