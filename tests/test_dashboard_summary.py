from decimal import Decimal
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.alert_candidates.schema import AlertCandidateCreate
from app.domains.alert_candidates.service import AlertCandidateService
from app.domains.alert_candidates.types import (
    AlertCandidateStatus,
    AlertCandidateType,
    AlertImportance,
)
from app.domains.alerts.service import AlertService
from app.domains.assets.model import Asset
from app.domains.news.model import NewsItem
from app.domains.portfolios.model import Portfolio, Position
from app.domains.signals.repository import SignalRepository
from app.domains.signals.schema import SignalCreate
from app.domains.signals.types import SignalType
from tests.conftest import TestingSessionLocal, api_data, set_current_user


# --- 헬퍼 ---


def make_asset(db: Session, symbol: str = "AAPL") -> Asset:
    asset = Asset(symbol=symbol, name=f"{symbol} Inc.", market="NASDAQ")
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def make_news(db: Session, asset_id: int, title: str = "Alert news") -> NewsItem:
    item = NewsItem(
        asset_id=asset_id,
        title=title,
        url=f"https://example.com/{title.replace(' ', '-')}",
        source="Test News",
        summary="Test summary.",
        sentiment="NEGATIVE",
        impact_level="HIGH",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def make_alert_for_user(user_id: int, signal_type: SignalType, symbol: str) -> None:
    db = TestingSessionLocal()
    try:
        asset = make_asset(db, symbol=symbol)
        news = make_news(db, asset.id)
        signal = SignalRepository(db).create(
            SignalCreate(
                asset_id=asset.id,
                news_item_id=news.id,
                signal_type=signal_type,
                score=80,
                risk_level="HIGH",
                reason="Test signal.",
            )
        )
        AlertService(db).create_alert(user_id, signal)
    finally:
        db.close()


def make_alert_candidate(
    user_id: int,
    candidate_type: AlertCandidateType,
    importance: AlertImportance,
    status: AlertCandidateStatus = AlertCandidateStatus.UNREAD,
) -> None:
    db = TestingSessionLocal()
    try:
        candidate = AlertCandidateService(db).create_candidate(
            AlertCandidateCreate(
                user_id=user_id,
                candidate_type=candidate_type,
                importance=importance,
                title="Test candidate",
            )
        )
        if status != AlertCandidateStatus.UNREAD:
            from app.domains.alert_candidates.repository import AlertCandidateRepository

            AlertCandidateRepository(db).update_status(candidate, status.value)
    finally:
        db.close()


def make_portfolio(user_id: int, cash_balance: Decimal = Decimal("0")) -> int:
    db = TestingSessionLocal()
    try:
        portfolio = Portfolio(
            user_id=user_id,
            name="Test Portfolio",
            concentration_threshold=Decimal("0.4"),
            cash_balance=cash_balance,
        )
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)
        return portfolio.id
    finally:
        db.close()


def add_position(portfolio_id: int, quantity: Decimal, avg_buy_price: Decimal) -> None:
    db = TestingSessionLocal()
    try:
        asset = make_asset(db, symbol=f"POS{portfolio_id}{int(quantity)}")
        position = Position(
            portfolio_id=portfolio_id,
            asset_id=asset.id,
            quantity=quantity,
            avg_buy_price=avg_buy_price,
        )
        db.add(position)
        db.commit()
    finally:
        db.close()


# --- 테스트 ---


def test_dashboard_summary_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 401


def test_dashboard_summary_empty_data_returns_zeros_and_nulls(
    client: TestClient,
) -> None:
    set_current_user(1)
    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["risk_alert_count"] == 0
    assert data["important_news_count"] == 0
    assert data["review_signal_count"] == 0
    assert data["cash_weight"] is None
    assert data["risk_alert_delta"] is None
    assert data["important_news_delta"] is None
    assert data["review_signal_delta"] is None
    assert data["cash_weight_delta"] is None


def test_dashboard_summary_counts_risk_alerts_by_signal_type(
    client: TestClient,
) -> None:
    make_alert_for_user(user_id=1, signal_type=SignalType.RISK_ALERT, symbol="RA1")
    make_alert_for_user(user_id=1, signal_type=SignalType.THESIS_BROKEN, symbol="TB1")
    # WATCH 타입은 집계되지 않아야 한다
    make_alert_for_user(user_id=1, signal_type=SignalType.WATCH, symbol="WC1")
    set_current_user(1)

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["risk_alert_count"] == 2


def test_dashboard_summary_counts_important_news(client: TestClient) -> None:
    # 집계 대상: NEWS_SURGE + HIGH + UNREAD
    make_alert_candidate(1, AlertCandidateType.NEWS_SURGE, AlertImportance.HIGH)
    # 집계 대상: DISCLOSURE + HIGH + UNREAD
    make_alert_candidate(1, AlertCandidateType.DISCLOSURE, AlertImportance.HIGH)
    # 제외: HIGH이지만 PRICE_MOVEMENT 타입
    make_alert_candidate(1, AlertCandidateType.PRICE_MOVEMENT, AlertImportance.HIGH)
    # 제외: NEWS_SURGE이지만 MEDIUM importance
    make_alert_candidate(1, AlertCandidateType.NEWS_SURGE, AlertImportance.MEDIUM)
    set_current_user(1)

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["important_news_count"] == 2


def test_dashboard_summary_counts_review_signals(client: TestClient) -> None:
    make_alert_for_user(user_id=1, signal_type=SignalType.SELL_REVIEW, symbol="SR1")
    make_alert_for_user(user_id=1, signal_type=SignalType.OVERHEATED, symbol="OH1")
    # RISK_ALERT는 review_signal에 포함되지 않아야 한다
    make_alert_for_user(user_id=1, signal_type=SignalType.RISK_ALERT, symbol="RA2")
    set_current_user(1)

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["review_signal_count"] == 2


def test_dashboard_summary_cash_weight_with_portfolio(client: TestClient) -> None:
    # cash_balance=5000, position cost=5000 => cash_weight=0.5
    portfolio_id = make_portfolio(user_id=1, cash_balance=Decimal("5000"))
    add_position(portfolio_id, quantity=Decimal("10"), avg_buy_price=Decimal("500"))
    set_current_user(1)

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    cash_weight = data["cash_weight"]
    assert cash_weight is not None
    weight_value = Decimal(cash_weight)
    assert weight_value == Decimal("0.5000")


def test_dashboard_summary_cash_weight_none_without_portfolio(
    client: TestClient,
) -> None:
    set_current_user(99)

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["cash_weight"] is None


def test_dashboard_summary_isolates_by_user(client: TestClient) -> None:
    """다른 사용자의 데이터는 집계되지 않아야 한다."""
    make_alert_for_user(user_id=2, signal_type=SignalType.RISK_ALERT, symbol="OTH1")
    make_alert_candidate(2, AlertCandidateType.NEWS_SURGE, AlertImportance.HIGH)
    set_current_user(1)

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["risk_alert_count"] == 0
    assert data["important_news_count"] == 0
