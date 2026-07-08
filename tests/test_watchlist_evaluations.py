from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters.llm.escalation import EscalationSignal
from app.adapters.llm.gateway import LLMCompletionResult, LLMGateway
from app.adapters.llm.privacy import (
    CloudSafePayload,
    PrivacyGate,
    WatchlistEvaluationItem,
    WatchlistEvaluationSnapshot,
)
from app.adapters.llm.schema import WatchlistEvaluationsResult
from app.adapters.llm.types import LLMTaskType, SensitivityLevel
from app.adapters.market.base import QuoteResult
from app.core.config import settings
from app.domains.assets.repository import AssetRepository
from app.domains.signals.repository import SignalRepository
from app.domains.signals.schema import SignalCreate
from app.domains.signals.types import SignalType
from app.domains.watchlists.evaluations_service import WatchlistEvaluationsService
from app.domains.watchlists.repository import WatchlistItemRepository, WatchlistRepository
from app.domains.watchlists.types import (
    AiJudgment,
    NewsRisk,
    ThemeHeat,
    ValuationBurden,
)
from tests.conftest import api_data, set_current_user


class EvaluationRecordingGateway(LLMGateway):
    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output
        self.calls: list[
            tuple[LLMTaskType, CloudSafePayload, type[BaseModel], str]
        ] = []

    def complete_json(
        self,
        task_type: LLMTaskType,
        payload: CloudSafePayload,
        schema: type[BaseModel],
        system_prompt: str,
        escalation_signal: EscalationSignal | None = None,
    ) -> LLMCompletionResult:
        self.calls.append((task_type, payload, schema, system_prompt))
        return LLMCompletionResult(
            output=self.output,
            provider="mock",
            model_name="mock",
        )


def create_asset(db: Session, symbol: str) -> int:
    return AssetRepository(db).create(
        symbol=symbol,
        name=f"{symbol} Inc.",
        market="NASDAQ",
        sector="Technology",
        industry=None,
        description=None,
    ).id


def add_watchlist_item(db: Session, watchlist_id: int, asset_id: int) -> None:
    WatchlistItemRepository(db).create(
        watchlist_id,
        asset_id,
        priority=0,
        reason=None,
        tags=[],
        memo=None,
    )


def evaluation_item(
    symbol: str,
    news_risk: NewsRisk,
    ai_judgment: AiJudgment,
) -> dict[str, str]:
    # Enum values are sourced from app/domains/watchlists/types.py.
    return {
        "symbol": symbol,
        "news_risk": news_risk.value,
        "valuation_burden": ValuationBurden.MODERATE.value,
        "theme_heat": ThemeHeat.NEUTRAL.value,
        "ai_judgment": ai_judgment.value,
    }


def test_watchlist_evaluation_snapshot_is_cloudsafe() -> None:
    snapshot = WatchlistEvaluationSnapshot(
        watchlist_id=7,
        item_count=1,
        items=[
            WatchlistEvaluationItem(
                symbol="AAPL",
                status=SignalType.RISK_ALERT.value,
                per=Decimal("31.20"),
                peg=Decimal("2.45"),
                daily_change_percent=Decimal("1.26"),
            )
        ],
    )

    payload = snapshot.as_payload()

    assert snapshot.sensitivity == SensitivityLevel.AGGREGATED
    assert PrivacyGate().guard(snapshot) is snapshot
    assert payload == {
        "watchlist_id": 7,
        "item_count": 1,
        "items": [
            {
                "symbol": "AAPL",
                "status": SignalType.RISK_ALERT.value,
                "per": "31.20",
                "peg": "2.45",
                "daily_change_percent": "1.26",
            }
        ],
    }


def test_watchlist_evaluations_service_maps_gateway_result_and_snapshot(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aapl_id = create_asset(db, "AAPL")
    msft_id = create_asset(db, "MSFT")
    watchlist = WatchlistRepository(db).create(user_id=1, name="Core")
    add_watchlist_item(db, watchlist.id, aapl_id)
    add_watchlist_item(db, watchlist.id, msft_id)
    SignalRepository(db).create(
        SignalCreate(
            asset_id=aapl_id,
            signal_type=SignalType.RISK_ALERT,
            score=90,
            reason="Risk active signal.",
        )
    )

    class RecordingMarketProvider:
        def get_quote(self, symbols: list[str]) -> list[QuoteResult]:
            assert symbols == ["AAPL", "MSFT"]
            return [
                QuoteResult(
                    symbol="AAPL",
                    name="Apple Inc.",
                    price=Decimal("195.64"),
                    previous_close=Decimal("193.20"),
                    change=Decimal("2.44"),
                    change_percent=Decimal("1.26"),
                    currency="USD",
                    as_of=datetime(2026, 6, 19, tzinfo=timezone.utc),
                    per=Decimal("31.20"),
                    peg=Decimal("2.45"),
                )
            ]

    monkeypatch.setattr(
        "app.domains.watchlists.evaluations_service.get_market_provider",
        lambda: RecordingMarketProvider(),
    )
    gateway = EvaluationRecordingGateway(
        {
            "items": [
                evaluation_item("AAPL", NewsRisk.HIGH, AiJudgment.RISK_INCREASING),
                evaluation_item("MSFT", NewsRisk.LOW, AiJudgment.WATCH),
                evaluation_item("FAKE", NewsRisk.HIGH, AiJudgment.WATCH),
            ]
        }
    )

    result = WatchlistEvaluationsService(db, gateway).generate(
        watchlist.id,
        user_id=1,
    )

    assert [item.symbol for item in result.items] == ["AAPL", "MSFT"]
    assert result.needs_research_count == 1
    assert "cash_relevance_avg" not in result.model_dump()
    task_type, payload, schema, _prompt = gateway.calls[0]
    assert task_type == LLMTaskType.WATCHLIST_EVALUATION
    assert isinstance(payload, WatchlistEvaluationSnapshot)
    assert payload.watchlist_id == watchlist.id
    assert payload.item_count == 2
    assert [item.symbol for item in payload.items] == ["AAPL", "MSFT"]
    assert payload.items[0].status == SignalType.RISK_ALERT.value
    assert payload.items[0].per == Decimal("31.20")
    assert payload.items[1].status == "NORMAL"
    assert schema is WatchlistEvaluationsResult


def test_watchlist_evaluations_service_aggregates_research_count(
    db: Session,
) -> None:
    watchlist = WatchlistRepository(db).create(user_id=1, name="Core")
    for symbol in ["AAPL", "MSFT", "NVDA", "TSLA"]:
        add_watchlist_item(db, watchlist.id, create_asset(db, symbol))
    gateway = EvaluationRecordingGateway(
        {
            "items": [
                evaluation_item("AAPL", NewsRisk.HIGH, AiJudgment.STABLE),
                evaluation_item("MSFT", NewsRisk.LOW, AiJudgment.RISK_INCREASING),
                evaluation_item("NVDA", NewsRisk.HIGH, AiJudgment.RISK_INCREASING),
                evaluation_item("TSLA", NewsRisk.LOW, AiJudgment.WATCH),
            ]
        }
    )

    result = WatchlistEvaluationsService(db, gateway).generate(watchlist.id, user_id=1)

    assert result.needs_research_count == 3
    assert "cash_relevance_avg" not in result.model_dump()


def test_watchlist_evaluations_service_skips_invalid_enum_item(
    db: Session,
) -> None:
    watchlist = WatchlistRepository(db).create(user_id=1, name="Core")
    add_watchlist_item(db, watchlist.id, create_asset(db, "AAPL"))
    add_watchlist_item(db, watchlist.id, create_asset(db, "MSFT"))
    gateway = EvaluationRecordingGateway(
        {
            "items": [
                {
                    "symbol": "AAPL",
                    "news_risk": "INVALID_VALUE",
                    "valuation_burden": ValuationBurden.MODERATE.value,
                    "theme_heat": ThemeHeat.NEUTRAL.value,
                    "ai_judgment": AiJudgment.WATCH.value,
                },
                evaluation_item("MSFT", NewsRisk.LOW, AiJudgment.STABLE),
            ]
        }
    )

    result = WatchlistEvaluationsService(db, gateway).generate(watchlist.id, user_id=1)

    assert [item.symbol for item in result.items] == ["MSFT"]
    assert result.needs_research_count == 0


def test_watchlist_evaluations_service_returns_zero_aggregates_for_empty_watchlist(
    db: Session,
) -> None:
    watchlist = WatchlistRepository(db).create(user_id=1, name="Empty")
    gateway = EvaluationRecordingGateway({"items": []})

    result = WatchlistEvaluationsService(db, gateway).generate(watchlist.id, user_id=1)

    assert result.items == []
    assert result.needs_research_count == 0
    assert "cash_relevance_avg" not in result.model_dump()
    assert gateway.calls == []


def test_watchlist_evaluations_endpoint_returns_enveloped_mock_response(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    set_current_user(1)
    asset_response = client.post(
        "/api/v1/assets",
        json={"symbol": "AAPL", "name": "AAPL Inc.", "market": "NASDAQ"},
    )
    asset = cast(dict[str, Any], api_data(asset_response))
    watchlist_response = client.post("/api/v1/watchlists", json={"name": "Core"})
    watchlist = cast(dict[str, Any], api_data(watchlist_response))
    item_response = client.post(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        json={"asset_id": asset["id"], "priority": 0},
    )
    assert item_response.status_code == 201

    response = client.get(f"/api/v1/watchlists/{watchlist['id']}/evaluations")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["items"] == [
        {
            "symbol": "AAPL",
            "news_risk": NewsRisk.LOW.value,
            "valuation_burden": ValuationBurden.MODERATE.value,
            "theme_heat": ThemeHeat.NEUTRAL.value,
            "ai_judgment": AiJudgment.WATCH.value,
        }
    ]
    assert data["needs_research_count"] == 0
    assert "cash_relevance_avg" not in data
    assert isinstance(data["generated_at"], str)
