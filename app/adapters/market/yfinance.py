from datetime import UTC, date, datetime
from decimal import Decimal
import logging
import math
from typing import Any, cast

import yfinance as yf  # type: ignore[import-untyped]

from app.adapters.market.base import (
    EarningsProvider,
    EarningsReportResult,
    PriceBarResult,
    PriceSeriesProvider,
    SymbolLookupProvider,
    SymbolLookupResult,
    ValuationProvider,
    ValuationResult,
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
            interval="1d",
        )

    def get_intraday_bars(
        self,
        symbol: str,
        market: str,
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
        frame = ticker.history(period="1d", interval="15m", auto_adjust=True)
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
            interval="15m",
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


class YFinanceValuationProvider(ValuationProvider):
    source = "yfinance"

    def get_valuation(self, symbol: str, market: str) -> ValuationResult | None:
        ticker_symbol = to_yfinance_ticker(symbol, market)
        if ticker_symbol is None:
            return None
        try:
            info = yf.Ticker(ticker_symbol).info
        except Exception:
            logger.exception(
                "Failed to collect valuation",
                extra={"symbol": symbol.upper(), "market": market.upper()},
            )
            return None
        return valuation_from_info(info, as_of=date.today(), source=self.source)


class YFinanceEarningsProvider(EarningsProvider):
    source = "yfinance"

    def get_quarterly_earnings(
        self, symbol: str, market: str
    ) -> list[EarningsReportResult]:
        ticker_symbol = to_yfinance_ticker(symbol, market)
        if ticker_symbol is None:
            return []
        try:
            ticker = yf.Ticker(ticker_symbol)
            return earnings_reports_from_frames(
                ticker.quarterly_income_stmt,
                ticker.earnings_dates,
                source=self.source,
            )
        except Exception:
            logger.exception(
                "Failed to collect quarterly earnings",
                extra={"symbol": symbol.upper(), "market": market.upper()},
            )
            return []


def earnings_reports_from_frames(
    income_stmt: Any,
    earnings_dates: Any,
    *,
    source: str,
) -> list[EarningsReportResult]:
    if income_stmt is None or getattr(income_stmt, "empty", True):
        return []
    estimates = _earnings_estimates(earnings_dates)
    reports = [
        EarningsReportResult(
            period_end=_date_from_value(column),
            revenue=_frame_decimal(income_stmt, "Total Revenue", column),
            operating_income=_frame_decimal(income_stmt, "Operating Income", column),
            eps=_frame_decimal(income_stmt, "Diluted EPS", column),
            eps_estimate=_closest_estimate(_date_from_value(column), estimates),
            source=source,
        )
        for column in income_stmt.columns
    ]
    return sorted(reports, key=lambda report: report.period_end, reverse=True)[:8]


def period_from_end(period_end: date) -> str:
    quarter = (period_end.month - 1) // 3 + 1
    return f"{period_end.year}Q{quarter}"


def _frame_decimal(frame: Any, row_name: str, column: Any) -> Decimal | None:
    if row_name not in frame.index:
        return None
    return _optional_decimal(frame.at[row_name, column])


def _earnings_estimates(frame: Any) -> list[tuple[date, Decimal]]:
    if frame is None or getattr(frame, "empty", True):
        return []
    estimates: list[tuple[date, Decimal]] = []
    for index, row in frame.iterrows():
        estimate = _optional_decimal(row.get("EPS Estimate"))
        if estimate is not None:
            estimates.append((_date_from_value(index), estimate))
    return estimates


def _closest_estimate(
    period_end: date, estimates: list[tuple[date, Decimal]]
) -> Decimal | None:
    if not estimates:
        return None
    return min(estimates, key=lambda item: abs(item[0] - period_end))[1]


def _date_from_value(value: Any) -> date:
    if hasattr(value, "date"):
        result = value.date()
        if isinstance(result, date):
            return result
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def valuation_from_info(
    info: Any,
    *,
    as_of: date,
    source: str,
) -> ValuationResult | None:
    if not isinstance(info, dict):
        return None
    free_cash_flow = _optional_decimal(info.get("freeCashflow"))
    market_cap = _optional_decimal(info.get("marketCap"))
    fcf_yield = (
        free_cash_flow / market_cap * Decimal("100")
        if free_cash_flow is not None
        and market_cap is not None
        and market_cap != Decimal("0")
        else None
    )
    return ValuationResult(
        per=_optional_decimal(info.get("trailingPE")),
        forward_per=_optional_decimal(info.get("forwardPE")),
        psr=_optional_decimal(info.get("priceToSalesTrailing12Months")),
        pbr=_optional_decimal(info.get("priceToBook")),
        ev_ebitda=_optional_decimal(info.get("enterpriseToEbitda")),
        peg=_optional_decimal(info.get("trailingPegRatio")),
        fcf_yield=fcf_yield,
        as_of=as_of,
        source=source,
    )


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
        "5Y": "5y",
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
    interval: str,
) -> list[PriceBarResult]:
    bars: list[PriceBarResult] = []
    if frame.empty:
        return bars

    for index, row in frame.iterrows():
        bars.append(
            PriceBarResult(
                symbol=symbol,
                market=market,
                interval=interval,
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


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or _is_nan(value):
        return None
    try:
        result = Decimal(str(value))
    except (ValueError, TypeError):
        return None
    return result if result.is_finite() else None


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
