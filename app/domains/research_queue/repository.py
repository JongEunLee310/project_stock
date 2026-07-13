from datetime import datetime, timedelta

from sqlalchemy import case, func, or_, select, tuple_
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.domains.assets.model import Asset
from app.domains.earnings.model import EarningsEvent, EarningsReport
from app.domains.news.model import NewsItem
from app.domains.prices.model import StockPriceBar
from app.domains.reports.model import ResearchReport
from app.domains.research_queue.schema import ResearchDataPresence
from app.domains.signals.model import Signal
from app.domains.signals.time import utc_now
from app.domains.signals.types import WATCHLIST_STATUS_PRIORITY
from app.domains.valuation.model import ValuationSnapshot


class ResearchQueueRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_active_assets(self) -> list[Asset]:
        stmt = select(Asset).where(Asset.is_active.is_(True)).order_by(Asset.id)
        return list(self.db.scalars(stmt).all())

    def get_data_presence_by_assets(
        self,
        assets: list[Asset],
    ) -> dict[int, ResearchDataPresence]:
        if not assets:
            return {}

        asset_ids = [asset.id for asset in assets]
        asset_keys = {(asset.symbol, asset.market) for asset in assets}
        news_rows = self.db.execute(
            select(NewsItem.asset_id, func.max(NewsItem.created_at))
            .where(NewsItem.asset_id.in_(asset_ids))
            .group_by(NewsItem.asset_id)
        )
        news_by_id: dict[int, datetime] = dict(
            (asset_id, created_at) for asset_id, created_at in news_rows
        )
        report_rows = self.db.execute(
            select(ResearchReport.asset_id, func.max(ResearchReport.created_at))
            .where(ResearchReport.asset_id.in_(asset_ids))
            .group_by(ResearchReport.asset_id)
        )
        reports_by_id: dict[int, datetime] = dict(
            (asset_id, created_at) for asset_id, created_at in report_rows
        )
        price_keys = self._present_keys(
            StockPriceBar.symbol,
            StockPriceBar.market,
            asset_keys,
        )
        earnings_keys = self._present_keys(
            EarningsReport.symbol,
            EarningsReport.market,
            asset_keys,
        )
        valuation_keys = self._present_keys(
            ValuationSnapshot.symbol,
            ValuationSnapshot.market,
            asset_keys,
        )
        signal_rows = self.db.execute(
            select(Signal.asset_id, func.max(Signal.created_at))
            .where(Signal.asset_id.in_(asset_ids))
            .group_by(Signal.asset_id)
        )
        signals_by_id: dict[int, datetime] = dict(
            (asset_id, created_at) for asset_id, created_at in signal_rows
        )

        return {
            asset.id: ResearchDataPresence(
                has_news=asset.id in news_by_id,
                has_price=(asset.symbol, asset.market) in price_keys,
                has_earnings=(asset.symbol, asset.market) in earnings_keys,
                has_valuation=(asset.symbol, asset.market) in valuation_keys,
                latest_news_at=news_by_id.get(asset.id),
                latest_report_at=reports_by_id.get(asset.id),
                latest_signal_at=signals_by_id.get(asset.id),
            )
            for asset in assets
        }

    def get_earnings_upcoming_assets(
        self,
        assets: list[Asset],
        horizon_days: int = 30,
    ) -> set[int]:
        if not assets:
            return set()
        asset_keys = {(asset.symbol, asset.market) for asset in assets}
        today = utc_now().date()
        end = today + timedelta(days=horizon_days)
        stmt = select(EarningsEvent.symbol, EarningsEvent.market).where(
            tuple_(EarningsEvent.symbol, EarningsEvent.market).in_(asset_keys),
            EarningsEvent.event_date >= today,
            EarningsEvent.event_date <= end,
        ).distinct()
        upcoming_keys = set(self.db.execute(stmt).all())
        return {
            asset.id
            for asset in assets
            if (asset.symbol, asset.market) in upcoming_keys
        }

    def get_active_signal_types_by_assets(
        self,
        asset_ids: list[int],
    ) -> dict[int, set[str]]:
        if not asset_ids:
            return {}
        stmt = (
            select(Signal.asset_id, Signal.signal_type)
            .where(
                Signal.asset_id.in_(asset_ids),
                self._active_signal_clause(),
            )
            .distinct()
        )
        result: dict[int, set[str]] = {}
        for asset_id, signal_type in self.db.execute(stmt):
            result.setdefault(asset_id, set()).add(signal_type)
        return result

    def get_top_signal_reason_by_assets(
        self,
        asset_ids: list[int],
    ) -> dict[int, str | None]:
        if not asset_ids:
            return {}
        rank_by_type = {
            signal_type.value: rank
            for rank, signal_type in enumerate(WATCHLIST_STATUS_PRIORITY)
        }
        rank_expression = case(
            rank_by_type,
            value=Signal.signal_type,
            else_=len(rank_by_type),
        )
        ranked = select(
            Signal.asset_id,
            Signal.reason,
            func.row_number().over(
                partition_by=Signal.asset_id,
                order_by=(
                    rank_expression.asc(),
                    Signal.score.desc(),
                    Signal.created_at.desc(),
                    Signal.id.desc(),
                ),
            ).label("asset_rank"),
        ).where(
            Signal.asset_id.in_(asset_ids),
            self._active_signal_clause(),
        ).subquery()
        stmt = select(ranked.c.asset_id, ranked.c.reason).where(
            ranked.c.asset_rank == 1
        )
        return {
            asset_id: reason
            for asset_id, reason in self.db.execute(stmt)
        }

    def get_latest_report_negative_factors(
        self,
        asset_ids: list[int],
    ) -> dict[int, str | None]:
        if not asset_ids:
            return {}
        ranked = select(
            ResearchReport.asset_id,
            ResearchReport.negative_factors,
            func.row_number().over(
                partition_by=ResearchReport.asset_id,
                order_by=(
                    ResearchReport.created_at.desc(),
                    ResearchReport.id.desc(),
                ),
            ).label("asset_rank"),
        ).where(ResearchReport.asset_id.in_(asset_ids)).subquery()
        stmt = select(ranked.c.asset_id, ranked.c.negative_factors).where(
            ranked.c.asset_rank == 1
        )
        return {
            asset_id: factors
            for asset_id, factors in self.db.execute(stmt)
        }

    def _present_keys(
        self,
        symbol_column: InstrumentedAttribute[str],
        market_column: InstrumentedAttribute[str],
        keys: set[tuple[str, str]],
    ) -> set[tuple[str, str]]:
        stmt = select(symbol_column, market_column).where(
            tuple_(symbol_column, market_column).in_(keys)
        ).distinct()
        return {(symbol, market) for symbol, market in self.db.execute(stmt)}

    @staticmethod
    def _active_signal_clause() -> ColumnElement[bool]:
        now = utc_now()
        return or_(Signal.expires_at.is_(None), Signal.expires_at > now)
