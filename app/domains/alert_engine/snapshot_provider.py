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

    def get_snapshots(
        self,
        rule: AlertRule,
        *,
        as_of: datetime,
    ) -> list[MetricSnapshot]:
        metrics = self._condition_metrics(rule.condition)
        unsupported = metrics & UNSUPPORTED_METRICS
        if unsupported:
            return [MetricSnapshot(unsupported_metrics=frozenset(unsupported))]

        asset_ids = self._target_asset_ids(rule)
        if asset_ids is None:
            return [
                MetricSnapshot(
                    unavailable_reasons={
                        metric: MetricUnavailableReason.NO_TARGET for metric in metrics
                    }
                )
            ]

        signal_pairs = (
            self.signal_snapshot_repo.latest_pair_by_asset(asset_ids)
            if metrics & (_DERIVED_METRICS | {AlertMetric.SIGNAL_CHANGED})
            else {}
        )
        readings = {
            metric: self._read_metric_by_asset(
                rule,
                metric,
                asset_ids,
                as_of,
                signal_pairs,
            )
            for metric in metrics
        }
        return [
            self._build_snapshot(asset_id, metrics, readings) for asset_id in asset_ids
        ]

    def _build_snapshot(
        self,
        asset_id: int,
        metrics: set[AlertMetric],
        readings: dict[AlertMetric, dict[int, _MetricResult]],
    ) -> MetricSnapshot:
        values: dict[AlertMetric, MetricValue] = {}
        previous_values: dict[AlertMetric, MetricValue] = {}
        evidence: dict[AlertMetric, list[dict[str, Any]]] = {}
        unavailable_reasons: dict[AlertMetric, MetricUnavailableReason] = {}

        for metric in metrics:
            reading = readings[metric][asset_id]
            if isinstance(reading, MetricUnavailableReason):
                unavailable_reasons[metric] = reading
                continue
            current, previous, has_previous, metric_evidence, _ = reading
            values[metric] = current
            if has_previous:
                previous_values[metric] = previous
            evidence[metric] = metric_evidence

        return MetricSnapshot(
            values=values,
            previous_values=previous_values,
            evidence=evidence,
            asset_id=asset_id,
            unavailable_reasons=unavailable_reasons,
        )

    def _condition_metrics(self, condition: dict[str, Any]) -> set[AlertMetric]:
        if set(condition) == {"all"}:
            return {AlertMetric(member["metric"]) for member in condition["all"]}
        return {AlertMetric(condition["metric"])}

    def _read_metric_by_asset(
        self,
        rule: AlertRule,
        metric: AlertMetric,
        asset_ids: list[int],
        as_of: datetime,
        signal_pairs: dict[int, _SignalPair],
    ) -> dict[int, _MetricResult]:
        if metric in _DERIVED_METRICS:
            return {
                asset_id: self._derived_signal_metric(
                    metric,
                    asset_id,
                    signal_pairs[asset_id],
                )
                for asset_id in asset_ids
            }
        if metric == AlertMetric.PRICE_CHANGE_1D:
            return self._price_changes(rule, asset_ids)
        if metric == AlertMetric.SIGNAL_CHANGED:
            return self._signal_changes(rule, asset_ids, signal_pairs)
        if metric == AlertMetric.POSITION_WEIGHT:
            return self._position_weights(rule, asset_ids)
        if metric == AlertMetric.EARNINGS_DATE:
            return self._earnings_dates(rule, asset_ids, as_of.date())
        return {
            asset_id: MetricUnavailableReason.NO_DATA for asset_id in asset_ids
        }

    def _derived_signal_metric(
        self,
        metric: AlertMetric,
        asset_id: int,
        pair: _SignalPair,
    ) -> _MetricResult:
        latest, previous = pair
        if latest is None:
            return MetricUnavailableReason.NO_DATA
        current = _derive_signal_metrics(latest.signal_type)[metric]
        previous_value = (
            _derive_signal_metrics(previous.signal_type)[metric]
            if previous is not None
            else None
        )
        return (
            current,
            previous_value,
            previous is not None,
            _signal_snapshot_evidence(
                asset_id=asset_id,
                snapshot=latest,
                metric=metric,
                value=current,
            ),
            asset_id,
        )

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

    def _price_changes(
        self,
        rule: AlertRule,
        asset_ids: list[int],
    ) -> dict[int, _MetricResult]:
        if rule.target_type != AlertTargetType.SYMBOL.value:
            return self._no_target_results(asset_ids)
        assets_by_id = {
            asset.id: asset for asset in self.asset_repo.list_by_ids(asset_ids)
        }
        return {
            asset_id: (
                self._price_change(assets_by_id[asset_id])
                if asset_id in assets_by_id
                else MetricUnavailableReason.NO_TARGET
            )
            for asset_id in asset_ids
        }

    def _price_change(self, asset: Asset) -> _MetricResult:
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

    def _signal_changes(
        self,
        rule: AlertRule,
        asset_ids: list[int],
        signal_pairs: dict[int, _SignalPair],
    ) -> dict[int, _MetricResult]:
        if rule.target_type != AlertTargetType.SYMBOL.value:
            return self._no_target_results(asset_ids)
        return {
            asset_id: self._signal_change(asset_id, signal_pairs[asset_id])
            for asset_id in asset_ids
        }

    def _signal_change(self, asset_id: int, pair: _SignalPair) -> _MetricResult:
        latest, previous = pair
        if latest is None:
            return MetricUnavailableReason.NO_DATA
        evidence = [
            {
                "kind": "SIGNAL_SNAPSHOT",
                "asset_id": asset_id,
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
            asset_id,
        )

    def _position_weights(
        self,
        rule: AlertRule,
        asset_ids: list[int],
    ) -> dict[int, _MetricResult]:
        if rule.target_type != AlertTargetType.PORTFOLIO.value or rule.target_id is None:
            return self._no_target_results(asset_ids)
        try:
            portfolio_id = int(rule.target_id)
        except ValueError:
            return self._no_target_results(asset_ids)
        portfolio = self.portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None or portfolio.user_id != rule.user_id:
            return self._no_target_results(asset_ids)
        summary = self.portfolio_service.get_summary(portfolio.id, rule.user_id)
        positions_by_asset = {
            position.asset_id: position for position in summary.positions
        }
        readings: dict[int, _MetricResult] = {}
        for asset_id in asset_ids:
            position = positions_by_asset.get(asset_id)
            if position is None:
                readings[asset_id] = MetricUnavailableReason.NO_DATA
                continue
            evidence = [
                {
                    "kind": "PORTFOLIO_POSITION",
                    "portfolio_id": portfolio.id,
                    "asset_id": asset_id,
                    "weight": str(position.weight),
                    "market_value": str(position.market_value),
                }
            ]
            readings[asset_id] = (
                float(position.weight),
                None,
                False,
                evidence,
                asset_id,
            )
        return readings

    def _earnings_dates(
        self,
        rule: AlertRule,
        asset_ids: list[int],
        today: date,
    ) -> dict[int, _MetricResult]:
        if rule.target_type != AlertTargetType.WATCHLIST.value or rule.target_id is None:
            return self._no_target_results(asset_ids)
        try:
            watchlist_id = int(rule.target_id)
        except ValueError:
            return self._no_target_results(asset_ids)
        watchlist = self.watchlist_repo.get_by_id(watchlist_id)
        if watchlist is None or watchlist.user_id != rule.user_id:
            return self._no_target_results(asset_ids)
        assets = self.asset_repo.list_by_ids(asset_ids)
        assets_by_id = {asset.id: asset for asset in assets}
        end = today + timedelta(days=366)
        events_by_asset = self.earnings_repo.get_first_events_by_asset(
            {
                asset.id: (asset.symbol, asset.market)
                for asset in assets
            },
            today,
            end,
        )
        readings: dict[int, _MetricResult] = {}
        for asset_id in asset_ids:
            asset = assets_by_id.get(asset_id)
            event = events_by_asset.get(asset_id)
            if asset is None or event is None:
                readings[asset_id] = MetricUnavailableReason.NO_DATA
                continue
            days_until = (event.event_date - today).days
            evidence = [
                {
                    "kind": "EARNINGS_EVENT",
                    "asset_id": asset_id,
                    "symbol": asset.symbol,
                    "market": asset.market,
                    "event_date": event.event_date.isoformat(),
                }
            ]
            readings[asset_id] = (
                days_until,
                None,
                False,
                evidence,
                asset_id,
            )
        return readings

    def _no_target_results(self, asset_ids: list[int]) -> dict[int, _MetricResult]:
        return {
            asset_id: MetricUnavailableReason.NO_TARGET for asset_id in asset_ids
        }

    def _percent_change(self, previous: Decimal, current: Decimal) -> float:
        return float((current / previous - Decimal("1")) * Decimal("100"))
