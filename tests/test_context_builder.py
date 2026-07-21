from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.adapters.llm.types import LLMTaskType
from app.adapters.market.base import QuoteResult
from app.domains.assets.model import Asset
from app.domains.decision_logs.model import DecisionLog
from app.domains.llm_context.context_builder import ContextBuilder
from app.domains.llm_context.schema import DataQualityStatus, LLMContextBundle
from app.domains.news.model import NewsItem
from app.domains.portfolios.model import Portfolio, Position
from app.domains.prices.model import StockPriceBar
from app.domains.signals.model import Signal
from app.domains.users.model import User


def test_build_context_bundle_maps_available_sources(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _create_user(db)
    asset = _create_asset(db, symbol="AAPL", name="Apple Inc.", market="NASDAQ")
    _create_price_bars(db, symbol="AAPL", market="NASDAQ", count=252)
    _create_portfolio(db, user_id=user.id, asset_id=asset.id)
    _create_news_item(db, asset_id=asset.id, title="Apple expands services")
    _create_decision_log(db, user_id=user.id, ticker="AAPL", reason="Keep watching.")
    _create_decision_log(db, user_id=user.id, ticker="MSFT", reason="Other symbol.")
    _mock_quotes(monkeypatch, {"AAPL": Decimal("150")})

    bundle = ContextBuilder(db).build_context_bundle(
        LLMTaskType.WATCHLIST_NOTE,
        user.id,
        [("AAPL", "NASDAQ")],
    )

    assert isinstance(bundle, LLMContextBundle)
    assert bundle.symbols == ["AAPL"]
    assert bundle.output_contract.required_fields == [
        "summary",
        "risk_level",
        "suggested_action",
        "reasons",
        "watch_points",
        "counter_arguments",
        "data_limitations",
        "confidence",
    ]
    assert bundle.user_rules
    assert bundle.data_quality.price_data_status == DataQualityStatus.VALID
    assert bundle.data_quality.news_data_status == DataQualityStatus.VALID
    assert "뉴스 데이터는 아직 포함되지 않았습니다." not in bundle.data_quality.warnings
    assert bundle.data_quality.portfolio_data_status == DataQualityStatus.VALID

    symbol_card = bundle.symbol_cards[0]
    assert symbol_card.display_name == "Apple Inc."
    assert len(symbol_card.recent_news) == 1
    assert symbol_card.recent_news[0].title == "Apple expands services"
    assert symbol_card.signals == []
    assert symbol_card.price_snapshot.close == 352.0
    assert symbol_card.price_snapshot.return_1d is not None
    assert symbol_card.price_snapshot.return_5d is not None
    assert symbol_card.price_snapshot.return_20d is not None
    assert symbol_card.price_snapshot.drawdown_from_52w_high == 0.0
    assert symbol_card.price_snapshot.volume_vs_20d_avg is not None

    assert symbol_card.portfolio_context is not None
    assert symbol_card.portfolio_context.holding is True
    assert symbol_card.portfolio_context.weight == pytest.approx(0.6)
    assert symbol_card.portfolio_context.avg_buy_price == 100.0
    assert symbol_card.portfolio_context.unrealized_return == pytest.approx(0.5)

    assert bundle.portfolio_summary is not None
    assert bundle.portfolio_summary.cash_ratio == pytest.approx(0.4)
    assert bundle.portfolio_summary.top_holding_weight == pytest.approx(0.6)
    assert bundle.portfolio_summary.concentration_risk == "high"
    assert len(bundle.recent_decisions) == 1
    assert bundle.recent_decisions[0].symbol == "AAPL"
    assert bundle.recent_decisions[0].reason == "Keep watching."


def test_missing_price_data_degrades_to_empty_snapshot(db: Session) -> None:
    user = _create_user(db)
    _create_asset(db, symbol="AAPL", name="Apple Inc.", market="NASDAQ")

    bundle = ContextBuilder(db).build_context_bundle(
        LLMTaskType.WATCHLIST_NOTE,
        user.id,
        [("AAPL", "NASDAQ")],
    )

    snapshot = bundle.symbol_cards[0].price_snapshot
    assert snapshot.close is None
    assert snapshot.return_1d is None
    assert snapshot.return_5d is None
    assert snapshot.return_20d is None
    assert snapshot.drawdown_from_52w_high is None
    assert snapshot.volume_vs_20d_avg is None
    assert bundle.data_quality.price_data_status == DataQualityStatus.MISSING


def test_recent_news_maps_nullable_fields_with_safe_defaults(db: Session) -> None:
    user = _create_user(db)
    asset = _create_asset(db, symbol="AAPL", name="Apple Inc.", market="NASDAQ")
    news_item = _create_news_item(
        db,
        asset_id=asset.id,
        title="Apple services momentum",
        summary=None,
        published_at=None,
    )

    symbol_card = ContextBuilder(db).build_symbol_context(user.id, "AAPL", "NASDAQ")

    assert len(symbol_card.recent_news) == 1
    recent_news = symbol_card.recent_news[0]
    assert recent_news.title == "Apple services momentum"
    assert recent_news.summary == ""
    assert recent_news.source == "test-wire"
    assert recent_news.published_at == news_item.created_at
    assert recent_news.trust_level == "unknown"


def test_recent_news_uses_stored_trust_level(db: Session) -> None:
    user = _create_user(db)
    asset = _create_asset(db, symbol="AAPL", name="Apple Inc.", market="NASDAQ")
    _create_news_item(
        db,
        asset_id=asset.id,
        title="Apple trust signal",
        trust_level="high",
    )

    symbol_card = ContextBuilder(db).build_symbol_context(user.id, "AAPL", "NASDAQ")

    assert len(symbol_card.recent_news) == 1
    assert symbol_card.recent_news[0].trust_level == "high"


def test_signals_map_active_items_and_exclude_expired(db: Session) -> None:
    user = _create_user(db)
    asset = _create_asset(db, symbol="AAPL", name="Apple Inc.", market="NASDAQ")
    _create_signal(
        db,
        asset_id=asset.id,
        signal_type="risk",
        score=75,
        risk_level=None,
        reason="Elevated headline risk.",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    _create_signal(
        db,
        asset_id=asset.id,
        signal_type="expired",
        score=95,
        risk_level="high",
        reason="Expired signal.",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )

    symbol_card = ContextBuilder(db).build_symbol_context(user.id, "AAPL", "NASDAQ")

    assert len(symbol_card.signals) == 1
    assert symbol_card.signals[0].type == "risk"
    assert symbol_card.signals[0].severity == "high"
    assert symbol_card.signals[0].reason == "Elevated headline risk."


def test_news_data_status_missing_adds_warning(db: Session) -> None:
    user = _create_user(db)
    _create_asset(db, symbol="AAPL", name="Apple Inc.", market="NASDAQ")

    bundle = ContextBuilder(db).build_context_bundle(
        LLMTaskType.WATCHLIST_NOTE,
        user.id,
        [("AAPL", "NASDAQ")],
    )

    assert bundle.data_quality.news_data_status == DataQualityStatus.MISSING
    assert "뉴스 데이터는 아직 포함되지 않았습니다." in bundle.data_quality.warnings


def test_unheld_symbol_has_no_portfolio_context(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _create_user(db)
    held_asset = _create_asset(db, symbol="AAPL", name="Apple Inc.", market="NASDAQ")
    _create_asset(db, symbol="MSFT", name="Microsoft Corp.", market="NASDAQ")
    _create_portfolio(db, user_id=user.id, asset_id=held_asset.id)
    _mock_quotes(monkeypatch, {"AAPL": Decimal("150")})

    symbol_card = ContextBuilder(db).build_symbol_context(user.id, "MSFT", "NASDAQ")

    assert symbol_card.portfolio_context is None


def test_recent_decisions_are_empty_without_matching_symbol(db: Session) -> None:
    user = _create_user(db)
    _create_decision_log(db, user_id=user.id, ticker="MSFT", reason=None)

    decisions = ContextBuilder(db).build_recent_decision_context(user.id, "AAPL")

    assert decisions == []


def test_missing_asset_and_portfolio_degrade_without_exception(db: Session) -> None:
    user = _create_user(db)

    bundle = ContextBuilder(db).build_context_bundle(
        LLMTaskType.WATCHLIST_NOTE,
        user.id,
        [("UNKNOWN", "NASDAQ")],
    )

    symbol_card = bundle.symbol_cards[0]
    assert symbol_card.display_name == ""
    assert symbol_card.portfolio_context is None
    assert symbol_card.recent_news == []
    assert symbol_card.signals == []
    assert bundle.portfolio_summary is None
    assert bundle.recent_decisions == []
    assert bundle.data_quality.price_data_status == DataQualityStatus.MISSING
    assert bundle.data_quality.portfolio_data_status == DataQualityStatus.MISSING


def _create_user(db: Session) -> User:
    user = User(email="owner@example.com", hashed_password="test-hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_asset(db: Session, *, symbol: str, name: str, market: str) -> Asset:
    asset = Asset(symbol=symbol, name=name, market=market)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _create_price_bars(
    db: Session,
    *,
    symbol: str,
    market: str,
    count: int,
) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = [
        StockPriceBar(
            symbol=symbol,
            market=market,
            interval="1d",
            timestamp=start + timedelta(days=index),
            open_price=Decimal(100 + index),
            high_price=Decimal(101 + index),
            low_price=Decimal(100 + index),
            close_price=Decimal(101 + index),
            adjusted_close_price=Decimal(101 + index),
            volume=1000 + index,
            currency="USD",
            source="test",
        )
        for index in range(count)
    ]
    db.add_all(bars)
    db.commit()


def _create_portfolio(db: Session, *, user_id: int, asset_id: int) -> None:
    portfolio = Portfolio(
        user_id=user_id,
        name="Core",
        concentration_threshold=Decimal("0.50"),
        cash_balance=Decimal("1000"),
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    db.add(
        Position(
            portfolio_id=portfolio.id,
            asset_id=asset_id,
            quantity=Decimal("10"),
            avg_buy_price=Decimal("100"),
        )
    )
    db.commit()


def _create_decision_log(
    db: Session,
    *,
    user_id: int,
    ticker: str,
    reason: str | None,
) -> DecisionLog:
    decision_log = DecisionLog(
        user_id=user_id,
        target_type="SYMBOL",
        target_id=ticker,
        symbol=ticker,
        decision_type="WATCH",
        rationale=reason,
        created_by="USER",
        decided_at=datetime(2026, 6, 26, tzinfo=UTC),
    )
    db.add(decision_log)
    db.commit()
    db.refresh(decision_log)
    return decision_log


def _create_news_item(
    db: Session,
    *,
    asset_id: int,
    title: str,
    summary: str | None = "Sales momentum remains stable.",
    published_at: datetime | None = datetime(2026, 6, 30, tzinfo=UTC),
    trust_level: str | None = None,
) -> NewsItem:
    news_item = NewsItem(
        asset_id=asset_id,
        title=title,
        url=f"https://example.com/news/{asset_id}/{title.replace(' ', '-')}",
        source="test-wire",
        published_at=published_at,
        summary=summary,
        trust_level=trust_level,
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    db.add(news_item)
    db.commit()
    db.refresh(news_item)
    return news_item


def _create_signal(
    db: Session,
    *,
    asset_id: int,
    signal_type: str,
    score: int,
    risk_level: str | None,
    reason: str,
    expires_at: datetime | None,
) -> Signal:
    signal = Signal(
        asset_id=asset_id,
        signal_type=signal_type,
        score=score,
        risk_level=risk_level,
        reason=reason,
        expires_at=expires_at,
        created_at=datetime.now(UTC),
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    return signal


def _mock_quotes(
    monkeypatch: pytest.MonkeyPatch,
    prices_by_symbol: dict[str, Decimal],
) -> None:
    class QuoteProvider:
        def get_quote(self, symbols: list[str]) -> list[QuoteResult]:
            return [
                QuoteResult(
                    symbol=symbol,
                    name=symbol,
                    price=prices_by_symbol[symbol],
                    previous_close=prices_by_symbol[symbol],
                    change=Decimal("0"),
                    change_percent=Decimal("0"),
                    currency="USD",
                    as_of=datetime(2026, 7, 1, tzinfo=UTC),
                )
                for symbol in symbols
                if symbol in prices_by_symbol
            ]

    monkeypatch.setattr(
        "app.domains.portfolios.service.get_market_provider",
        lambda: QuoteProvider(),
    )
