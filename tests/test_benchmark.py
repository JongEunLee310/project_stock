from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.assets.model import Asset
from app.domains.benchmark.schema import BenchmarkRange, BenchmarkSeriesKind
from app.domains.benchmark.sector_map import resolve_sector_etf
from app.domains.prices.model import StockPriceBar
from app.domains.prices.repository import PriceBarRepository
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user


def create_asset(*, sector: str | None = "Technology") -> int:
    with TestingSessionLocal() as db:
        asset = Asset(
            symbol="BMK",
            name="Benchmark",
            market="NASDAQ",
            sector=sector,
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset.id


def add_daily_closes(
    db: Session,
    symbol: str,
    market: str,
    closes: dict[date, Decimal],
) -> None:
    db.add_all(
        [
            StockPriceBar(
                symbol=symbol,
                market=market,
                interval="1d",
                timestamp=datetime.combine(point_date, time.min, tzinfo=UTC),
                open_price=close,
                high_price=close,
                low_price=close,
                close_price=close,
                adjusted_close_price=close,
                volume=1000,
                currency="USD",
                source="fixture",
            )
            for point_date, close in closes.items()
        ]
    )
    db.commit()


def test_get_benchmark_comparison_derives_aligned_cumulative_returns(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset()
    outside_range = date(2026, 4, 8)
    first_date = date(2026, 4, 9)
    second_date = date(2026, 4, 10)
    excluded_date = date(2026, 6, 1)
    reference_date = date(2026, 7, 10)
    with TestingSessionLocal() as db:
        add_daily_closes(
            db,
            "BMK",
            "NASDAQ",
            {
                outside_range: Decimal("90"),
                first_date: Decimal("100"),
                second_date: Decimal("110"),
                excluded_date: Decimal("999"),
                reference_date: Decimal("120"),
            },
        )
        add_daily_closes(
            db,
            "QQQ",
            "NASDAQ",
            {
                outside_range: Decimal("180"),
                first_date: Decimal("200"),
                second_date: Decimal("210"),
                excluded_date: Decimal("230"),
                reference_date: Decimal("220"),
            },
        )
        add_daily_closes(
            db,
            "XLK",
            "NYSE",
            {
                outside_range: Decimal("45"),
                first_date: Decimal("50"),
                second_date: Decimal("55"),
                reference_date: Decimal("60"),
            },
        )

    response = client.get(
        f"/api/v1/assets/{asset_id}/benchmark-comparison",
        params={"range": "3M"},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["asset_id"] == asset_id
    assert data["range"] == "3M"
    assert [series["kind"] for series in data["series"]] == [
        kind.value for kind in BenchmarkSeriesKind
    ]
    assert [series["label"] for series in data["series"]] == [
        "BMK",
        "NASDAQ 100",
        "XLK",
    ]
    expected_dates = ["2026-04-09", "2026-04-10", "2026-07-10"]
    assert [
        [point["date"] for point in series["points"]]
        for series in data["series"]
    ] == [expected_dates, expected_dates, expected_dates]
    # BMK: 110 / 100 - 1 = 10%, 120 / 100 - 1 = 20%.
    # QQQ: 210 / 200 - 1 = 5%, 220 / 200 - 1 = 10%.
    # XLK: 55 / 50 - 1 = 10%, 60 / 50 - 1 = 20%.
    assert [
        [Decimal(point["return_percent"]) for point in series["points"]]
        for series in data["series"]
    ] == [
        [Decimal("0.00"), Decimal("10.00"), Decimal("20.00")],
        [Decimal("0.00"), Decimal("5.00"), Decimal("10.00")],
        [Decimal("0.00"), Decimal("10.00"), Decimal("20.00")],
    ]


def test_get_benchmark_comparison_excludes_bars_before_bounded_query_start(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_current_user(1)
    asset_id = create_asset()
    old_date = date(2020, 1, 2)
    first_date = date(2026, 4, 9)
    reference_date = date(2026, 7, 10)
    with TestingSessionLocal() as db:
        for symbol, market in [
            ("BMK", "NASDAQ"),
            ("QQQ", "NASDAQ"),
            ("XLK", "NYSE"),
        ]:
            add_daily_closes(
                db,
                symbol,
                market,
                {
                    old_date: Decimal("1"),
                    first_date: Decimal("100"),
                    reference_date: Decimal("120"),
                },
            )

    query_starts: list[date | None] = []
    original_get_daily_closes = PriceBarRepository.get_daily_closes

    def record_query_start(
        repository: PriceBarRepository,
        symbol: str,
        market: str,
        start: date | None,
    ) -> list[tuple[date, Decimal]]:
        query_starts.append(start)
        return original_get_daily_closes(repository, symbol, market, start)

    monkeypatch.setattr(PriceBarRepository, "get_daily_closes", record_query_start)

    response = client.get(
        f"/api/v1/assets/{asset_id}/benchmark-comparison",
        params={"range": "3M"},
    )

    assert response.status_code == 200
    assert query_starts == [date(2026, 3, 26)] * 3
    data = cast(dict[str, Any], api_data(response))
    assert [
        [point["date"] for point in series["points"]]
        for series in data["series"]
    ] == [["2026-04-09", "2026-07-10"]] * 3
    assert [
        [Decimal(point["return_percent"]) for point in series["points"]]
        for series in data["series"]
    ] == [[Decimal("0.00"), Decimal("20.00")]] * 3


@pytest.mark.parametrize(
    ("range_", "expected_first_date"),
    [
        (BenchmarkRange.ONE_MONTH, date(2026, 6, 9)),
        (BenchmarkRange.THREE_MONTHS, date(2026, 4, 9)),
        (BenchmarkRange.SIX_MONTHS, date(2026, 1, 8)),
        (BenchmarkRange.ONE_YEAR, date(2025, 7, 9)),
    ],
)
def test_get_benchmark_comparison_filters_from_reference_date(
    client: TestClient,
    range_: BenchmarkRange,
    expected_first_date: date,
) -> None:
    set_current_user(1)
    asset_id = create_asset()
    dates = [
        date(2025, 7, 8),
        date(2025, 7, 9),
        date(2026, 1, 8),
        date(2026, 4, 9),
        date(2026, 6, 9),
        date(2026, 7, 10),
    ]
    with TestingSessionLocal() as db:
        for symbol, market in [
            ("BMK", "NASDAQ"),
            ("QQQ", "NASDAQ"),
            ("XLK", "NYSE"),
        ]:
            add_daily_closes(
                db,
                symbol,
                market,
                {
                    point_date: Decimal(index + 1)
                    for index, point_date in enumerate(dates)
                },
            )

    response = client.get(
        f"/api/v1/assets/{asset_id}/benchmark-comparison",
        params={"range": range_.value},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["series"][0]["points"][0]["date"] == expected_first_date.isoformat()


def test_get_benchmark_comparison_returns_empty_points_when_a_series_is_missing(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset()
    with TestingSessionLocal() as db:
        add_daily_closes(
            db,
            "BMK",
            "NASDAQ",
            {date(2026, 7, 10): Decimal("100")},
        )

    response = client.get(f"/api/v1/assets/{asset_id}/benchmark-comparison")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert [series["points"] for series in data["series"]] == [[], [], []]
    assert [series["label"] for series in data["series"]] == [
        "BMK",
        "NASDAQ 100",
        "XLK",
    ]


@pytest.mark.parametrize("sector", [None, "Unknown Sector"])
def test_get_benchmark_comparison_uses_spy_for_unmapped_sector(
    client: TestClient,
    sector: str | None,
) -> None:
    set_current_user(1)
    asset_id = create_asset(sector=sector)
    with TestingSessionLocal() as db:
        for symbol, market in [
            ("BMK", "NASDAQ"),
            ("QQQ", "NASDAQ"),
            ("SPY", "NYSE"),
        ]:
            add_daily_closes(
                db,
                symbol,
                market,
                {date(2026, 7, 10): Decimal("100")},
            )

    response = client.get(f"/api/v1/assets/{asset_id}/benchmark-comparison")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["series"][2]["label"] == "S&P 500"
    assert Decimal(data["series"][2]["points"][0]["return_percent"]) == Decimal(
        "0.00"
    )


def test_resolve_sector_etf_uses_shared_mapping_and_fallback() -> None:
    assert resolve_sector_etf("Technology") == ("XLK", "NYSE", "XLK")
    assert resolve_sector_etf(None) == ("SPY", "NYSE", "S&P 500")


def test_get_benchmark_comparison_defaults_to_three_months(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset()

    response = client.get(f"/api/v1/assets/{asset_id}/benchmark-comparison")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["range"] == "3M"


def test_get_benchmark_comparison_rejects_unsupported_range(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset()

    response = client.get(
        f"/api/v1/assets/{asset_id}/benchmark-comparison",
        params={"range": "1D"},
    )

    assert response.status_code == 422


def test_get_benchmark_comparison_returns_404_for_missing_asset(
    client: TestClient,
) -> None:
    set_current_user(1)
    existing_asset_id = create_asset()

    response = client.get(
        f"/api/v1/assets/{existing_asset_id + 1}/benchmark-comparison"
    )

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }


def test_get_benchmark_comparison_requires_authentication(
    client: TestClient,
) -> None:
    asset_id = create_asset()

    response = client.get(f"/api/v1/assets/{asset_id}/benchmark-comparison")

    assert response.status_code == 401
