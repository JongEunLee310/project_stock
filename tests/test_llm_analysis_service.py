from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.mock import MockLLMClient
from app.adapters.llm.privacy import (
    PrivacyGate,
    to_context_bundle_snapshot,
)
from app.adapters.llm.prompts.analysis import ANALYSIS_PROMPT_VERSION
from app.adapters.llm.types import LLMTaskType, SensitivityLevel
from app.adapters.market.base import QuoteResult
from app.domains.assets.model import Asset
from app.domains.llm_analysis.repository import LLMAnalysisRunRepository
from app.domains.llm_analysis.schema import (
    LLMAnalysisRunCreate,
    RunStatus,
)
from app.domains.llm_analysis.service import LLMAnalysisService
from app.domains.llm_context.context_builder import ContextBuilder
from app.domains.portfolios.model import Portfolio, Position
from app.domains.prices.model import StockPriceBar
from app.domains.users.model import User


VALID_ANALYSIS_RESPONSE = {
    "summary": "AAPL context remains constructive.",
    "risk_level": "LOW",
    "suggested_action": "hold",
    "reasons": ["Price trend is intact."],
    "watch_points": ["Watch concentration risk."],
    "counter_arguments": ["News coverage is limited."],
    "data_limitations": ["Mock data only."],
    "confidence": 0.72,
}


def test_run_analysis_persists_input_and_successful_output(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, asset = _create_analysis_sources(db, monkeypatch)
    gateway = LLMGateway(
        clients={"cloud": MockLLMClient({"LLMAnalysisResult": VALID_ANALYSIS_RESPONSE})}
    )

    run = LLMAnalysisService(db, gateway).run_analysis(
        LLMTaskType.WATCHLIST_NOTE,
        user.id,
        [(asset.symbol, asset.market)],
    )

    assert run.status == RunStatus.SUCCEEDED.value
    assert run.input_context_json["symbols"] == ["AAPL"]
    assert run.input_context_json["symbol_cards"][0]["portfolio_context"][
        "avg_buy_price"
    ] == 100.0
    assert run.output_json == VALID_ANALYSIS_RESPONSE
    assert run.prompt_version == ANALYSIS_PROMPT_VERSION
    assert run.model_name == "mock"
    assert run.provider == "mock"


def test_run_analysis_records_failed_status_on_schema_error(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, asset = _create_analysis_sources(db, monkeypatch)
    gateway = LLMGateway(
        clients={"cloud": MockLLMClient({"LLMAnalysisResult": {"summary": "invalid"}})}
    )

    run = LLMAnalysisService(db, gateway).run_analysis(
        LLMTaskType.WATCHLIST_NOTE,
        user.id,
        [(asset.symbol, asset.market)],
    )

    assert run.status == RunStatus.FAILED.value
    assert run.error_message is not None
    assert "risk_level" in run.error_message
    assert run.input_context_json["symbols"] == ["AAPL"]
    assert run.output_json is None


def test_context_bundle_projection_is_cloud_safe_without_avg_buy_price(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, asset = _create_analysis_sources(db, monkeypatch)
    bundle = ContextBuilder(db).build_context_bundle(
        LLMTaskType.WATCHLIST_NOTE,
        user.id,
        [(asset.symbol, asset.market)],
    )

    projection = to_context_bundle_snapshot(bundle)
    payload = projection.as_payload()
    projected_context = payload["symbol_cards"][0]["portfolio_context"]

    assert projection.sensitivity == SensitivityLevel.AGGREGATED
    assert "avg_buy_price" in str(bundle.model_dump(mode="json"))
    assert "avg_buy_price" not in str(payload)
    assert projected_context["holding"] is True
    assert projected_context["weight"] == pytest.approx(0.6)
    assert projected_context["unrealized_return"] == pytest.approx(0.5)
    assert PrivacyGate().guard(projection) == projection


def test_llm_analysis_repository_round_trip(db: Session) -> None:
    user = _create_user(db)
    repository = LLMAnalysisRunRepository(db)

    run = repository.create(
        LLMAnalysisRunCreate(
            user_id=user.id,
            task_type=LLMTaskType.WATCHLIST_NOTE,
            related_symbols=["AAPL"],
            input_context_json={"symbols": ["AAPL"]},
        )
    )
    found = repository.get_by_id(run.id)

    assert found is not None
    assert found.status == RunStatus.PENDING.value

    succeeded = repository.mark_succeeded(
        run.id,
        output_json=VALID_ANALYSIS_RESPONSE,
        model_name="test-model",
        prompt_version="test-prompt",
        provider="cloud",
    )
    assert succeeded.status == RunStatus.SUCCEEDED.value
    assert succeeded.output_json == VALID_ANALYSIS_RESPONSE
    assert succeeded.model_name == "test-model"
    assert succeeded.prompt_version == "test-prompt"
    assert succeeded.provider == "cloud"

    failed = repository.mark_failed(run.id, "gateway failed")
    assert failed.status == RunStatus.FAILED.value
    assert failed.error_message == "gateway failed"


def _create_analysis_sources(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[User, Asset]:
    user = _create_user(db)
    asset = _create_asset(db, symbol="AAPL", name="Apple Inc.", market="NASDAQ")
    _create_price_bars(db, symbol="AAPL", market="NASDAQ", count=252)
    _create_portfolio(db, user_id=user.id, asset_id=asset.id)
    _mock_quotes(monkeypatch, {"AAPL": Decimal("150")})
    return user, asset


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
