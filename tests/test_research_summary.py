from datetime import UTC, datetime
from typing import cast
from unittest.mock import Mock

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.llm.gateway import LLMCompletionResult, LLMGateway
from app.adapters.llm.mock import DEFAULT_MOCK_RESPONSES
from app.adapters.llm.privacy import ResearchSummarySnapshot
from app.adapters.llm.schema import ResearchSummaryResult
from app.adapters.llm.types import LLMTaskType
from app.domains.assets.model import Asset
from app.domains.llm_context.context_builder import ContextBuilder
from app.domains.llm_context.schema import (
    PortfolioContext,
    PriceSnapshot,
    SymbolCard,
)
from app.domains.research_summary.model import ResearchSummaryRow
from app.domains.research_summary.repository import ResearchSummaryRepository
from app.domains.research_summary.service import ResearchSummaryService


def _result(*, headline: str = "요약 제목") -> ResearchSummaryResult:
    return ResearchSummaryResult.model_validate(
        {
            **DEFAULT_MOCK_RESPONSES["ResearchSummaryResult"],
            "headline": headline,
        }
    )


def test_generate_uses_cloud_safe_snapshot_without_portfolio_context(
    db: Session,
) -> None:
    asset = Asset(symbol="AAPL", name="Apple", market="NASDAQ")
    db.add(asset)
    db.commit()
    card = SymbolCard(
        symbol=asset.symbol,
        market=asset.market,
        display_name=asset.name,
        price_snapshot=PriceSnapshot(
            close=200.0,
            return_1d=0.01,
            return_5d=0.02,
            return_20d=0.03,
            drawdown_from_52w_high=-0.04,
            volume_vs_20d_avg=1.2,
        ),
        portfolio_context=PortfolioContext(
            holding=True,
            weight=0.5,
            avg_buy_price=100.0,
            unrealized_return=1.0,
        ),
        recent_news=[],
        signals=[],
    )
    context_builder = Mock(spec=ContextBuilder)
    context_builder.build_symbol_context.return_value = card
    gateway = Mock(spec=LLMGateway)
    gateway.complete_json.return_value = LLMCompletionResult(
        output=_result().model_dump(mode="json"),
        provider="mock",
        model_name="mock",
    )

    response = ResearchSummaryService(
        db,
        cast(LLMGateway, gateway),
        cast(ContextBuilder, context_builder),
    ).generate(asset.id, user_id=7)

    context_builder.build_symbol_context.assert_called_once_with(
        7, asset.symbol, asset.market
    )
    task_type, snapshot, schema, _prompt = gateway.complete_json.call_args.args
    assert task_type is LLMTaskType.RESEARCH_SUMMARY
    assert schema is ResearchSummaryResult
    assert isinstance(snapshot, ResearchSummarySnapshot)
    assert "portfolio_context" not in snapshot.as_payload()
    assert response.asset_id == asset.id


def test_repository_upsert_keeps_one_row_per_asset(db: Session) -> None:
    asset = Asset(symbol="MSFT", name="Microsoft", market="NASDAQ")
    db.add(asset)
    db.commit()
    repository = ResearchSummaryRepository(db)

    first = repository.upsert(asset.id, _result(headline="첫 요약"))
    first_id = first.id
    first.updated_at = datetime(2020, 1, 1, tzinfo=UTC)
    db.commit()
    second = repository.upsert(asset.id, _result(headline="갱신 요약"))

    row_count = db.scalar(select(func.count(ResearchSummaryRow.id)))
    assert row_count == 1
    assert first_id == second.id
    assert second.headline == "갱신 요약"
    assert second.updated_at > datetime(2020, 1, 1)


def test_default_mock_research_summary_response_is_deterministic() -> None:
    first = ResearchSummaryResult.model_validate(
        DEFAULT_MOCK_RESPONSES["ResearchSummaryResult"]
    )
    second = ResearchSummaryResult.model_validate(
        DEFAULT_MOCK_RESPONSES["ResearchSummaryResult"]
    )

    assert first == second
    assert first.counter_points
    assert first.key_risks
