from datetime import UTC, datetime

from app.adapters.llm.types import LLMTaskType, RiskLevel
from app.domains.llm_context.risk import derive_risk_level
from app.domains.llm_context.schema import (
    DataQualitySection,
    DataQualityStatus,
    LLMContextBundle,
    OutputContract,
    PortfolioContext,
    PortfolioSummary,
    PriceSnapshot,
    SignalItem,
    SymbolCard,
)


def test_derive_risk_level_returns_high_for_high_signal() -> None:
    bundle = _bundle(
        [
            _symbol_card(
                signals=[SignalItem(type="news", severity="high", reason="sharp move")]
            )
        ]
    )

    assert derive_risk_level(bundle) == RiskLevel.HIGH


def test_derive_risk_level_returns_high_for_unrealized_loss_threshold() -> None:
    bundle = _bundle(
        [
            _symbol_card(
                portfolio_context=PortfolioContext(
                    holding=True,
                    weight=0.2,
                    avg_buy_price=100.0,
                    unrealized_return=-0.10,
                )
            )
        ]
    )

    assert derive_risk_level(bundle) == RiskLevel.HIGH


def test_derive_risk_level_returns_low_without_high_risk_signal_or_loss() -> None:
    bundle = _bundle(
        [
            _symbol_card(
                signals=[SignalItem(type="news", severity="medium", reason="watch")],
                portfolio_context=PortfolioContext(
                    holding=True,
                    weight=0.2,
                    avg_buy_price=100.0,
                    unrealized_return=-0.09,
                ),
            )
        ]
    )

    assert derive_risk_level(bundle) == RiskLevel.LOW


def test_derive_risk_level_skips_missing_portfolio_context() -> None:
    bundle = _bundle([_symbol_card(portfolio_context=None)])

    assert derive_risk_level(bundle) == RiskLevel.LOW


def _bundle(symbol_cards: list[SymbolCard]) -> LLMContextBundle:
    return LLMContextBundle(
        task_type=LLMTaskType.WATCHLIST_NOTE,
        as_of=datetime(2026, 7, 5, tzinfo=UTC),
        user_intent="watch",
        symbols=[card.symbol for card in symbol_cards],
        data_quality=DataQualitySection(
            price_data_status=DataQualityStatus.VALID,
            news_data_status=DataQualityStatus.VALID,
            portfolio_data_status=DataQualityStatus.VALID,
            warnings=[],
        ),
        symbol_cards=symbol_cards,
        portfolio_summary=PortfolioSummary(
            cash_ratio=0.1,
            top_holding_weight=0.2,
            concentration_risk="low",
        ),
        user_rules=[],
        recent_decisions=[],
        output_contract=OutputContract(required_fields=["summary"]),
    )


def _symbol_card(
    *,
    signals: list[SignalItem] | None = None,
    portfolio_context: PortfolioContext | None = PortfolioContext(
        holding=False,
        weight=None,
        avg_buy_price=None,
        unrealized_return=None,
    ),
) -> SymbolCard:
    return SymbolCard(
        symbol="AAPL",
        market="NASDAQ",
        display_name="Apple Inc.",
        price_snapshot=PriceSnapshot(
            close=100.0,
            return_1d=0.01,
            return_5d=0.02,
            return_20d=0.03,
            drawdown_from_52w_high=-0.05,
            volume_vs_20d_avg=1.2,
        ),
        portfolio_context=portfolio_context,
        recent_news=[],
        signals=[] if signals is None else signals,
    )
