from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.domains.features.price_builder import PriceFeatureBuilder
from app.domains.features.schema import PriceFeatureSet
from app.domains.prices.model import StockPriceBar


def test_price_feature_builder_calculates_all_features_with_full_history() -> None:
    bars = [
        _price_bar(
            day_offset=index,
            close_price=Decimal(index + 1),
            high_price=Decimal(index + 11),
            volume=100 + index + 1,
        )
        for index in range(252)
    ]

    features = PriceFeatureBuilder().build(bars)

    assert features == PriceFeatureSet(
        return_1d=Decimal("1") / Decimal("251"),
        return_5d=Decimal("5") / Decimal("247"),
        return_20d=Decimal("20") / Decimal("232"),
        volume_vs_20d_avg=Decimal("352") / Decimal("342.5"),
        drawdown_from_52w_high=Decimal("-10") / Decimal("262"),
    )


def test_price_feature_builder_degrades_by_feature_when_history_is_short() -> None:
    features = PriceFeatureBuilder().build(
        [
            _price_bar(
                day_offset=0,
                close_price=Decimal("90"),
                high_price=Decimal("100"),
                volume=100,
            ),
        ],
    )

    assert features.return_1d is None
    assert features.return_5d is None
    assert features.return_20d is None
    assert features.volume_vs_20d_avg is None
    assert features.drawdown_from_52w_high == Decimal("-0.1")


def test_price_feature_builder_calculates_features_at_minimum_windows() -> None:
    bars = [
        _price_bar(
            day_offset=index,
            close_price=Decimal(index + 1),
            high_price=Decimal(index + 1),
            volume=index + 1,
        )
        for index in range(21)
    ]

    features = PriceFeatureBuilder().build(bars)

    assert features.return_1d == Decimal("1") / Decimal("20")
    assert features.return_5d == Decimal("5") / Decimal("16")
    assert features.return_20d == Decimal("20")
    assert features.volume_vs_20d_avg == Decimal("21") / Decimal("11.5")
    assert features.drawdown_from_52w_high == Decimal("0")


def test_price_feature_builder_returns_none_when_denominator_is_zero() -> None:
    bars = [
        _price_bar(
            day_offset=index,
            close_price=Decimal("0"),
            high_price=Decimal("0"),
            volume=0,
        )
        for index in range(21)
    ]

    features = PriceFeatureBuilder().build(bars)

    assert features.return_1d is None
    assert features.return_5d is None
    assert features.return_20d is None
    assert features.volume_vs_20d_avg is None
    assert features.drawdown_from_52w_high is None


def test_price_feature_builder_reorders_descending_input() -> None:
    bars = [
        _price_bar(
            day_offset=index,
            close_price=Decimal(index + 1),
            high_price=Decimal(index + 11),
            volume=100 + index + 1,
        )
        for index in range(252)
    ]

    builder = PriceFeatureBuilder()

    assert builder.build(list(reversed(bars))) == builder.build(bars)


def _price_bar(
    *,
    day_offset: int,
    close_price: Decimal,
    high_price: Decimal,
    volume: int,
) -> StockPriceBar:
    return StockPriceBar(
        symbol="AAPL",
        market="NASDAQ",
        interval="1d",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=day_offset),
        open_price=close_price,
        high_price=high_price,
        low_price=close_price,
        close_price=close_price,
        adjusted_close_price=close_price,
        volume=volume,
        currency="USD",
        source="test",
    )
