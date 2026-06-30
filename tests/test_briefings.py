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
    DashboardBriefingSnapshot,
    PortfolioBriefingSnapshot,
    PrivacyGate,
    to_briefing_snapshot,
    to_dashboard_snapshot,
)
from app.adapters.llm.schema import BriefingResult
from app.adapters.llm.types import LLMTaskType, SensitivityLevel
from app.core.config import settings
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.dashboard.briefing_service import DashboardBriefingService
from app.domains.dashboard.schema import DashboardSummaryResponse
from app.domains.portfolios.briefing_service import PortfolioBriefingService
from app.domains.portfolios.model import Portfolio
from app.domains.portfolios.schema import (
    PortfolioCreate,
    PortfolioSummaryResponse,
    PositionCreate,
    PositionWeight,
    RiskExposure,
    SectorWeight,
)
from app.domains.portfolios.service import PortfolioService
from tests.conftest import api_data, set_current_user


class RecordingGateway(LLMGateway):
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
            "headline": "Portfolio needs review",
            "body": "Concentration and cash weight should be checked.",
            "risk_headline": "Before buying",
            "risk_checks": ["Review concentration"],
        }


def make_summary() -> PortfolioSummaryResponse:
    return PortfolioSummaryResponse(
        portfolio_id=1,
        concentration_threshold=Decimal("0.40"),
        total_cost_value=Decimal("12000"),
        total_value=Decimal("15000"),
        cash_balance=Decimal("3000"),
        cash_weight=Decimal("0.20"),
        has_sector_concentration=True,
        positions=[
            PositionWeight(
                asset_id=101,
                quantity=Decimal("10"),
                avg_buy_price=Decimal("100"),
                cost_value=Decimal("1000"),
                market_value=Decimal("9000"),
                cost_weight=Decimal("0.25"),
                weight=Decimal("0.60"),
                exceeds_threshold=True,
            )
        ],
        sector_weights=[
            SectorWeight(
                sector="Technology",
                market_value=Decimal("9000"),
                weight=Decimal("0.60"),
                exceeds_threshold=True,
            )
        ],
        day_change_value=Decimal("120"),
        day_change_percent=Decimal("1.25"),
        risk_exposures=[
            RiskExposure(
                code="SINGLE_NAME_CONCENTRATION:AAPL",
                label="AAPL single-name concentration",
                level="HIGH",
                description="AAPL is above threshold.",
            )
        ],
    )


def assert_no_monetary_fields(payload: dict[str, Any]) -> None:
    serialized = str(payload)
    for forbidden in [
        "quantity",
        "avg_buy_price",
        "market_value",
        "cost_value",
        "cash_balance",
        "total_value",
        "total_cost_value",
        "day_change_value",
    ]:
        assert forbidden not in serialized


def test_portfolio_briefing_snapshot_is_cloudsafe_without_monetary_fields() -> None:
    snapshot = to_briefing_snapshot(
        make_summary(),
        symbol_by_asset_id={101: "AAPL"},
        sector_by_asset_id={101: "Technology"},
        daily_change_by_asset_id={101: Decimal("1.50")},
    )

    payload = snapshot.as_payload()

    assert snapshot.sensitivity == SensitivityLevel.AGGREGATED
    assert PrivacyGate().guard(snapshot) is snapshot
    assert payload["positions"][0] == {
        "symbol": "AAPL",
        "sector": "Technology",
        "weight": "0.60",
        "daily_change_percent": "1.50",
    }
    assert payload["sector_weights"][0] == {
        "sector": "Technology",
        "weight": "0.60",
    }
    assert payload["cash_weight"] == "0.20"
    assert_no_monetary_fields(payload)


def test_dashboard_briefing_snapshot_omits_highlights_when_data_is_unavailable() -> None:
    snapshot = to_dashboard_snapshot(
        DashboardSummaryResponse(
            risk_alert_count=2,
            important_news_count=3,
            review_signal_count=1,
            cash_weight="0.2500",
        ),
        highlights=[],
    )

    payload = snapshot.as_payload()

    assert snapshot.sensitivity == SensitivityLevel.AGGREGATED
    assert PrivacyGate().guard(snapshot) is snapshot
    assert payload == {
        "risk_alert_count": 2,
        "important_news_count": 3,
        "review_signal_count": 1,
        "cash_weight": "0.2500",
        "watchlist_highlights": [],
    }
    assert_no_monetary_fields(payload)


def test_original_portfolio_entity_is_rejected_at_cloud_boundary() -> None:
    portfolio = Portfolio(
        user_id=1,
        name="Private",
        concentration_threshold=Decimal("0.4"),
        cash_balance=Decimal("1000"),
    )

    with pytest.raises(CloudBoundaryViolationError):
        PrivacyGate().guard(portfolio)


def create_owned_portfolio(db: Session) -> int:
    asset = AssetRepository(db).create(
        symbol="AAPL",
        name="Apple Inc.",
        market="NASDAQ",
        sector="Technology",
        industry=None,
        description=None,
    )
    service = PortfolioService(db)
    portfolio = service.create_portfolio(
        user_id=1,
        data=PortfolioCreate(
            name="Core",
            concentration_threshold=Decimal("0.40"),
            cash_balance=Decimal("1000"),
        ),
    )
    service.add_position(
        portfolio.id,
        user_id=1,
        data=PositionCreate(
            asset_id=asset.id,
            quantity=Decimal("10"),
            avg_buy_price=Decimal("100"),
        ),
    )
    return portfolio.id


def test_portfolio_briefing_service_maps_gateway_result(db: Session) -> None:
    portfolio_id = create_owned_portfolio(db)
    gateway = RecordingGateway()

    result = PortfolioBriefingService(db, gateway).generate(portfolio_id, user_id=1)

    assert result.headline == "Portfolio needs review"
    assert result.risk_checks == ["Review concentration"]
    assert len(gateway.calls) == 1
    task_type, payload, schema, _prompt = gateway.calls[0]
    assert task_type == LLMTaskType.PORTFOLIO_BRIEFING
    assert isinstance(payload, PortfolioBriefingSnapshot)
    assert schema is BriefingResult


def test_portfolio_briefing_service_raises_404_for_missing_portfolio(
    db: Session,
) -> None:
    with pytest.raises(AppException) as exc_info:
        PortfolioBriefingService(db, RecordingGateway()).generate(999, user_id=1)

    assert exc_info.value.status_code == 404


def test_dashboard_briefing_service_maps_gateway_result_without_highlights(
    db: Session,
) -> None:
    gateway = RecordingGateway()

    result = DashboardBriefingService(db, gateway).generate(user_id=1)

    assert result.body == "Concentration and cash weight should be checked."
    task_type, payload, schema, _prompt = gateway.calls[0]
    assert task_type == LLMTaskType.DASHBOARD_BRIEFING
    assert isinstance(payload, DashboardBriefingSnapshot)
    assert payload.watchlist_highlights == []
    assert schema is BriefingResult


def test_portfolio_briefing_endpoint_returns_enveloped_mock_response(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    set_current_user(1)
    portfolio_response = client.post(
        "/api/v1/portfolios",
        json={"name": "Core", "cash_balance": "1000"},
    )
    portfolio = cast(dict[str, Any], api_data(portfolio_response))
    asset_response = client.post(
        "/api/v1/assets",
        json={
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "market": "NASDAQ",
            "sector": "Technology",
        },
    )
    asset = cast(dict[str, Any], api_data(asset_response))
    position_response = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/positions",
        json={
            "asset_id": asset["id"],
            "quantity": "10",
            "avg_buy_price": "100",
        },
    )
    assert position_response.status_code == 201

    response = client.get(f"/api/v1/portfolios/{portfolio['id']}/briefing")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["headline"] == "Mock briefing headline."
    assert data["body"] == "Mock briefing body."
    assert data["risk_headline"] == "Mock risk checks"
    assert data["risk_checks"] == ["Mock risk check"]
    assert isinstance(data["generated_at"], str)


def test_portfolio_briefing_endpoint_blocks_other_users(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    set_current_user(1)
    portfolio_response = client.post("/api/v1/portfolios", json={"name": "Core"})
    portfolio = cast(dict[str, Any], api_data(portfolio_response))
    set_current_user(2, "other@example.com")

    response = client.get(f"/api/v1/portfolios/{portfolio['id']}/briefing")

    assert response.status_code == 403


def test_dashboard_briefing_endpoint_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/briefing")

    assert response.status_code == 401


def test_dashboard_briefing_endpoint_returns_enveloped_mock_response(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    set_current_user(1)

    response = client.get("/api/v1/dashboard/briefing")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["headline"] == "Mock briefing headline."
    assert data["body"] == "Mock briefing body."
    assert data["risk_checks"] == ["Mock risk check"]
    assert isinstance(data["generated_at"], str)
