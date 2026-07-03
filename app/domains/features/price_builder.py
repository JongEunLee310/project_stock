from decimal import Decimal

from app.domains.features.schema import PriceFeatureSet
from app.domains.prices.model import StockPriceBar

_RETURN_WINDOW_1D = 1
_RETURN_WINDOW_5D = 5
_RETURN_WINDOW_20D = 20
_VOLUME_AVG_WINDOW = 20
_HIGH_WINDOW_52W = 252


class PriceFeatureBuilder:
    def build(self, bars: list[StockPriceBar]) -> PriceFeatureSet:
        sorted_bars = sorted(bars, key=lambda bar: bar.timestamp)

        return PriceFeatureSet(
            return_1d=_calculate_return(sorted_bars, _RETURN_WINDOW_1D),
            return_5d=_calculate_return(sorted_bars, _RETURN_WINDOW_5D),
            return_20d=_calculate_return(sorted_bars, _RETURN_WINDOW_20D),
            volume_vs_20d_avg=_calculate_volume_vs_average(sorted_bars),
            drawdown_from_52w_high=_calculate_drawdown_from_high(sorted_bars),
        )


def _calculate_return(
    bars: list[StockPriceBar],
    lookback_window: int,
) -> Decimal | None:
    if len(bars) < lookback_window + 1:
        return None

    latest_close = bars[-1].close_price
    baseline_close = bars[-(lookback_window + 1)].close_price
    if baseline_close == 0:
        return None

    return (latest_close - baseline_close) / baseline_close


def _calculate_volume_vs_average(bars: list[StockPriceBar]) -> Decimal | None:
    if len(bars) < _VOLUME_AVG_WINDOW:
        return None

    window = bars[-_VOLUME_AVG_WINDOW:]
    average_volume = sum(Decimal(bar.volume) for bar in window) / Decimal(
        _VOLUME_AVG_WINDOW,
    )
    if average_volume == 0:
        return None

    return Decimal(bars[-1].volume) / average_volume


def _calculate_drawdown_from_high(bars: list[StockPriceBar]) -> Decimal | None:
    if not bars:
        return None

    high_window = bars[-_HIGH_WINDOW_52W:]
    high_price = max(bar.high_price for bar in high_window)
    if high_price == 0:
        return None

    return (bars[-1].close_price - high_price) / high_price

