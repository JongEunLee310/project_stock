from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters.llm.exceptions import CloudBoundaryViolationError
from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.privacy import (
    CloudSafePayload,
    PrivacyGate,
    WatchlistHighlight,
    WatchlistObservationSnapshot,
    to_watchlist_observation_snapshot,
)
from app.adapters.llm.schema import ObservationsResult
from app.adapters.llm.types import LLMTaskType, SensitivityLevel
from app.adapters.market.base import QuoteResult
from app.core.config import settings
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.signals.repository import SignalRepository
from app.domains.signals.schema import SignalCreate
from app.domains.signals.types import SignalType
from app.domains.watchlists.model import Watchlist
from app.domains.watchlists.observations_service import WatchlistObservationsService
from app.domains.watchlists.repository import WatchlistItemRepository, WatchlistRepository
from tests.conftest import api_data, api_error, set_current_user


class ObservationRecordingGateway(LLMGateway):
    def __init__(self) -> None:
        self.calls: list[
            tuple[LLMTaskType, CloudSafePayload, type[BaseModel], str]
        ] = []

    def complete_json(
        self,
        task_type: LLMTaskType,
        payload: CloudSafePayload,
        schema: type[BaseModel],
        system_prompt: str,
    ) -> dict[str, Any]:
        self.calls.append((task_type, payload, schema, system_prompt))
        return {
            "summary": "Two names need review.",
            "items": [
                {"symbol": "AAPL", "note": "Risk signal is active."},
                {"symbol": "MSFT", "note": "No active signal."},
            ],
        }


def create_asset(db: Session, symbol: str) -> int:
    return AssetRepository(db).create(
        symbol=symbol,
        name=f"{symbol} Inc.",
        market="NASDAQ",
        sector="Technology",
        industry=None,
        description=None,
    ).id


def test_watchlist_observation_snapshot_is_cloudsafe_without_monetary_fields() -> None:
    snapshot = to_watchlist_observation_snapshot(
        7,
        [
            WatchlistHighlight(
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
    assert snapshot.item_count == 1
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
    serialized = str(payload)
    for forbidden in ["quantity", "market_value", "cost_value", "avg_buy_price"]:
        assert forbidden not in serialized


def test_watchlist_observation_privacy_gate_rejects_original_entity() -> None:
    watchlist = Watchlist(id=1, user_id=1, name="Core")

    with pytest.raises(CloudBoundaryViolationError):
        PrivacyGate().guard(watchlist)


def test_watchlist_observations_service_maps_gateway_result(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aapl_id = create_asset(db, "AAPL")
    msft_id = create_asset(db, "MSFT")
    watchlist = WatchlistRepository(db).create(user_id=1, name="Core")
    item_repo = WatchlistItemRepository(db)
    item_repo.create(watchlist.id, aapl_id, priority=0, reason=None, tags=[], memo=None)
    item_repo.create(watchlist.id, msft_id, priority=1, reason=None, tags=[], memo=None)
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
        "app.domains.watchlists.observations_service.get_market_provider",
        lambda: RecordingMarketProvider(),
    )
    gateway = ObservationRecordingGateway()

    result = WatchlistObservationsService(db, gateway).generate(watchlist.id, user_id=1)

    assert result.summary == "Two names need review."
    assert [item.symbol for item in result.items] == ["AAPL", "MSFT"]
    task_type, payload, schema, _prompt = gateway.calls[0]
    assert task_type == LLMTaskType.WATCHLIST_NOTE
    assert isinstance(payload, WatchlistObservationSnapshot)
    assert payload.watchlist_id == watchlist.id
    assert payload.item_count == 2
    assert [item.symbol for item in payload.items] == ["AAPL", "MSFT"]
    assert payload.items[0].status == SignalType.RISK_ALERT.value
    assert payload.items[0].per == Decimal("31.20")
    assert payload.items[1].status == "NORMAL"
    assert schema is ObservationsResult


def test_watchlist_observations_service_handles_empty_watchlist(db: Session) -> None:
    watchlist = WatchlistRepository(db).create(user_id=1, name="Empty")
    gateway = ObservationRecordingGateway()

    WatchlistObservationsService(db, gateway).generate(watchlist.id, user_id=1)

    _task_type, payload, _schema, _prompt = gateway.calls[0]
    assert isinstance(payload, WatchlistObservationSnapshot)
    assert payload.items == []
    assert payload.item_count == 0


def test_watchlist_observations_service_limits_items_after_dedup(db: Session) -> None:
    watchlist = WatchlistRepository(db).create(user_id=1, name="Large")
    item_repo = WatchlistItemRepository(db)
    for index in range(31):
        asset_id = create_asset(db, f"SYM{index:02d}")
        item_repo.create(
            watchlist.id,
            asset_id,
            priority=index,
            reason=None,
            tags=[],
            memo=None,
        )
    gateway = ObservationRecordingGateway()

    WatchlistObservationsService(db, gateway).generate(watchlist.id, user_id=1)

    _task_type, payload, _schema, _prompt = gateway.calls[0]
    assert isinstance(payload, WatchlistObservationSnapshot)
    assert payload.item_count == 30
    assert [item.symbol for item in payload.items] == [
        f"SYM{index:02d}" for index in range(30)
    ]


def test_watchlist_observations_service_raises_404_for_missing_watchlist(
    db: Session,
) -> None:
    with pytest.raises(AppException) as exc_info:
        WatchlistObservationsService(db, ObservationRecordingGateway()).generate(
            999,
            user_id=1,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.error_code == "WATCHLIST_NOT_FOUND"


def test_watchlist_observations_service_raises_403_for_other_user(
    db: Session,
) -> None:
    watchlist = WatchlistRepository(db).create(user_id=1, name="Core")

    with pytest.raises(AppException) as exc_info:
        WatchlistObservationsService(db, ObservationRecordingGateway()).generate(
            watchlist.id,
            user_id=2,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.error_code == "WATCHLIST_FORBIDDEN"


def test_watchlist_observations_endpoint_returns_enveloped_mock_response(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    set_current_user(1)
    watchlist_response = client.post("/api/v1/watchlists", json={"name": "Core"})
    watchlist = cast(dict[str, Any], api_data(watchlist_response))

    response = client.get(f"/api/v1/watchlists/{watchlist['id']}/observations")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["summary"] == "Mock watchlist observation summary."
    assert data["items"] == [
        {"symbol": "AAPL", "note": "Mock watchlist observation note."}
    ]
    assert isinstance(data["generated_at"], str)


def test_watchlist_observations_endpoint_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/watchlists/1/observations")

    assert response.status_code == 401


def test_watchlist_observations_endpoint_returns_404_for_missing_watchlist(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    set_current_user(1)

    response = client.get("/api/v1/watchlists/999/observations")

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "WATCHLIST_NOT_FOUND",
        "message": "관심 목록을 찾을 수 없습니다.",
    }


def test_watchlist_observations_endpoint_blocks_other_users(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    set_current_user(1)
    watchlist_response = client.post("/api/v1/watchlists", json={"name": "Core"})
    watchlist = cast(dict[str, Any], api_data(watchlist_response))
    set_current_user(2, "other@example.com")

    response = client.get(f"/api/v1/watchlists/{watchlist['id']}/observations")

    assert response.status_code == 403
    assert api_error(response) == {
        "code": "WATCHLIST_FORBIDDEN",
        "message": "관심 목록 접근 권한이 없습니다.",
    }
