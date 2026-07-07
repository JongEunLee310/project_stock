from app.adapters.factory import get_exchange_rate_provider
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.market.schema import ExchangeRateResponse

DEFAULT_FX_PAIR = "USD/KRW"


class ExchangeRateService:
    def get_rates(self, pairs: list[str]) -> list[ExchangeRateResponse]:
        try:
            rates = get_exchange_rate_provider().get_rates(pairs)
        except Exception as exc:
            raise AppException(
                status_code=502,
                detail="시세 제공자에서 가격 데이터를 가져오지 못했습니다.",
                error_code=ErrorCode.MARKET_DATA_PROVIDER_ERROR,
            ) from exc

        return [
            ExchangeRateResponse(
                pair=rate.pair,
                rate=rate.rate,
                change_percent=rate.change_percent,
                reference_at=rate.as_of,
            )
            for rate in rates
        ]


def parse_fx_pairs(pairs: str | None) -> list[str]:
    if pairs is None:
        return [DEFAULT_FX_PAIR]

    normalized_pairs = [pair.strip().upper() for pair in pairs.split(",") if pair.strip()]
    return normalized_pairs or [DEFAULT_FX_PAIR]
