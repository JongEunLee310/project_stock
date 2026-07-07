from fastapi import APIRouter, Query

from app.core.response import ApiResponse, success
from app.domains.market.fx_service import (
    DEFAULT_FX_PAIR,
    ExchangeRateService,
    parse_fx_pairs,
)
from app.domains.market.index_service import MarketIndexService
from app.domains.market.schema import ExchangeRateResponse, MarketIndexQuoteResponse

router = APIRouter()


@router.get(
    "/indices",
    response_model=ApiResponse[list[MarketIndexQuoteResponse]],
    summary="Get market index quotes",
    description="Return deterministic snapshot quotes for representative indices.",
)
def get_market_indices() -> ApiResponse[list[MarketIndexQuoteResponse]]:
    return success(MarketIndexService().get_quotes())


@router.get(
    "/fx",
    response_model=ApiResponse[list[ExchangeRateResponse]],
    summary="Get exchange rates",
    description="Return deterministic snapshot exchange rates for requested pairs.",
)
def get_exchange_rates(
    pairs: str | None = Query(default=DEFAULT_FX_PAIR),
) -> ApiResponse[list[ExchangeRateResponse]]:
    return success(ExchangeRateService().get_rates(parse_fx_pairs(pairs)))
