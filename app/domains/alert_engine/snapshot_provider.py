from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.domains.alert_engine.types import MetricSnapshot, MetricValue
from app.domains.alert_rules.model import AlertRule
from app.domains.alert_rules.types import AlertMetric, AlertTargetType
from app.domains.assets.model import Asset
from app.domains.assets.repository import AssetRepository
from app.domains.earnings.repository import EarningsRepository
from app.domains.portfolios.repository import PortfolioRepository
from app.domains.portfolios.service import PortfolioService
from app.domains.prices.repository import PriceBarRepository
from app.domains.signals.repository import SignalSnapshotRepository
from app.domains.watchlists.repository import (
    WatchlistItemRepository,
    WatchlistRepository,
)

UNSUPPORTED_METRICS = frozenset(
    {
        AlertMetric.NEWS_RISK,
        AlertMetric.THEME_HEAT,
        AlertMetric.AI_JUDGMENT_CHANGED,
        AlertMetric.TOPIC_IMPACT_SCORE,
    }
)


class MetricSnapshotProvider:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.earnings_repo = EarningsRepository(db)
        self.portfolio_repo = PortfolioRepository(db)
        self.portfolio_service = PortfolioService(db)
        self.price_repo = PriceBarRepository(db)
        self.signal_snapshot_repo = SignalSnapshotRepository(db)
        self.watchlist_repo = WatchlistRepository(db)
        self.watchlist_item_repo = WatchlistItemRepository(db)

    def get_snapshot(
        self,
        rule: AlertRule,
        *,
        as_of: datetime,
    ) -> MetricSnapshot:
        metrics = self._condition_metrics(rule.condition)
        values: dict[AlertMetric, MetricValue] = {}
        previous_values: dict[AlertMetric, MetricValue] = {}
        evidence: dict[AlertMetric, list[dict[str, Any]]] = {}
        unsupported = metrics & UNSUPPORTED_METRICS
        asset_id: int | None = None

        for metric in metrics - unsupported:
            reading = self._read_metric(rule, metric, as_of)
            if reading is None:
                continue
            current, previous, has_previous, metric_evidence, reading_asset_id = reading
            values[metric] = current
            if has_previous:
                previous_values[metric] = previous
            evidence[metric] = metric_evidence
            if asset_id is None:
                asset_id = reading_asset_id

        return MetricSnapshot(
            values=values,
            previous_values=previous_values,
            evidence=evidence,
            unsupported_metrics=frozenset(unsupported),
            asset_id=asset_id,
        )

    def _condition_metrics(self, condition: dict[str, Any]) -> set[AlertMetric]:
        if set(condition) == {"all"}:
            return {AlertMetric(member["metric"]) for member in condition["all"]}
        return {AlertMetric(condition["metric"])}

    def _read_metric(
        self,
        rule: AlertRule,
        metric: AlertMetric,
        as_of: datetime,
    ) -> tuple[
        MetricValue,
        MetricValue,
        bool,
        list[dict[str, Any]],
        int | None,
    ] | None:
        if metric == AlertMetric.PRICE_CHANGE_1D:
            return self._price_change(rule)
        if metric == AlertMetric.SIGNAL_CHANGED:
            return self._signal_change(rule)
        if metric == AlertMetric.POSITION_WEIGHT:
            return self._position_weight(rule)
        if metric == AlertMetric.EARNINGS_DATE:
            return self._earnings_date(rule, as_of.date())
        return None

    def _symbol_asset(self, rule: AlertRule) -> Asset | None:
        if rule.target_type != AlertTargetType.SYMBOL.value or rule.target_id is None:
            return None
        assets = self.asset_repo.list_all(symbol=rule.target_id.upper(), limit=2)
        if len(assets) != 1:
            return None
        return assets[0]

    def _price_change(
        self,
        rule: AlertRule,
    ) -> tuple[MetricValue, MetricValue, bool, list[dict[str, Any]], int | None] | None:
        asset = self._symbol_asset(rule)
        if asset is None:
            return None
        bars = self.price_repo.list_recent(asset.symbol, asset.market, "1d", 3)
        if len(bars) < 2 or bars[-2].close_price == 0:
            return None
        current = self._percent_change(bars[-2].close_price, bars[-1].close_price)
        previous: float | None = None
        has_previous = len(bars) >= 3 and bars[-3].close_price != 0
        if has_previous:
            previous = self._percent_change(bars[-3].close_price, bars[-2].close_price)
        evidence = [
            {
                "kind": "PRICE",
                "symbol": asset.symbol,
                "market": asset.market,
                "previous_close": str(bars[-2].close_price),
                "current_close": str(bars[-1].close_price),
                "as_of": bars[-1].timestamp.isoformat(),
            }
        ]
        return current, previous, has_previous, evidence, asset.id

    def _signal_change(
        self,
        rule: AlertRule,
    ) -> tuple[MetricValue, MetricValue, bool, list[dict[str, Any]], int | None] | None:
        asset = self._symbol_asset(rule)
        if asset is None:
            return None
        latest, previous = self.signal_snapshot_repo.latest_pair_by_asset([asset.id])[
            asset.id
        ]
        if latest is None:
            return None
        evidence = [
            {
                "kind": "SIGNAL_SNAPSHOT",
                "asset_id": asset.id,
                "snapshot_date": latest.snapshot_date.isoformat(),
                "signal_id": latest.signal_id,
                "score": latest.score,
            }
        ]
        return (
            latest.signal_type,
            previous.signal_type if previous is not None else None,
            previous is not None,
            evidence,
            asset.id,
        )

    def _position_weight(
        self,
        rule: AlertRule,
    ) -> tuple[MetricValue, MetricValue, bool, list[dict[str, Any]], int | None] | None:
        if rule.target_type != AlertTargetType.PORTFOLIO.value or rule.target_id is None:
            return None
        try:
            portfolio_id = int(rule.target_id)
        except ValueError:
            return None
        portfolio = self.portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None or portfolio.user_id != rule.user_id:
            return None
        summary = self.portfolio_service.get_summary(portfolio.id, rule.user_id)
        if not summary.positions:
            return None
        largest = max(summary.positions, key=lambda position: position.weight)
        evidence = [
            {
                "kind": "PORTFOLIO_POSITION",
                "portfolio_id": portfolio.id,
                "asset_id": largest.asset_id,
                "weight": str(largest.weight),
                "market_value": str(largest.market_value),
            }
        ]
        return float(largest.weight), None, False, evidence, largest.asset_id

    def _earnings_date(
        self,
        rule: AlertRule,
        today: date,
    ) -> tuple[MetricValue, MetricValue, bool, list[dict[str, Any]], int | None] | None:
        if rule.target_type != AlertTargetType.WATCHLIST.value or rule.target_id is None:
            return None
        try:
            watchlist_id = int(rule.target_id)
        except ValueError:
            return None
        watchlist = self.watchlist_repo.get_by_id(watchlist_id)
        if watchlist is None or watchlist.user_id != rule.user_id:
            return None
        items = self.watchlist_item_repo.list_by_watchlist(watchlist.id)
        assets = self.asset_repo.list_by_ids([item.asset_id for item in items])
        upcoming: list[tuple[date, Asset]] = []
        end = today + timedelta(days=366)
        for asset in assets:
            events = self.earnings_repo.get_events(asset.symbol, asset.market, today, end)
            if events:
                upcoming.append((events[0].event_date, asset))
        if not upcoming:
            return None
        event_date, asset = min(upcoming, key=lambda item: (item[0], item[1].id))
        days_until = (event_date - today).days
        evidence = [
            {
                "kind": "EARNINGS_EVENT",
                "asset_id": asset.id,
                "symbol": asset.symbol,
                "market": asset.market,
                "event_date": event_date.isoformat(),
            }
        ]
        return days_until, None, False, evidence, asset.id

    def _percent_change(self, previous: Decimal, current: Decimal) -> float:
        return float((current / previous - Decimal("1")) * Decimal("100"))
