from fastapi import APIRouter

from app.core.response import ApiResponse, success
from app.domains.market.index_service import MarketIndexService
from app.domains.market.schema import MarketIndexQuoteResponse

router = APIRouter()


@router.get(
    "/indices",
    response_model=ApiResponse[list[MarketIndexQuoteResponse]],
    summary="Get market index quotes",
    description="Return deterministic snapshot quotes for representative indices.",
)
def get_market_indices() -> ApiResponse[list[MarketIndexQuoteResponse]]:
    return success(MarketIndexService().get_quotes())
