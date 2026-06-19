from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.deps import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.domains.assets.model import Asset
from app.domains.news.model import NewsItem
from app.domains.signals.repository import SignalRepository
from app.domains.signals.schema import SignalCreate
from app.domains.signals.types import SignalType
from app.domains.theses.model import InvestmentThesis
from app.domains.users.model import User
from app.main import app


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def set_current_user(user_id: int, email: str = "owner@example.com") -> None:
    def override_get_current_user() -> User:
        return User(id=user_id, email=email, hashed_password="test-hash")

    app.dependency_overrides[get_current_user] = override_get_current_user


def create_asset(client: TestClient, symbol: str = "AAPL") -> dict[str, Any]:
    response = client.post(
        "/api/v1/assets",
        json={"symbol": symbol, "name": f"{symbol} Inc.", "market": "NASDAQ"},
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


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
    return cast(dict[str, Any], response.json())


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
    assert response.json() == [active]


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
    assert response.json() == [expired, active]


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
    assert response.json() == signal


def test_get_signal_returns_404_when_missing(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/signals/999")

    assert response.status_code == 404


def test_list_signals_requires_asset_id(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/signals")

    assert response.status_code == 422


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
