from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from statistics import median
from typing import Protocol

_TTM_QUARTERS = 4
_MIN_OBSERVATIONS = 20
_TWO_DECIMAL_PLACES = Decimal("0.01")


class EarningsReportLike(Protocol):
    @property
    def period_end(self) -> date: ...

    @property
    def eps(self) -> Decimal | None: ...


def build_ttm_eps_series(
    reports: Iterable[EarningsReportLike],
) -> list[tuple[date, Decimal]]:
    ordered_reports = sorted(reports, key=lambda report: report.period_end)
    series: list[tuple[date, Decimal]] = []
    for index in range(_TTM_QUARTERS - 1, len(ordered_reports)):
        window = ordered_reports[index - _TTM_QUARTERS + 1 : index + 1]
        eps_values = [report.eps for report in window]
        if any(eps is None for eps in eps_values):
            continue
        # yfinance stores consecutive quarters, so calendar-gap correction is omitted.
        ttm_eps = sum((eps for eps in eps_values if eps is not None), Decimal("0"))
        series.append((ordered_reports[index].period_end, ttm_eps))
    return series


def build_per_series(
    closes: Iterable[tuple[date, Decimal]],
    ttm_eps_series: Iterable[tuple[date, Decimal]],
) -> list[Decimal]:
    ordered_eps = sorted(ttm_eps_series, key=lambda item: item[0])
    if not ordered_eps:
        return []

    series: list[Decimal] = []
    eps_index = -1
    for close_date, close_price in sorted(closes, key=lambda item: item[0]):
        while (
            eps_index + 1 < len(ordered_eps)
            and ordered_eps[eps_index + 1][0] <= close_date
        ):
            eps_index += 1
        if eps_index < 0:
            continue
        ttm_eps = ordered_eps[eps_index][1]
        if ttm_eps <= 0:
            continue
        series.append(close_price / ttm_eps)
    return series


def median_and_percentile(series: list[Decimal]) -> tuple[Decimal, int] | None:
    if len(series) < _MIN_OBSERVATIONS:
        return None
    median_value = median(series).quantize(_TWO_DECIMAL_PLACES)
    latest_value = series[-1]
    rank_count = sum(value <= latest_value for value in series)
    percentile = int(
        (Decimal(rank_count) * 100 / Decimal(len(series))).quantize(Decimal("1"))
    )
    return median_value, percentile
