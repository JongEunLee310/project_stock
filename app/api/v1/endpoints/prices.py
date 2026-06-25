from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.response import ApiResponse, success
from app.db.session import get_db
from app.domains.prices.schema import PriceSeriesResponse
from app.domains.prices.service import PriceSeriesService

router = APIRouter()


@router.get(
    "/{symbol}/prices",
    response_model=ApiResponse[PriceSeriesResponse],
    summary="Get stock price series",
    description="Return deterministic daily OHLCV price bars for a stock symbol.",
)
def get_stock_price_series(
    symbol: str,
    market: Literal["KRX", "NASDAQ", "NYSE"],
    price_range: Annotated[str, Query(alias="range")] = "3M",
    interval: str = "1d",
    adjusted: bool = True,
    db: Session = Depends(get_db),
) -> ApiResponse[PriceSeriesResponse]:
    return success(
        PriceSeriesService(db).get_series(
            symbol=symbol,
            market=market,
            range_value=price_range,
            interval=interval,
            adjusted=adjusted,
        )
    )
