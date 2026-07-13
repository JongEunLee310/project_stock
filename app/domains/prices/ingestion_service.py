from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.market.base import PriceBarResult, PriceSeriesProvider
from app.domains.prices.normalizer import PriceNormalizer
from app.domains.prices.repository import PriceBarRepository
from app.domains.prices.validator import PriceValidator
from app.domains.raw_prices.service import RawPriceService

logger = logging.getLogger(__name__)


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
        self.normalizer = PriceNormalizer()
        self.validator = PriceValidator()

    def collect_and_save(
        self,
        provider: PriceSeriesProvider,
        targets: list[tuple[str, str]],
        range_value: str = "3M",
    ) -> IngestionResult:
        result = IngestionResult(target_count=len(targets))
        for symbol, market in targets:
            result = self._collect_target(
                provider, symbol, market, range_value, result
            )
        return result

    def _collect_target(
        self,
        provider: PriceSeriesProvider,
        symbol: str,
        market: str,
        range_value: str,
        result: IngestionResult,
    ) -> IngestionResult:
        normalized_symbol = self.normalizer.canonicalize_symbol(symbol)
        normalized_market = self.normalizer.canonicalize_market(market)
        try:
            bars = provider.get_daily_bars(
                normalized_symbol,
                normalized_market,
                range_value,
                adjusted=True,
            )
            payload = _provider_payload(provider, normalized_symbol, normalized_market, bars)
            raw_price = self.raw_price_service.save_raw(
                normalized_symbol,
                normalized_market,
                payload,
                source=_provider_source(provider, bars),
            )
            validation = self.validator.validate_bars(
                bars,
                normalized_symbol,
                normalized_market,
            )
            saved_count = (
                self.price_repo.upsert_bars(validation.valid_bars)
                if validation.valid_bars
                else 0
            )
            return IngestionResult(
                target_count=result.target_count,
                success_count=result.success_count + 1,
                failure_count=result.failure_count,
                raw_saved_count=result.raw_saved_count + (1 if raw_price else 0),
                raw_skipped_count=result.raw_skipped_count + (0 if raw_price else 1),
                received_bar_count=result.received_bar_count + len(bars),
                saved_bar_count=result.saved_bar_count + saved_count,
                dropped_bar_count=result.dropped_bar_count + validation.dropped_count,
                warning_count=result.warning_count + validation.warning_count,
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
def _as_utc(value: datetime) -> datetime:
    return PriceNormalizer().normalize_timestamp(value)
