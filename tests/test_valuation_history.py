from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domains.valuation.history import (
    build_per_series,
    build_ttm_eps_series,
    median_and_percentile,
)


@dataclass(frozen=True)
class ReportFixture:
    period_end: date
    eps: Decimal | None


def test_build_ttm_eps_series_sorts_reports_and_uses_sliding_windows() -> None:
    reports = [
        ReportFixture(date(2025, 6, 30), Decimal("2")),
        ReportFixture(date(2024, 12, 31), Decimal("1")),
        ReportFixture(date(2025, 9, 30), Decimal("4")),
        ReportFixture(date(2025, 3, 31), Decimal("3")),
        ReportFixture(date(2025, 12, 31), Decimal("5")),
    ]

    assert build_ttm_eps_series(reports) == [
        (date(2025, 9, 30), Decimal("10")),
        (date(2025, 12, 31), Decimal("14")),
    ]


def test_build_ttm_eps_series_skips_each_window_containing_null_eps() -> None:
    reports = [
        ReportFixture(date(2024, 12, 31), Decimal("1")),
        ReportFixture(date(2025, 3, 31), None),
        ReportFixture(date(2025, 6, 30), Decimal("2")),
        ReportFixture(date(2025, 9, 30), Decimal("3")),
        ReportFixture(date(2025, 12, 31), Decimal("4")),
        ReportFixture(date(2026, 3, 31), Decimal("5")),
    ]

    assert build_ttm_eps_series(reports) == [
        (date(2026, 3, 31), Decimal("14")),
    ]


def test_build_per_series_matches_latest_available_positive_ttm_eps() -> None:
    closes = [
        (date(2025, 3, 30), Decimal("90")),
        (date(2025, 3, 31), Decimal("100")),
        (date(2025, 6, 30), Decimal("120")),
        (date(2025, 9, 30), Decimal("140")),
    ]
    ttm_eps_series = [
        (date(2025, 3, 31), Decimal("10")),
        (date(2025, 6, 30), Decimal("0")),
        (date(2025, 9, 30), Decimal("-2")),
    ]

    assert build_per_series(closes, ttm_eps_series) == [Decimal("10")]


def test_median_and_percentile_quantizes_median_and_ranks_last_value() -> None:
    # Source: deterministic arithmetic sequence; median is (10.9 + 11.0) / 2.
    series = [Decimal("10") + Decimal(index) / 10 for index in range(20)]

    assert median_and_percentile(series) == (Decimal("10.95"), 100)


def test_median_and_percentile_rounds_rank_to_zero_boundary() -> None:
    # Source: one minimum final value among 201 observations gives a 0.498% rank.
    series = [Decimal(index) for index in range(1, 201)] + [Decimal("0")]

    assert median_and_percentile(series) == (Decimal("100.00"), 0)


@pytest.mark.parametrize("count", [0, 19])
def test_median_and_percentile_requires_twenty_observations(count: int) -> None:
    series = [Decimal(index) for index in range(count)]

    assert median_and_percentile(series) is None


def test_build_per_series_accepts_unsorted_closes() -> None:
    first_date = date(2025, 4, 1)
    closes = [
        (first_date + timedelta(days=1), Decimal("120")),
        (first_date, Decimal("100")),
    ]

    assert build_per_series(
        closes,
        [(date(2025, 3, 31), Decimal("10"))],
    ) == [Decimal("10"), Decimal("12")]
