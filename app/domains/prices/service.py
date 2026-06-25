from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.adapters.factory import get_price_series_provider
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.prices.model import StockPriceBar
from app.domains.prices.repository import PriceBarRepository
from app.domains.prices.schema import PriceBar, PriceSeriesResponse

_RANGE_COUNTS = {
    "1M": 22,
    "3M": 66,
    "6M": 132,
    "1Y": 252,
}
_SUPPORTED_INTERVAL = "1d"


class PriceSeriesService:
    def __init__(self, db: Session) -> None:
        self.repo = PriceBarRepository(db)

    def get_series(
        self,
        symbol: str,
        market: str,
        range_value: str = "3M",
        interval: str = _SUPPORTED_INTERVAL,
        adjusted: bool = True,
    ) -> PriceSeriesResponse:
        normalized_symbol = symbol.upper()
        normalized_market = market.upper()
        self._validate_range(range_value)
        self._validate_interval(interval)
        count = _RANGE_COUNTS[range_value]

        try:
            generated_bars = get_price_series_provider().get_daily_bars(
                normalized_symbol,
                normalized_market,
                range_value,
                adjusted,
            )
        except Exception as exc:
            raise AppException(
                status_code=502,
                detail="시세 제공자에서 가격 데이터를 가져오지 못했습니다.",
                error_code=ErrorCode.MARKET_DATA_PROVIDER_ERROR,
            ) from exc

        if not generated_bars:
            raise AppException(
                status_code=404,
                detail="가격 시계열을 찾을 수 없습니다.",
                error_code=ErrorCode.PRICE_SERIES_NOT_FOUND,
            )

        try:
            self.repo.upsert_many(generated_bars)
        except SQLAlchemyError as exc:
            raise AppException(
                status_code=502,
                detail="가격 데이터를 저장하지 못했습니다.",
                error_code=ErrorCode.MARKET_DATA_PROVIDER_ERROR,
            ) from exc

        bars = self.repo.list_recent(
            symbol=normalized_symbol,
            market=normalized_market,
            interval=interval,
            limit=count,
        )
        if not bars:
            raise AppException(
                status_code=404,
                detail="가격 시계열을 찾을 수 없습니다.",
                error_code=ErrorCode.PRICE_SERIES_NOT_FOUND,
            )
        return self._to_response(
            symbol=normalized_symbol,
            market=normalized_market,
            range_value=range_value,
            interval=interval,
            bars=bars,
        )

    def _validate_range(self, range_value: str) -> None:
        if range_value not in _RANGE_COUNTS:
            raise AppException(
                status_code=400,
                detail="지원하지 않는 가격 범위입니다.",
                error_code=ErrorCode.INVALID_PRICE_RANGE,
            )

    def _validate_interval(self, interval: str) -> None:
        if interval != _SUPPORTED_INTERVAL:
            raise AppException(
                status_code=400,
                detail="지원하지 않는 가격 간격입니다.",
                error_code=ErrorCode.INVALID_PRICE_INTERVAL,
            )

    def _to_response(
        self,
        symbol: str,
        market: str,
        range_value: str,
        interval: str,
        bars: list[StockPriceBar],
    ) -> PriceSeriesResponse:
        latest = max(bar.updated_at or bar.timestamp for bar in bars)
        return PriceSeriesResponse(
            symbol=symbol,
            market=market,
            currency=bars[-1].currency,
            interval=interval,
            range=range_value,
            source=bars[-1].source,
            last_updated_at=_as_utc(latest),
            bars=[self._to_bar(bar) for bar in bars],
        )

    def _to_bar(self, bar: StockPriceBar) -> PriceBar:
        return PriceBar(
            date=bar.timestamp.date().isoformat(),
            open=_decimal_to_wire(bar.open_price),
            high=_decimal_to_wire(bar.high_price),
            low=_decimal_to_wire(bar.low_price),
            close=_decimal_to_wire(bar.close_price),
            adjusted_close=_decimal_to_wire(bar.adjusted_close_price),
            volume=bar.volume,
        )


def _decimal_to_wire(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
