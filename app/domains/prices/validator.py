from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import logging
from typing import Any

from app.adapters.market.base import PriceBarResult
from app.domains.ingestion.schema import DataQualityStatus, ValidationErrorReason
from app.domains.prices.normalizer import PriceNormalizer

logger = logging.getLogger(__name__)

_OUTLIER_THRESHOLD = Decimal("0.5")
_EXPECTED_CURRENCY_BY_MARKET = {
    "KOSPI": "KRW",
    "KOSDAQ": "KRW",
    "NASDAQ": "USD",
    "NYSE": "USD",
}


@dataclass(frozen=True)
class PriceValidationResult:
    valid_bars: list[PriceBarResult]
    dropped_count: int
    warning_count: int
    status: DataQualityStatus
    reasons: list[ValidationErrorReason]


class PriceValidator:
    def __init__(self) -> None:
        self.normalizer = PriceNormalizer()

    def validate_bars(
        self,
        bars: list[PriceBarResult],
        symbol: str,
        market: str,
    ) -> PriceValidationResult:
        valid_bars: list[PriceBarResult] = []
        dropped_count = 0
        warning_count = 0
        previous_close: Decimal | None = None
        today = date.today()
        reasons: list[ValidationErrorReason] = []

        for bar in sorted(bars, key=lambda item: item.timestamp):
            if _has_missing_required_price(bar):
                logger.warning(
                    "Dropping price bar with missing OHLC data",
                    extra={"symbol": symbol, "market": market},
                )
                dropped_count += 1
                reasons.append(ValidationErrorReason.MISSING_REQUIRED_FIELD)
                continue
            if self.normalizer.normalize_timestamp(bar.timestamp).date() > today:
                logger.warning(
                    "Dropping future-dated price bar",
                    extra={"symbol": symbol, "market": market},
                )
                dropped_count += 1
                reasons.append(ValidationErrorReason.FUTURE_TIMESTAMP)
                continue

            expected_currency = _EXPECTED_CURRENCY_BY_MARKET.get(market)
            if expected_currency is not None and bar.currency.upper() != expected_currency:
                logger.warning(
                    "Price bar currency does not match expected market currency",
                    extra={
                        "symbol": symbol,
                        "market": market,
                        "currency": bar.currency,
                        "expected_currency": expected_currency,
                    },
                )
                warning_count += 1
                reasons.append(ValidationErrorReason.CURRENCY_MISMATCH)

            if previous_close is not None and previous_close != 0:
                return_rate = (bar.close_price - previous_close) / previous_close
                if abs(return_rate) > _OUTLIER_THRESHOLD:
                    logger.warning(
                        "Price bar return exceeds outlier threshold",
                        extra={
                            "symbol": symbol,
                            "market": market,
                            "return_rate": str(return_rate),
                        },
                    )
                    warning_count += 1
                    reasons.append(ValidationErrorReason.OUTLIER_RETURN)

            valid_bars.append(bar)
            previous_close = bar.close_price

        return PriceValidationResult(
            valid_bars=valid_bars,
            dropped_count=dropped_count,
            warning_count=warning_count,
            status=_status_for_counts(dropped_count, warning_count),
            reasons=reasons,
        )


def _status_for_counts(dropped_count: int, warning_count: int) -> DataQualityStatus:
    if dropped_count > 0:
        return DataQualityStatus.INVALID
    if warning_count > 0:
        return DataQualityStatus.LOW_TRUST
    return DataQualityStatus.VALID


def _has_missing_required_price(bar: PriceBarResult) -> bool:
    values: tuple[Any, ...] = (
        bar.open_price,
        bar.high_price,
        bar.low_price,
        bar.close_price,
        bar.adjusted_close_price,
    )
    return any(value is None for value in values)
