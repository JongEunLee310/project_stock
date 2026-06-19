from collections.abc import Generator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.deps import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.domains.alerts.service import AlertService
from app.domains.alerts.types import AlertStatus
from app.domains.assets.model import Asset
from app.domains.news.model import NewsItem
from app.domains.signals.model import Signal
from app.domains.signals.repository import SignalRepository
from app.domains.signals.schema import SignalCreate
from app.domains.signals.types import SignalType
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


def create_asset(db: Session, symbol: str = "AAPL") -> Asset:
    asset = Asset(symbol=symbol, name=f"{symbol} Inc.", market="NASDAQ")
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def create_news_item(db: Session, asset_id: int, title: str = "Guidance cut") -> NewsItem:
    item = NewsItem(
        asset_id=asset_id,
        title=title,
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        source="Example News",
        summary="Management lowered guidance.",
        sentiment="NEGATIVE",
        impact_level="HIGH",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def create_signal(
    db: Session,
    asset_id: int,
    news_item_id: int | None,
    signal_type: SignalType = SignalType.RISK_ALERT,
) -> Signal:
    return SignalRepository(db).create(
        SignalCreate(
            asset_id=asset_id,
            news_item_id=news_item_id,
            signal_type=signal_type,
            score=82,
            risk_level="HIGH",
            reason="Negative guidance conflicts with the current thesis.",
            evidence={"news_item_id": news_item_id},
        )
    )


def create_user(db: Session, email: str = "owner@example.com") -> User:
    user = User(email=email, hashed_password="test-hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_alert_for_user(
    user_id: int,
    signal_type: SignalType = SignalType.RISK_ALERT,
    title: str = "Guidance cut",
) -> dict[str, Any]:
    db = TestingSessionLocal()
    try:
        asset = create_asset(db, symbol=f"AAPL{user_id}{len(title)}")
        news = create_news_item(db, asset.id, title=title)
        signal = create_signal(db, asset.id, news.id, signal_type=signal_type)
        alert = AlertService(db).create_alert(user_id, signal)
        assert alert is not None
        return {
            "id": alert.id,
            "user_id": alert.user_id,
            "signal_id": alert.signal_id,
            "status": alert.status,
        }
    finally:
        db.close()


def test_alert_service_create_alert_deduplicates_same_event(db: Session) -> None:
    user = create_user(db)
    asset = create_asset(db)
    news = create_news_item(db, asset.id)
    signal = create_signal(db, asset.id, news.id)
    service = AlertService(db)

    first = service.create_alert(user.id, signal)
    duplicate = service.create_alert(user.id, signal)

    assert first is not None
    assert first.status == AlertStatus.UNREAD.value
    assert duplicate is None


def test_list_alerts_returns_only_current_users_alerts(client: TestClient) -> None:
    owner_alert = create_alert_for_user(1, title="Owner alert")
    create_alert_for_user(2, title="Other alert")
    set_current_user(1)

    response = client.get("/api/v1/alerts")

    assert response.status_code == 200
    data = response.json()
    assert [item["id"] for item in data] == [owner_alert["id"]]
    assert data[0]["user_id"] == 1


def test_list_alerts_filters_by_status(client: TestClient) -> None:
    unread = create_alert_for_user(1, title="Unread alert")
    read = create_alert_for_user(1, title="Read alert")
    set_current_user(1)
    read_response = client.post(f"/api/v1/alerts/{read['id']}/read")
    assert read_response.status_code == 200

    response = client.get("/api/v1/alerts", params={"status": AlertStatus.UNREAD.value})

    assert response.status_code == 200
    data = response.json()
    assert [item["id"] for item in data] == [unread["id"]]
    assert data[0]["status"] == AlertStatus.UNREAD.value


def test_mark_alert_read_updates_status(client: TestClient) -> None:
    alert = create_alert_for_user(1)
    set_current_user(1)

    response = client.post(f"/api/v1/alerts/{alert['id']}/read")

    assert response.status_code == 200
    data = cast(dict[str, Any], response.json())
    assert data["status"] == AlertStatus.READ.value


def test_dismiss_alert_updates_status(client: TestClient) -> None:
    alert = create_alert_for_user(1)
    set_current_user(1)

    response = client.post(f"/api/v1/alerts/{alert['id']}/dismiss")

    assert response.status_code == 200
    data = cast(dict[str, Any], response.json())
    assert data["status"] == AlertStatus.DISMISSED.value


def test_mark_alert_read_returns_404_for_other_user_or_missing_alert(
    client: TestClient,
) -> None:
    alert = create_alert_for_user(1)
    set_current_user(2, "other@example.com")

    other_user_response = client.post(f"/api/v1/alerts/{alert['id']}/read")
    missing_response = client.post("/api/v1/alerts/999/read")

    assert other_user_response.status_code == 404
    assert missing_response.status_code == 404


def test_create_alert_deduplicates_same_signal_event(db: Session) -> None:
    user = create_user(db)
    asset = create_asset(db)
    news = create_news_item(db, asset.id)
    first_signal = create_signal(db, asset.id, news.id)
    second_signal = create_signal(db, asset.id, news.id)
    service = AlertService(db)

    first = service.create_alert(user.id, first_signal)
    second = service.create_alert(user.id, second_signal)

    assert first is not None
    assert second is None


def test_create_alert_does_not_collapse_signals_without_news_item(
    db: Session,
) -> None:
    user = create_user(db)
    asset = create_asset(db)
    first_signal = create_signal(db, asset.id, None)
    second_signal = create_signal(db, asset.id, None)
    service = AlertService(db)

    first = service.create_alert(user.id, first_signal)
    second = service.create_alert(user.id, second_signal)

    assert first is not None
    assert first.dedup_key == f"{SignalType.RISK_ALERT.value}:signal:{first_signal.id}"
    assert second is not None
    assert second.dedup_key == f"{SignalType.RISK_ALERT.value}:signal:{second_signal.id}"
