from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.market.base import QuoteResult
from app.domains.assets.model import Asset
from app.domains.news.model import NewsItem
from app.domains.signals.repository import SignalRepository
from app.domains.signals.schema import SignalCreate
from app.domains.signals.time import is_expired_at
from app.domains.signals.types import SignalType
from app.domains.theses.model import InvestmentThesis
from app.domains.users.model import User
from tests.conftest import api_data, api_meta, set_current_user


def create_asset(client: TestClient, symbol: str = "AAPL") -> dict[str, Any]:
    response = client.post(
        "/api/v1/assets",
        json={"symbol": symbol, "name": f"{symbol} Inc.", "market": "NASDAQ"},
    )
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


def signal_payload(
    asset_id: int,
    signal_type: str = SignalType.RISK_ALERT.value,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "signal_type": signal_type,
        "score": 82,
        "risk_level": "HIGH",
        "reason": "Negative guidance conflicts with the current thesis.",
        "evidence": {
            "summary": "Management lowered next-quarter guidance.",
            "factors": ["Revenue guide down", "Margin pressure"],
        },
        "expires_at": expires_at.isoformat() if expires_at is not None else None,
    }


def create_signal(
    client: TestClient,
    asset_id: int,
    signal_type: str = SignalType.RISK_ALERT.value,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/signals",
        json=signal_payload(asset_id, signal_type, expires_at),
    )
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


def create_db_asset(db: Session) -> Asset:
    asset = Asset(symbol="AAPL", name="Apple Inc.", market="NASDAQ")
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def create_db_user(db: Session) -> User:
    user = User(email="owner@example.com", hashed_password="test-hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_db_thesis(db: Session, asset_id: int, user_id: int) -> InvestmentThesis:
    thesis = InvestmentThesis(
        user_id=user_id,
        asset_id=asset_id,
        summary="Services growth should offset device cyclicality.",
    )
    db.add(thesis)
    db.commit()
    db.refresh(thesis)
    return thesis


def create_db_news_item(db: Session, asset_id: int) -> NewsItem:
    item = NewsItem(
        asset_id=asset_id,
        title="Apple lowers guidance",
        url="https://example.com/apple-guidance",
        source="Example News",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def test_create_signal_success_returns_evidence_as_dict(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)

    data = create_signal(client, asset["id"])

    assert data["id"] > 0
    assert data["asset_id"] == asset["id"]
    assert data["signal_type"] == "RISK_ALERT"
    assert data["score"] == 82
    assert data["risk_level"] == "HIGH"
    assert data["evidence"] == {
        "summary": "Management lowered next-quarter guidance.",
        "factors": ["Revenue guide down", "Margin pressure"],
    }
    assert data["is_expired"] is False
    assert "created_at" in data


def test_list_signals_excludes_expired_by_default(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)
    expired_at = datetime.now(timezone.utc) - timedelta(days=1)
    active = create_signal(client, asset["id"], SignalType.WATCH.value)
    create_signal(client, asset["id"], SignalType.SELL_REVIEW.value, expired_at)

    response = client.get("/api/v1/signals", params={"asset_id": asset["id"]})

    assert response.status_code == 200
    assert api_data(response) == [active]
    assert api_meta(response) == {"page": 1, "size": 20, "total": 1}


def test_list_signals_includes_expired_when_requested(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)
    expired_at = datetime.now(timezone.utc) - timedelta(days=1)
    active = create_signal(client, asset["id"], SignalType.WATCH.value)
    expired = create_signal(client, asset["id"], SignalType.SELL_REVIEW.value, expired_at)

    response = client.get(
        "/api/v1/signals",
        params={"asset_id": asset["id"], "include_expired": "true"},
    )

    assert response.status_code == 200
    assert api_data(response) == [expired, active]
    assert api_meta(response) == {"page": 1, "size": 20, "total": 2}


def test_list_signals_uses_page_and_size(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)
    first = create_signal(client, asset["id"], SignalType.WATCH.value)
    create_signal(client, asset["id"], SignalType.SELL_REVIEW.value)

    response = client.get(
        "/api/v1/signals",
        params={"asset_id": asset["id"], "page": 2, "size": 1},
    )

    assert response.status_code == 200
    assert api_data(response) == [first]
    assert api_meta(response) == {"page": 2, "size": 1, "total": 2}


def test_list_signals_without_expand_excludes_asset_field(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)
    create_signal(client, asset["id"], SignalType.WATCH.value)

    response = client.get("/api/v1/signals", params={"asset_id": asset["id"]})

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert len(data) == 1
    assert "asset" not in data[0]


def test_list_signals_expand_asset_includes_asset_object(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_current_user(1)
    asset = create_asset(client, "AAPL")
    create_signal(client, asset["id"], SignalType.WATCH.value)
    create_signal(client, asset["id"], SignalType.BUY_CANDIDATE.value)
    calls: list[list[str]] = []

    class RecordingMarketProvider:
        def get_quote(self, symbols: list[str]) -> list[QuoteResult]:
            calls.append(symbols)
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
                )
            ]

    monkeypatch.setattr(
        "app.domains.signals.service.get_market_provider",
        lambda: RecordingMarketProvider(),
    )

    response = client.get(
        "/api/v1/signals",
        params={"asset_id": asset["id"], "expand": "metadata, asset"},
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert len(data) == 2
    assert calls == [["AAPL"]]
    for item in data:
        brief = item["asset"]
        assert brief["symbol"] == "AAPL"
        assert brief["name"] == "AAPL Inc."
        assert brief["price"] == "195.64"
        assert brief["change_percent"] == "1.26"
        assert isinstance(brief["price"], str)
        assert isinstance(brief["change_percent"], str)
    assert api_meta(response) == {"page": 1, "size": 20, "total": 2}


def test_list_signals_expand_asset_returns_null_for_missing_asset(
    client: TestClient,
) -> None:
    set_current_user(1)
    missing_asset_id = 999
    create_signal(client, missing_asset_id, SignalType.WATCH.value)

    response = client.get(
        "/api/v1/signals",
        params={"asset_id": missing_asset_id, "expand": "asset"},
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert len(data) == 1
    assert data[0]["asset"] is None


def test_is_expired_for_past_future_and_null_expires_at(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    future = datetime.now(timezone.utc) + timedelta(minutes=5)

    expired = create_signal(client, asset["id"], SignalType.RISK_ALERT.value, past)
    active = create_signal(client, asset["id"], SignalType.WATCH.value, future)
    no_expiry = create_signal(client, asset["id"], SignalType.BUY_CANDIDATE.value)

    assert expired["is_expired"] is True
    assert active["is_expired"] is False
    assert no_expiry["is_expired"] is False


def test_get_signal_detail(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)
    signal = create_signal(client, asset["id"])

    response = client.get(f"/api/v1/signals/{signal['id']}")

    assert response.status_code == 200
    assert api_data(response) == signal


def test_get_signal_returns_404_when_missing(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/signals/999")

    assert response.status_code == 404


def test_list_signals_requires_asset_id(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/signals")

    assert response.status_code == 422


def test_create_signal_rejects_score_outside_0_to_100(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)
    payload = signal_payload(asset["id"])
    payload["score"] = 101

    response = client.post("/api/v1/signals", json=payload)

    assert response.status_code == 422


def test_is_expired_at_treats_naive_datetime_as_utc() -> None:
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)

    assert is_expired_at(datetime(2026, 6, 19, 11, 59), now) is True
    assert is_expired_at(datetime(2026, 6, 19, 12, 1), now) is False


def test_signal_repository_exists_active_ignores_expired_rows(db: Session) -> None:
    asset = create_db_asset(db)
    user = create_db_user(db)
    thesis = create_db_thesis(db, asset.id, user.id)
    news_item = create_db_news_item(db, asset.id)
    repo = SignalRepository(db)
    repo.create(
        SignalCreate(
            asset_id=asset.id,
            thesis_id=thesis.id,
            news_item_id=news_item.id,
            signal_type=SignalType.RISK_ALERT,
            score=90,
            risk_level="CRITICAL",
            reason="The original thesis is now under pressure.",
            evidence={"conflict": "GUIDANCE_CUT"},
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )

    assert repo.exists_active(asset.id, SignalType.RISK_ALERT.value, news_item.id) is False

    repo.create(
        SignalCreate(
            asset_id=asset.id,
            thesis_id=thesis.id,
            news_item_id=news_item.id,
            signal_type=SignalType.RISK_ALERT,
            score=91,
            risk_level="CRITICAL",
            reason="A fresh active duplicate should now be detected.",
            evidence={"conflict": "GUIDANCE_CUT"},
        )
    )

    assert repo.exists_active(asset.id, SignalType.RISK_ALERT.value, news_item.id) is True
