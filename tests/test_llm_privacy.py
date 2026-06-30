from decimal import Decimal
from typing import ClassVar

import pytest

from app.adapters.llm.exceptions import CloudBoundaryViolationError
from app.adapters.llm.privacy import (
    CloudSafePayload,
    PortfolioConcentrationSnapshot,
    PrivacyGate,
    to_concentration_snapshot,
)
from app.adapters.llm.types import SensitivityLevel
from app.domains.portfolios.model import Portfolio, Position


class RawPayload(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.RAW

    value: str


class SemiPayload(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.SEMI

    value: str


class PublicPayload(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.PUBLIC

    value: str


def make_portfolio() -> Portfolio:
    return Portfolio(
        user_id=7,
        name="Retirement",
        concentration_threshold=Decimal("0.40"),
        cash_balance=Decimal("1000.00"),
    )


def make_position(
    asset_id: int,
    quantity: Decimal,
    avg_buy_price: Decimal,
) -> Position:
    return Position(
        portfolio_id=1,
        asset_id=asset_id,
        quantity=quantity,
        avg_buy_price=avg_buy_price,
    )


def test_guard_returns_aggregated_cloud_safe_projection() -> None:
    payload = PortfolioConcentrationSnapshot(
        position_count_band="1-5",
        largest_position_band="25-40%",
        cash_band="0-25%",
        is_concentrated=False,
    )

    assert PrivacyGate().guard(payload) is payload


def test_guard_returns_public_cloud_safe_projection() -> None:
    payload = PublicPayload(value="market holiday")

    assert PrivacyGate().guard(payload) is payload


def test_guard_rejects_original_portfolio_entity() -> None:
    with pytest.raises(CloudBoundaryViolationError):
        PrivacyGate().guard(make_portfolio())


def test_guard_rejects_free_form_dict() -> None:
    with pytest.raises(CloudBoundaryViolationError):
        PrivacyGate().guard({"position_count_band": "1-5"})


@pytest.mark.parametrize(
    "payload",
    [
        RawPayload(value="raw"),
        SemiPayload(value="semi"),
    ],
)
def test_guard_rejects_cloud_safe_payload_with_blocked_sensitivity(
    payload: CloudSafePayload,
) -> None:
    with pytest.raises(CloudBoundaryViolationError):
        PrivacyGate().guard(payload)


def test_to_concentration_snapshot_returns_cloud_safe_bands_only() -> None:
    portfolio = make_portfolio()
    positions = [
        make_position(
            asset_id=101,
            quantity=Decimal("10"),
            avg_buy_price=Decimal("100"),
        ),
        make_position(
            asset_id=102,
            quantity=Decimal("5"),
            avg_buy_price=Decimal("400"),
        ),
    ]

    snapshot = to_concentration_snapshot(portfolio, positions)
    payload = snapshot.as_payload()

    assert payload == {
        "position_count_band": "1-5",
        "largest_position_band": "40%+",
        "cash_band": "25-40%",
        "is_concentrated": True,
    }
    assert set(payload) == {
        "position_count_band",
        "largest_position_band",
        "cash_band",
        "is_concentrated",
    }
    assert isinstance(payload["position_count_band"], str)
    assert isinstance(payload["largest_position_band"], str)
    assert isinstance(payload["cash_band"], str)
    assert isinstance(payload["is_concentrated"], bool)
    assert "user_id" not in payload
    assert "cash_balance" not in payload
    assert "quantity" not in payload
    assert "asset_id" not in payload
    assert PrivacyGate().guard(snapshot) is snapshot
