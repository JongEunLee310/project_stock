from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.alerts.service import AlertService
from app.domains.alerts.types import AlertStatus
from app.domains.assets.model import Asset
from app.domains.news.model import NewsItem
from app.domains.signals.model import Signal
from app.domains.signals.repository import SignalRepository
from app.domains.signals.schema import SignalCreate
from app.domains.signals.types import SignalType
from app.domains.users.model import User
from tests.conftest import TestingSessionLocal, api_data, api_meta, set_current_user


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
    reason: str = "Negative guidance conflicts with the current thesis.",
) -> Signal:
    return SignalRepository(db).create(
        SignalCreate(
            asset_id=asset_id,
            news_item_id=news_item_id,
            signal_type=signal_type,
            score=82,
            risk_level="HIGH",
            reason=reason,
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
    reason: str = "Negative guidance conflicts with the current thesis.",
) -> dict[str, Any]:
    db = TestingSessionLocal()
    try:
        asset = create_asset(db, symbol=f"AAPL{user_id}{len(title)}")
        news = create_news_item(db, asset.id, title=title)
        signal = create_signal(
            db,
            asset.id,
            news.id,
            signal_type=signal_type,
            reason=reason,
        )
        alert = AlertService(db).create_alert(user_id, signal)
        assert alert is not None
        return {
            "id": alert.id,
            "user_id": alert.user_id,
            "signal_id": alert.signal_id,
            "status": alert.status,
            "asset_id": asset.id,
            "symbol": asset.symbol,
            "alert_type": signal.signal_type,
            "message": signal.reason,
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
    data = cast(list[dict[str, Any]], api_data(response))
    assert [item["id"] for item in data] == [owner_alert["id"]]
    assert data[0]["user_id"] == 1
    assert api_meta(response) == {"page": 1, "size": 20, "total": 1}


def test_list_alerts_includes_signal_context(client: TestClient) -> None:
    alert = create_alert_for_user(
        1,
        signal_type=SignalType.THESIS_BROKEN,
        title="Thesis break",
        reason="Margin collapse invalidates the thesis.",
    )
    set_current_user(1)

    response = client.get("/api/v1/alerts")

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert data[0]["asset_id"] == alert["asset_id"]
    assert data[0]["symbol"] == alert["symbol"]
    assert data[0]["alert_type"] == SignalType.THESIS_BROKEN.value
    assert data[0]["message"] == "Margin collapse invalidates the thesis."


def test_list_alerts_keeps_context_for_mixed_assets(client: TestClient) -> None:
    first = create_alert_for_user(
        1,
        signal_type=SignalType.WATCH,
        title="First mixed asset",
        reason="Watch revenue acceleration.",
    )
    second = create_alert_for_user(
        1,
        signal_type=SignalType.SELL_REVIEW,
        title="Second mixed asset",
        reason="Review position after margin pressure.",
    )
    set_current_user(1)

    response = client.get("/api/v1/alerts")

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    context_by_id = {item["id"]: item for item in data}
    assert context_by_id[first["id"]]["asset_id"] == first["asset_id"]
    assert context_by_id[first["id"]]["symbol"] == first["symbol"]
    assert context_by_id[first["id"]]["alert_type"] == SignalType.WATCH.value
    assert context_by_id[first["id"]]["message"] == "Watch revenue acceleration."
    assert context_by_id[second["id"]]["asset_id"] == second["asset_id"]
    assert context_by_id[second["id"]]["symbol"] == second["symbol"]
    assert context_by_id[second["id"]]["alert_type"] == SignalType.SELL_REVIEW.value
    assert (
        context_by_id[second["id"]]["message"]
        == "Review position after margin pressure."
    )


def test_list_alerts_uses_page_and_size(client: TestClient) -> None:
    create_alert_for_user(1, title="First alert")
    second_alert = create_alert_for_user(1, title="Second alert")
    set_current_user(1)

    response = client.get("/api/v1/alerts", params={"page": 1, "size": 1})

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert [item["id"] for item in data] == [second_alert["id"]]
    assert api_meta(response) == {"page": 1, "size": 1, "total": 2}


def test_list_alerts_filters_by_status(client: TestClient) -> None:
    unread = create_alert_for_user(1, title="Unread alert")
    read = create_alert_for_user(1, title="Read alert")
    set_current_user(1)
    read_response = client.post(f"/api/v1/alerts/{read['id']}/read")
    assert read_response.status_code == 200

    response = client.get("/api/v1/alerts", params={"status": AlertStatus.UNREAD.value})

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert [item["id"] for item in data] == [unread["id"]]
    assert data[0]["status"] == AlertStatus.UNREAD.value
    assert api_meta(response) == {"page": 1, "size": 20, "total": 1}


def test_mark_alert_read_updates_status(client: TestClient) -> None:
    alert = create_alert_for_user(1, signal_type=SignalType.BUY_CANDIDATE)
    set_current_user(1)

    response = client.post(f"/api/v1/alerts/{alert['id']}/read")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["status"] == AlertStatus.READ.value
    assert data["asset_id"] == alert["asset_id"]
    assert data["symbol"] == alert["symbol"]
    assert data["alert_type"] == SignalType.BUY_CANDIDATE.value
    assert data["message"] == alert["message"]


def test_dismiss_alert_updates_status(client: TestClient) -> None:
    alert = create_alert_for_user(1, signal_type=SignalType.OVERHEATED)
    set_current_user(1)

    response = client.post(f"/api/v1/alerts/{alert['id']}/dismiss")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["status"] == AlertStatus.DISMISSED.value
    assert data["asset_id"] == alert["asset_id"]
    assert data["symbol"] == alert["symbol"]
    assert data["alert_type"] == SignalType.OVERHEATED.value
    assert data["message"] == alert["message"]


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
