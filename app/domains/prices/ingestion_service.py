from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.market.base import PriceBarResult, PriceSeriesProvider
from app.domains.prices.repository import PriceBarRepository
from app.domains.raw_prices.service import RawPriceService

logger = logging.getLogger(__name__)

_OUTLIER_THRESHOLD = Decimal("0.5")
_EXPECTED_CURRENCY_BY_MARKET = {
    "KOSPI": "KRW",
    "KOSDAQ": "KRW",
    "NASDAQ": "USD",
    "NYSE": "USD",
}


@dataclass(frozen=True)
class IngestionResult:
    target_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    raw_saved_count: int = 0
    raw_skipped_count: int = 0
    received_bar_count: int = 0
    saved_bar_count: int = 0
    dropped_bar_count: int = 0
    warning_count: int = 0


class PriceIngestionService:
    def __init__(self, db: Session) -> None:
        self.price_repo = PriceBarRepository(db)
        self.raw_price_service = RawPriceService(db)

    def collect_and_save(
        self,
        provider: PriceSeriesProvider,
        targets: list[tuple[str, str]],
    ) -> IngestionResult:
        result = IngestionResult(target_count=len(targets))
        for symbol, market in targets:
            result = self._collect_target(provider, symbol, market, result)
        return result

    def _collect_target(
        self,
        provider: PriceSeriesProvider,
        symbol: str,
        market: str,
        result: IngestionResult,
    ) -> IngestionResult:
        normalized_symbol = symbol.upper()
        normalized_market = market.upper()
        try:
            bars = provider.get_daily_bars(
                normalized_symbol,
                normalized_market,
                "3M",
                adjusted=True,
            )
            payload = _provider_payload(provider, normalized_symbol, normalized_market, bars)
            raw_price = self.raw_price_service.save_raw(
                normalized_symbol,
                normalized_market,
                payload,
                source=_provider_source(provider, bars),
            )
            valid_bars, dropped_count, warning_count = self._validate_bars(
                bars,
                normalized_symbol,
                normalized_market,
            )
            saved_count = self.price_repo.upsert_bars(valid_bars) if valid_bars else 0
            return IngestionResult(
                target_count=result.target_count,
                success_count=result.success_count + 1,
                failure_count=result.failure_count,
                raw_saved_count=result.raw_saved_count + (1 if raw_price else 0),
                raw_skipped_count=result.raw_skipped_count + (0 if raw_price else 1),
                received_bar_count=result.received_bar_count + len(bars),
                saved_bar_count=result.saved_bar_count + saved_count,
                dropped_bar_count=result.dropped_bar_count + dropped_count,
                warning_count=result.warning_count + warning_count,
            )
        except Exception:
            logger.exception(
                "Failed to collect price target",
                extra={"symbol": normalized_symbol, "market": normalized_market},
            )
            return IngestionResult(
                target_count=result.target_count,
                success_count=result.success_count,
                failure_count=result.failure_count + 1,
                raw_saved_count=result.raw_saved_count,
                raw_skipped_count=result.raw_skipped_count,
                received_bar_count=result.received_bar_count,
                saved_bar_count=result.saved_bar_count,
                dropped_bar_count=result.dropped_bar_count,
                warning_count=result.warning_count,
            )

    def _validate_bars(
        self,
        bars: list[PriceBarResult],
        symbol: str,
        market: str,
    ) -> tuple[list[PriceBarResult], int, int]:
        valid_bars: list[PriceBarResult] = []
        dropped_count = 0
        warning_count = 0
        previous_close: Decimal | None = None
        today = date.today()

        for bar in sorted(bars, key=lambda item: item.timestamp):
            if _has_missing_required_price(bar):
                logger.warning(
                    "Dropping price bar with missing OHLC data",
                    extra={"symbol": symbol, "market": market},
                )
                dropped_count += 1
                continue
            if _as_utc(bar.timestamp).date() > today:
                logger.warning(
                    "Dropping future-dated price bar",
                    extra={"symbol": symbol, "market": market},
                )
                dropped_count += 1
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

            valid_bars.append(bar)
            previous_close = bar.close_price

        return valid_bars, dropped_count, warning_count


def _provider_payload(
    provider: PriceSeriesProvider,
    symbol: str,
    market: str,
    bars: list[PriceBarResult],
) -> dict[str, Any]:
    payload = getattr(provider, "last_payload", None)
    if isinstance(payload, dict):
        return payload
    return {
        "symbol": symbol,
        "market": market,
        "source": _provider_source(provider, bars),
        "rows": [
            {
                "timestamp": bar.timestamp.isoformat(),
                "open": str(bar.open_price),
                "high": str(bar.high_price),
                "low": str(bar.low_price),
                "close": str(bar.close_price),
                "adjusted_close": str(bar.adjusted_close_price),
                "volume": bar.volume,
                "currency": bar.currency,
            }
            for bar in bars
        ],
    }


def _provider_source(provider: PriceSeriesProvider, bars: list[PriceBarResult]) -> str:
    source = getattr(provider, "source", None)
    if isinstance(source, str):
        return source
    if bars:
        return bars[0].source
    return provider.__class__.__name__


def _has_missing_required_price(bar: PriceBarResult) -> bool:
    return any(
        value is None
        for value in (
            bar.open_price,
            bar.high_price,
            bar.low_price,
            bar.close_price,
            bar.adjusted_close_price,
        )
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
