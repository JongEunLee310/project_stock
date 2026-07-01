from app.adapters.factory import get_index_quote_provider
from app.adapters.market.mock import MARKET_INDEX_SYMBOLS
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.market.schema import MarketIndexQuoteResponse


class MarketIndexService:
    def get_quotes(self) -> list[MarketIndexQuoteResponse]:
        try:
            quotes = get_index_quote_provider().get_quotes(MARKET_INDEX_SYMBOLS)
        except Exception as exc:
            raise AppException(
                status_code=502,
                detail="시세 제공자에서 가격 데이터를 가져오지 못했습니다.",
                error_code=ErrorCode.MARKET_DATA_PROVIDER_ERROR,
            ) from exc

        return [
            MarketIndexQuoteResponse(
                symbol=quote.symbol,
                name=quote.name,
                value=quote.value,
                change_percent=quote.change_percent,
                reference_at=quote.reference_at,
            )
            for quote in quotes
        ]
