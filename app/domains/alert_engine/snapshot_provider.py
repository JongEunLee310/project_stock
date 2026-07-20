from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.domains.alert_engine.types import (
    MetricSnapshot,
    MetricUnavailableReason,
    MetricValue,
)
from app.domains.alert_rules.model import AlertRule
from app.domains.alert_rules.types import AlertMetric, AlertTargetType
from app.domains.assets.model import Asset
from app.domains.assets.repository import AssetRepository
from app.domains.earnings.repository import EarningsRepository
from app.domains.portfolios.repository import PortfolioRepository, PositionRepository
from app.domains.portfolios.service import PortfolioService
from app.domains.prices.repository import PriceBarRepository
from app.domains.signals.repository import SignalSnapshotRepository
from app.domains.signals.snapshot_model import AssetSignalSnapshot
from app.domains.signals.types import SignalType
from app.domains.watchlists.repository import (
    WatchlistItemRepository,
    WatchlistRepository,
)
from app.domains.watchlists.types import AiJudgment, NewsRisk, ThemeHeat

UNSUPPORTED_METRICS = frozenset({AlertMetric.TOPIC_IMPACT_SCORE})

_DERIVED_METRICS = frozenset(
    {
        AlertMetric.NEWS_RISK,
        AlertMetric.THEME_HEAT,
        AlertMetric.AI_JUDGMENT_CHANGED,
    }
)
_DERIVED_VALUE_ORDER = {
    AlertMetric.NEWS_RISK: {
        NewsRisk.LOW.value: 0,
        NewsRisk.MEDIUM.value: 1,
        NewsRisk.HIGH.value: 2,
    },
    AlertMetric.THEME_HEAT: {
        ThemeHeat.COLD.value: 0,
        ThemeHeat.NEUTRAL.value: 1,
        ThemeHeat.OVERHEATED.value: 2,
    },
    AlertMetric.AI_JUDGMENT_CHANGED: {
        AiJudgment.STABLE.value: 0,
        AiJudgment.WATCH.value: 1,
        AiJudgment.RISK_INCREASING.value: 2,
    },
}

_SignalPair = tuple[AssetSignalSnapshot | None, AssetSignalSnapshot | None]
_MetricReading = tuple[
    MetricValue,
    MetricValue,
    bool,
    list[dict[str, Any]],
    int | None,
]
_MetricResult = _MetricReading | MetricUnavailableReason


def _derive_signal_metrics(signal_type: str | None) -> dict[AlertMetric, str]:
    news_risk = NewsRisk.LOW.value
    theme_heat = ThemeHeat.NEUTRAL.value
    ai_judgment = AiJudgment.STABLE.value

    if signal_type in {
        SignalType.RISK_ALERT.value,
        SignalType.THESIS_BROKEN.value,
    }:
        news_risk = NewsRisk.HIGH.value
        ai_judgment = AiJudgment.RISK_INCREASING.value
    elif signal_type in {
        SignalType.WATCH.value,
        SignalType.SELL_REVIEW.value,
    }:
        news_risk = NewsRisk.MEDIUM.value
        ai_judgment = AiJudgment.WATCH.value
    elif signal_type == SignalType.OVERHEATED.value:
        news_risk = NewsRisk.MEDIUM.value
        theme_heat = ThemeHeat.OVERHEATED.value
        ai_judgment = AiJudgment.WATCH.value
    elif signal_type == SignalType.BUY_CANDIDATE.value:
        ai_judgment = AiJudgment.WATCH.value

    return {
        AlertMetric.NEWS_RISK: news_risk,
        AlertMetric.THEME_HEAT: theme_heat,
        AlertMetric.AI_JUDGMENT_CHANGED: ai_judgment,
    }


def _signal_snapshot_evidence(
    *,
    asset_id: int,
    snapshot: AssetSignalSnapshot | None,
    metric: AlertMetric,
    value: str,
) -> list[dict[str, Any]]:
    return [
        {
            "kind": "SIGNAL_SNAPSHOT",
            "asset_id": asset_id,
            "snapshot_date": (
                snapshot.snapshot_date.isoformat() if snapshot is not None else None
            ),
            "signal_id": snapshot.signal_id if snapshot is not None else None,
            "score": snapshot.score if snapshot is not None else None,
            "signal_type": snapshot.signal_type if snapshot is not None else None,
            "derived_metric": metric.value,
            "derived_value": value,
        }
    ]


def _aggregate_derived_metric(
    metric: AlertMetric,
    pairs: Mapping[int, _SignalPair],
) -> _MetricReading | None:
    states = [
        (
            asset_id,
            latest,
            previous,
            _derive_signal_metrics(latest.signal_type if latest is not None else None),
            _derive_signal_metrics(
                previous.signal_type if previous is not None else None
            ),
        )
        for asset_id, (latest, previous) in sorted(pairs.items())
        if latest is not None
    ]
    if not states:
        return None

    if metric == AlertMetric.AI_JUDGMENT_CHANGED:
        transitions = [
            state
            for state in states
            if state[2] is not None and state[3][metric] != state[4][metric]
        ]
        if transitions:
            selected = min(
                transitions,
                key=lambda state: (
                    state[3][metric] != AiJudgment.RISK_INCREASING.value,
                    state[0],
                ),
            )
        else:
            selected = max(
                states,
                key=lambda state: (_DERIVED_VALUE_ORDER[metric][state[3][metric]], -state[0]),
            )
        asset_id, latest, previous, current_values, previous_values = selected
        current = current_values[metric]
        return (
            current,
            previous_values[metric],
            previous is not None,
            _signal_snapshot_evidence(
                asset_id=asset_id,
                snapshot=latest,
                metric=metric,
                value=current,
            ),
            asset_id,
        )

    selected = max(
        states,
        key=lambda state: (_DERIVED_VALUE_ORDER[metric][state[3][metric]], -state[0]),
    )
    asset_id, latest, _, current_values, _ = selected
    current = current_values[metric]
    previous_value = max(
        (state[4][metric] for state in states),
        key=_DERIVED_VALUE_ORDER[metric].__getitem__,
    )
    return (
        current,
        previous_value,
        any(state[2] is not None for state in states),
        _signal_snapshot_evidence(
            asset_id=asset_id,
            snapshot=latest,
            metric=metric,
            value=current,
        ),
        asset_id,
    )


class MetricSnapshotProvider:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.earnings_repo = EarningsRepository(db)
        self.portfolio_repo = PortfolioRepository(db)
        self.position_repo = PositionRepository(db)
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
        unavailable_reasons: dict[AlertMetric, MetricUnavailableReason] = {}
        unsupported = metrics & UNSUPPORTED_METRICS
        asset_id: int | None = None

        for metric in metrics - unsupported:
            reading = self._read_metric(rule, metric, as_of)
            if isinstance(reading, MetricUnavailableReason):
                unavailable_reasons[metric] = reading
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
            unavailable_reasons=unavailable_reasons,
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
    ) -> _MetricResult:
        if metric in _DERIVED_METRICS:
            return self._derived_signal_metric(rule, metric)
        if metric == AlertMetric.PRICE_CHANGE_1D:
            return self._price_change(rule)
        if metric == AlertMetric.SIGNAL_CHANGED:
            return self._signal_change(rule)
        if metric == AlertMetric.POSITION_WEIGHT:
            return self._position_weight(rule)
        if metric == AlertMetric.EARNINGS_DATE:
            return self._earnings_date(rule, as_of.date())
        return MetricUnavailableReason.NO_DATA

    def _derived_signal_metric(
        self,
        rule: AlertRule,
        metric: AlertMetric,
    ) -> _MetricResult:
        asset_ids = self._target_asset_ids(rule)
        if asset_ids is None:
            return MetricUnavailableReason.NO_TARGET
        pairs = self.signal_snapshot_repo.latest_pair_by_asset(asset_ids)
        reading = _aggregate_derived_metric(metric, pairs)
        if reading is None:
            return MetricUnavailableReason.NO_DATA
        return reading

    def _target_asset_ids(self, rule: AlertRule) -> list[int] | None:
        if rule.target_type == AlertTargetType.SYMBOL.value:
            asset = self._symbol_asset(rule)
            return [asset.id] if asset is not None else None
        if rule.target_id is None:
            return None
        try:
            target_id = int(rule.target_id)
        except ValueError:
            return None
        if rule.target_type == AlertTargetType.WATCHLIST.value:
            watchlist = self.watchlist_repo.get_by_id(target_id)
            if watchlist is None or watchlist.user_id != rule.user_id:
                return None
            asset_ids = [
                item.asset_id
                for item in self.watchlist_item_repo.list_by_watchlist(watchlist.id)
            ]
        elif rule.target_type == AlertTargetType.PORTFOLIO.value:
            portfolio = self.portfolio_repo.get_by_id(target_id)
            if portfolio is None or portfolio.user_id != rule.user_id:
                return None
            asset_ids = [
                position.asset_id
                for position in self.position_repo.list_by_portfolio(portfolio.id)
            ]
        else:
            return None
        return sorted(set(asset_ids)) or None

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
    ) -> _MetricResult:
        asset = self._symbol_asset(rule)
        if asset is None:
            return MetricUnavailableReason.NO_TARGET
        bars = self.price_repo.list_recent(asset.symbol, asset.market, "1d", 3)
        if len(bars) < 2 or bars[-2].close_price == 0:
            return MetricUnavailableReason.NO_DATA
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
    ) -> _MetricResult:
        asset = self._symbol_asset(rule)
        if asset is None:
            return MetricUnavailableReason.NO_TARGET
        latest, previous = self.signal_snapshot_repo.latest_pair_by_asset([asset.id])[
            asset.id
        ]
        if latest is None:
            return MetricUnavailableReason.NO_DATA
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
    ) -> _MetricResult:
        if rule.target_type != AlertTargetType.PORTFOLIO.value or rule.target_id is None:
            return MetricUnavailableReason.NO_TARGET
        try:
            portfolio_id = int(rule.target_id)
        except ValueError:
            return MetricUnavailableReason.NO_TARGET
        portfolio = self.portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None or portfolio.user_id != rule.user_id:
            return MetricUnavailableReason.NO_TARGET
        summary = self.portfolio_service.get_summary(portfolio.id, rule.user_id)
        if not summary.positions:
            return MetricUnavailableReason.NO_DATA
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
    ) -> _MetricResult:
        if rule.target_type != AlertTargetType.WATCHLIST.value or rule.target_id is None:
            return MetricUnavailableReason.NO_TARGET
        try:
            watchlist_id = int(rule.target_id)
        except ValueError:
            return MetricUnavailableReason.NO_TARGET
        watchlist = self.watchlist_repo.get_by_id(watchlist_id)
        if watchlist is None or watchlist.user_id != rule.user_id:
            return MetricUnavailableReason.NO_TARGET
        items = self.watchlist_item_repo.list_by_watchlist(watchlist.id)
        assets = self.asset_repo.list_by_ids([item.asset_id for item in items])
        upcoming: list[tuple[date, Asset]] = []
        end = today + timedelta(days=366)
        for asset in assets:
            events = self.earnings_repo.get_events(asset.symbol, asset.market, today, end)
            if events:
                upcoming.append((events[0].event_date, asset))
        if not upcoming:
            return MetricUnavailableReason.NO_DATA
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
