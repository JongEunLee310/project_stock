"""
이슈 #100 (symbol 필터) · #101 (detail 펀더멘털 nullable 필드) 전용 테스트.
"""
from typing import Any, cast

from fastapi.testclient import TestClient

from tests.conftest import api_data, api_meta

FUNDAMENTAL_FIELDS = (
    "per",
    "peg",
    "fifty_two_week_low",
    "fifty_two_week_high",
    "target_price",
    "target_upside_percent",
)


def create_asset(
    client: TestClient,
    symbol: str = "AAPL",
    market: str = "NASDAQ",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/assets",
        json={
            "symbol": symbol,
            "name": f"{symbol} Inc.",
            "market": market,
            "sector": "Technology",
        },
    )
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


# ── #100 symbol 필터 ────────────────────────────────────────────────────────


def test_list_assets_symbol_filter_hit(client: TestClient) -> None:
    """symbol 파라미터가 주어지면 해당 종목만 반환한다."""
    create_asset(client, symbol="AAPL")
    create_asset(client, symbol="TSLA")

    response = client.get("/api/v1/assets", params={"symbol": "AAPL"})

    assert response.status_code == 200
    items = cast(list[dict[str, Any]], api_data(response))
    assert len(items) == 1
    assert items[0]["symbol"] == "AAPL"
    assert api_meta(response) == {"page": 1, "size": 20, "total": 1}


def test_list_assets_symbol_filter_miss(client: TestClient) -> None:
    """존재하지 않는 symbol로 필터하면 빈 목록과 total 0을 반환한다."""
    create_asset(client, symbol="AAPL")

    response = client.get("/api/v1/assets", params={"symbol": "ZZZZ"})

    assert response.status_code == 200
    items = cast(list[dict[str, Any]], api_data(response))
    assert items == []
    assert api_meta(response) == {"page": 1, "size": 20, "total": 0}


def test_list_assets_no_symbol_filter_returns_all(client: TestClient) -> None:
    """symbol 파라미터 없이 요청하면 기존 동작(전체 목록)을 유지한다."""
    create_asset(client, symbol="AAPL")
    create_asset(client, symbol="TSLA")

    response = client.get("/api/v1/assets")

    assert response.status_code == 200
    items = cast(list[dict[str, Any]], api_data(response))
    assert len(items) == 2
    assert api_meta(response)["total"] == 2


def test_list_assets_symbol_filter_combined_with_is_active(client: TestClient) -> None:
    """symbol 필터와 is_active 필터를 동시에 적용할 수 있다."""
    create_asset(client, symbol="AAPL")

    response = client.get(
        "/api/v1/assets", params={"symbol": "AAPL", "is_active": True}
    )

    assert response.status_code == 200
    items = cast(list[dict[str, Any]], api_data(response))
    assert len(items) == 1
    assert items[0]["symbol"] == "AAPL"


# ── #101 detail 펀더멘털 nullable 필드 ─────────────────────────────────────


def test_asset_detail_contains_fundamental_fields(client: TestClient) -> None:
    """AssetDetailResponse에 신규 펀더멘털 필드 6개가 모두 존재한다."""
    asset = create_asset(client, symbol="AAPL")

    response = client.get(f"/api/v1/assets/{asset['id']}/detail")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    for field in FUNDAMENTAL_FIELDS:
        assert field in data, f"필드 누락: {field}"


def test_asset_detail_aapl_fundamental_values_from_mock(client: TestClient) -> None:
    """AAPL mock 데이터에는 펀더멘털 값이 문자열 Decimal로 채워진다."""
    asset = create_asset(client, symbol="AAPL")

    response = client.get(f"/api/v1/assets/{asset['id']}/detail")

    data = cast(dict[str, Any], api_data(response))
    assert data["per"] == "31.20"
    assert data["peg"] == "2.45"
    assert data["fifty_two_week_low"] == "164.08"
    assert data["fifty_two_week_high"] == "237.49"
    assert data["target_price"] == "220.00"
    assert data["target_upside_percent"] == "12.45"


def test_asset_detail_unknown_symbol_fundamental_fields_are_none(
    client: TestClient,
) -> None:
    """mock 데이터가 없는 symbol(fallback)은 펀더멘털 필드를 None으로 반환한다."""
    asset = create_asset(client, symbol="ZZZZ")

    response = client.get(f"/api/v1/assets/{asset['id']}/detail")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    for field in FUNDAMENTAL_FIELDS:
        assert data[field] is None, f"{field} should be None for fallback symbol"
