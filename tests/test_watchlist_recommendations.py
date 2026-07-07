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
    StockRecommendationCandidate,
    StockRecommendationSnapshot,
    to_stock_recommendation_snapshot,
)
from app.adapters.llm.schema import StockRecommendationResult
from app.adapters.llm.types import LLMTaskType, SensitivityLevel
from app.adapters.market.base import QuoteResult
from app.core.config import settings
from app.domains.assets.repository import AssetRepository
from app.domains.signals.repository import SignalRepository
from app.domains.signals.schema import SignalCreate
from app.domains.signals.types import SignalType
from app.domains.watchlists.recommendations_service import (
    RECOMMENDATION_CANDIDATE_LIMIT,
    RECOMMENDATION_MAX_ITEMS,
    WatchlistRecommendationsService,
)
from app.domains.watchlists.repository import WatchlistItemRepository, WatchlistRepository
from tests.conftest import api_data, api_error, set_current_user


class RecommendationRecordingGateway(LLMGateway):
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


class FailingGateway(LLMGateway):
    def __init__(self) -> None:
        pass

    def complete_json(
        self,
        task_type: LLMTaskType,
        payload: CloudSafePayload,
        schema: type[BaseModel],
        system_prompt: str,
        escalation_signal: EscalationSignal | None = None,
    ) -> LLMCompletionResult:
        raise AssertionError("LLM should not be called")


def create_asset(db: Session, symbol: str, sector: str | None = "Technology") -> int:
    return AssetRepository(db).create(
        symbol=symbol,
        name=f"{symbol} Inc.",
        market="NASDAQ",
        sector=sector,
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


def test_stock_recommendation_snapshot_is_cloudsafe() -> None:
    snapshot = to_stock_recommendation_snapshot(
        7,
        ["MSFT"],
        [
            StockRecommendationCandidate(
                symbol="AAPL",
                name="AAPL Inc.",
                sector="Technology",
                status=SignalType.BUY_CANDIDATE.value,
                per=Decimal("31.20"),
                peg=Decimal("2.45"),
                daily_change_percent=Decimal("1.26"),
            )
        ],
    )

    payload = snapshot.as_payload()

    assert snapshot.sensitivity == SensitivityLevel.AGGREGATED
    assert snapshot.candidate_count == 1
    assert PrivacyGate().guard(snapshot) is snapshot
    assert payload == {
        "watchlist_id": 7,
        "current_symbols": ["MSFT"],
        "candidate_count": 1,
        "candidates": [
            {
                "symbol": "AAPL",
                "name": "AAPL Inc.",
                "sector": "Technology",
                "status": SignalType.BUY_CANDIDATE.value,
                "per": "31.20",
                "peg": "2.45",
                "daily_change_percent": "1.26",
            }
        ],
    }


def test_watchlist_recommendations_service_excludes_current_items_and_maps_result(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_asset_id = create_asset(db, "MSFT")
    candidate_asset_id = create_asset(db, "AAPL")
    watchlist = WatchlistRepository(db).create(user_id=1, name="Core")
    add_watchlist_item(db, watchlist.id, current_asset_id)
    SignalRepository(db).create(
        SignalCreate(
            asset_id=candidate_asset_id,
            signal_type=SignalType.BUY_CANDIDATE,
            score=90,
            reason="Candidate signal.",
        )
    )

    class RecordingMarketProvider:
        def get_quote(self, symbols: list[str]) -> list[QuoteResult]:
            assert symbols == ["AAPL"]
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
        "app.domains.watchlists.recommendations_service.get_market_provider",
        lambda: RecordingMarketProvider(),
    )
    gateway = RecommendationRecordingGateway(
        {
            "recommendations": [
                {
                    "symbol": "AAPL",
                    "rationale": "Buy candidate with positive daily change.",
                    "reference_metrics": ["BUY_CANDIDATE", "PER 31.20"],
                }
            ]
        }
    )

    result = WatchlistRecommendationsService(db, gateway).generate(
        watchlist.id,
        user_id=1,
    )

    assert [item.symbol for item in result.recommendations] == ["AAPL"]
    assert result.recommendations[0].name == "AAPL Inc."
    assert result.recommendations[0].reference_metrics == [
        "BUY_CANDIDATE",
        "PER 31.20",
    ]
    task_type, payload, schema, _prompt = gateway.calls[0]
    assert task_type == LLMTaskType.STOCK_RECOMMENDATION
    assert isinstance(payload, StockRecommendationSnapshot)
    assert payload.current_symbols == ["MSFT"]
    assert [candidate.symbol for candidate in payload.candidates] == ["AAPL"]
    assert payload.candidates[0].status == SignalType.BUY_CANDIDATE.value
    assert payload.candidates[0].per == Decimal("31.20")
    assert schema is StockRecommendationResult


def test_watchlist_recommendations_service_filters_symbols_outside_candidates(
    db: Session,
) -> None:
    create_asset(db, "AAPL")
    watchlist = WatchlistRepository(db).create(user_id=1, name="Core")
    gateway = RecommendationRecordingGateway(
        {
            "recommendations": [
                {
                    "symbol": "AAPL",
                    "rationale": "Valid candidate.",
                    "reference_metrics": ["Mock metric"],
                },
                {
                    "symbol": "FAKE",
                    "rationale": "Invalid candidate.",
                    "reference_metrics": ["Should be filtered"],
                },
            ]
        }
    )

    result = WatchlistRecommendationsService(db, gateway).generate(
        watchlist.id,
        user_id=1,
    )

    assert [item.symbol for item in result.recommendations] == ["AAPL"]


def test_watchlist_recommendations_service_caps_candidates_in_id_order(
    db: Session,
) -> None:
    watchlist = WatchlistRepository(db).create(user_id=1, name="Core")
    for index in range(RECOMMENDATION_CANDIDATE_LIMIT + 1):
        create_asset(db, f"SYM{index:02d}")
    gateway = RecommendationRecordingGateway({"recommendations": []})

    WatchlistRecommendationsService(db, gateway).generate(watchlist.id, user_id=1)

    _task_type, payload, _schema, _prompt = gateway.calls[0]
    assert isinstance(payload, StockRecommendationSnapshot)
    assert payload.candidate_count == RECOMMENDATION_CANDIDATE_LIMIT
    assert [candidate.symbol for candidate in payload.candidates] == [
        f"SYM{index:02d}" for index in range(RECOMMENDATION_CANDIDATE_LIMIT)
    ]


def test_watchlist_recommendations_service_caps_projected_recommendations(
    db: Session,
) -> None:
    watchlist = WatchlistRepository(db).create(user_id=1, name="Core")
    symbols = [f"SYM{index:02d}" for index in range(RECOMMENDATION_MAX_ITEMS + 1)]
    for symbol in symbols:
        create_asset(db, symbol)
    gateway = RecommendationRecordingGateway(
        {
            "recommendations": [
                {
                    "symbol": symbol,
                    "rationale": f"{symbol} rationale.",
                    "reference_metrics": ["Mock metric"],
                }
                for symbol in symbols
            ]
        }
    )

    result = WatchlistRecommendationsService(db, gateway).generate(
        watchlist.id,
        user_id=1,
    )

    assert [item.symbol for item in result.recommendations] == symbols[
        :RECOMMENDATION_MAX_ITEMS
    ]


def test_watchlist_recommendations_service_returns_empty_without_llm_for_no_candidates(
    db: Session,
) -> None:
    asset_id = create_asset(db, "AAPL")
    watchlist = WatchlistRepository(db).create(user_id=1, name="Core")
    add_watchlist_item(db, watchlist.id, asset_id)

    result = WatchlistRecommendationsService(db, FailingGateway()).generate(
        watchlist.id,
        user_id=1,
    )

    assert result.recommendations == []


def test_watchlist_recommendations_endpoint_returns_mock_recommendation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    set_current_user(1)
    asset_response = client.post(
        "/api/v1/assets",
        json={"symbol": "AAPL", "name": "AAPL Inc.", "market": "NASDAQ"},
    )
    assert asset_response.status_code == 201
    watchlist_response = client.post("/api/v1/watchlists", json={"name": "Core"})
    watchlist = cast(dict[str, Any], api_data(watchlist_response))

    response = client.get(f"/api/v1/watchlists/{watchlist['id']}/recommendations")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["recommendations"] == [
        {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "rationale": "Mock recommendation rationale.",
            "reference_metrics": ["Mock metric A", "Mock metric B"],
        }
    ]
    assert isinstance(data["generated_at"], str)


def test_watchlist_recommendations_endpoint_returns_404_for_missing_watchlist(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    set_current_user(1)

    response = client.get("/api/v1/watchlists/999/recommendations")

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "WATCHLIST_NOT_FOUND",
        "message": "관심 목록을 찾을 수 없습니다.",
    }


def test_watchlist_recommendations_endpoint_blocks_other_users(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    set_current_user(1)
    watchlist_response = client.post("/api/v1/watchlists", json={"name": "Core"})
    watchlist = cast(dict[str, Any], api_data(watchlist_response))
    set_current_user(2, "other@example.com")

    response = client.get(f"/api/v1/watchlists/{watchlist['id']}/recommendations")

    assert response.status_code == 403
    assert api_error(response) == {
        "code": "WATCHLIST_FORBIDDEN",
        "message": "관심 목록 접근 권한이 없습니다.",
    }
