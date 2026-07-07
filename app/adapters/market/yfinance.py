from datetime import UTC, datetime
from decimal import Decimal
import logging
import math
from typing import Any, cast

import yfinance as yf  # type: ignore[import-untyped]

from app.adapters.market.base import (
    PriceBarResult,
    PriceSeriesProvider,
    SymbolLookupProvider,
    SymbolLookupResult,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)

_MARKET_SUFFIXES = {
    "KOSPI": ".KS",
    "KOSDAQ": ".KQ",
    "NASDAQ": "",
    "NYSE": "",
}
_YFINANCE_EXCHANGE_MARKETS = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NASDAQ": "NASDAQ",
    "NYQ": "NYSE",
    "NYSE": "NYSE",
    "ASE": "NYSE",
    "PCX": "NYSE",
    "KSC": "KOSPI",
    "KQ": "KOSDAQ",
}


class YFinancePriceProvider(PriceSeriesProvider):
    source = "yfinance"

    def __init__(self) -> None:
        self.last_payload: dict[str, Any] | None = None

    def get_daily_bars(
        self,
        symbol: str,
        market: str,
        range_value: str,
        adjusted: bool,
    ) -> list[PriceBarResult]:
        normalized_symbol = symbol.upper()
        normalized_market = market.upper()
        ticker_symbol = to_yfinance_ticker(normalized_symbol, normalized_market)
        if ticker_symbol is None:
            logger.warning(
                "Skipping unsupported market for yfinance price collection",
                extra={"symbol": normalized_symbol, "market": normalized_market},
            )
            self.last_payload = {
                "symbol": normalized_symbol,
                "market": normalized_market,
                "source": self.source,
                "skipped": "unsupported_market",
            }
            return []

        ticker = yf.Ticker(ticker_symbol)
        frame = ticker.history(
            period=_range_to_period(range_value),
            interval="1d",
            auto_adjust=adjusted,
        )
        currency = _currency_from_ticker(ticker, normalized_market)
        self.last_payload = _payload_from_frame(
            frame=frame,
            symbol=normalized_symbol,
            market=normalized_market,
            ticker=ticker_symbol,
            currency=currency,
        )
        return _bars_from_frame(
            frame=frame,
            symbol=normalized_symbol,
            market=normalized_market,
            currency=currency,
        )


class YFinanceSymbolLookupProvider(SymbolLookupProvider):
    def search(
        self,
        query: str,
        market: str | None = None,
    ) -> list[SymbolLookupResult]:
        normalized_market = market.strip().upper() if market is not None else None
        try:
            search = yf.Search(query.strip(), max_results=10)
            quotes = getattr(search, "quotes", [])
        except Exception as exc:
            raise AppException(
                status_code=502,
                detail="시장 데이터 제공자 조회 중 오류가 발생했습니다.",
                error_code=ErrorCode.MARKET_DATA_PROVIDER_ERROR,
            ) from exc

        results: list[SymbolLookupResult] = []
        for quote in quotes:
            result = _lookup_result_from_quote(quote)
            if result is None:
                continue
            if normalized_market is not None and result.market != normalized_market:
                continue
            results.append(result)
        return results


def to_yfinance_ticker(symbol: str, market: str) -> str | None:
    suffix = _MARKET_SUFFIXES.get(market.upper())
    if suffix is None:
        return None
    return f"{symbol.upper()}{suffix}"


def _lookup_result_from_quote(quote: Any) -> SymbolLookupResult | None:
    if not isinstance(quote, dict):
        return None
    symbol = quote.get("symbol")
    name = quote.get("shortname") or quote.get("longname") or quote.get("name")
    exchange = quote.get("exchange")
    if not isinstance(symbol, str) or not symbol:
        return None
    if not isinstance(name, str) or not name:
        return None
    if not isinstance(exchange, str):
        return None
    market = _YFINANCE_EXCHANGE_MARKETS.get(exchange.upper())
    if market is None:
        return None
    sector = quote.get("sector")
    return SymbolLookupResult(
        symbol=symbol.upper(),
        name=name,
        market=market,
        sector=sector if isinstance(sector, str) and sector else None,
    )


def _range_to_period(range_value: str) -> str:
    return {
        "1M": "1mo",
        "3M": "3mo",
        "6M": "6mo",
        "1Y": "1y",
    }.get(range_value, "3mo")


def _currency_from_ticker(ticker: Any, market: str) -> str:
    try:
        fast_info = ticker.fast_info
        currency = fast_info.get("currency") if fast_info is not None else None
    except Exception:
        currency = None
    if isinstance(currency, str) and currency:
        return currency.upper()
    return "KRW" if market in {"KOSPI", "KOSDAQ"} else "USD"


def _payload_from_frame(
    frame: Any,
    symbol: str,
    market: str,
    ticker: str,
    currency: str,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    if not frame.empty:
        for index, row in frame.iterrows():
            records.append(
                {
                    "timestamp": _timestamp_from_index(index).isoformat(),
                    "open": _to_json_value(row.get("Open")),
                    "high": _to_json_value(row.get("High")),
                    "low": _to_json_value(row.get("Low")),
                    "close": _to_json_value(row.get("Close")),
                    "adjusted_close": _to_json_value(
                        row.get("Adj Close", row.get("Close"))
                    ),
                    "volume": _to_json_value(row.get("Volume")),
                }
            )
    return {
        "symbol": symbol,
        "market": market,
        "ticker": ticker,
        "currency": currency,
        "source": YFinancePriceProvider.source,
        "rows": records,
    }


def _bars_from_frame(
    frame: Any,
    symbol: str,
    market: str,
    currency: str,
) -> list[PriceBarResult]:
    bars: list[PriceBarResult] = []
    if frame.empty:
        return bars

    for index, row in frame.iterrows():
        bars.append(
            PriceBarResult(
                symbol=symbol,
                market=market,
                interval="1d",
                timestamp=_timestamp_from_index(index),
                open_price=_to_decimal(row.get("Open")),
                high_price=_to_decimal(row.get("High")),
                low_price=_to_decimal(row.get("Low")),
                close_price=_to_decimal(row.get("Close")),
                adjusted_close_price=_to_decimal(row.get("Adj Close", row.get("Close"))),
                volume=int(row.get("Volume") or 0),
                currency=currency,
                source=YFinancePriceProvider.source,
            )
        )
    return bars


def _timestamp_from_index(index: Any) -> datetime:
    if hasattr(index, "to_pydatetime"):
        value = cast(datetime, index.to_pydatetime())
    elif isinstance(index, datetime):
        value = index
    else:
        value = datetime.fromisoformat(str(index))
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_decimal(value: Any) -> Decimal:
    if value is None or _is_nan(value):
        raise ValueError("missing price value")
    return Decimal(str(value))


def _to_json_value(value: Any) -> str | int | float | None:
    if value is None or _is_nan(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (str, int, float)):
        return value
    return str(value)


def _is_nan(value: Any) -> bool:
    try:
        return bool(math.isnan(value))
    except TypeError:
        return False
