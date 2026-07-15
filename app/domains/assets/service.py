from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.factory import get_market_provider, get_symbol_lookup_provider
from app.adapters.market.base import SymbolLookupResult
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.assets.schema import (
    AnalystOpinionItem,
    AnalystOpinionsResponse,
    AssetCreate,
    AssetDetailResponse,
    AssetLookupItem,
    AssetLookupResponse,
    AssetResponse,
)


class AssetService:
    def __init__(self, db: Session) -> None:
        self.repo = AssetRepository(db)

    def register(self, data: AssetCreate) -> AssetResponse:
        normalized_symbol = data.symbol.strip().upper()
        normalized_market = data.market.strip().upper()
        if self.repo.get_by_symbol_market(normalized_symbol, normalized_market):
            raise AppException(
                status_code=400,
                detail="이미 등록된 종목입니다.",
                error_code=ErrorCode.ASSET_DUPLICATE,
            )
        lookup_item = self._find_exact_market_symbol(
            normalized_symbol,
            normalized_market,
        )
        if lookup_item is None:
            raise AppException(
                status_code=422,
                detail="시장 데이터에서 확인되지 않은 종목입니다.",
                error_code=ErrorCode.ASSET_NOT_IN_MARKET,
            )
        try:
            asset = self.repo.create(
                symbol=lookup_item.symbol,
                name=lookup_item.name,
                market=lookup_item.market,
                sector=lookup_item.sector,
                industry=None,
                description=None,
            )
        except IntegrityError as exc:
            raise AppException(
                status_code=400,
                detail="이미 등록된 종목입니다.",
                error_code=ErrorCode.ASSET_DUPLICATE,
            ) from exc
        return AssetResponse.model_validate(asset)

    def lookup(
        self,
        query: str,
        market: str | None = None,
    ) -> AssetLookupResponse:
        normalized_market = market.strip().upper() if market is not None else None
        items = []
        for result in get_symbol_lookup_provider().search(query, normalized_market):
            registered = (
                self.repo.get_by_symbol_market(result.symbol, result.market) is not None
            )
            items.append(
                AssetLookupItem(
                    symbol=result.symbol,
                    name=result.name,
                    market=result.market,
                    sector=result.sector,
                    registered=registered,
                )
            )
        return AssetLookupResponse(items=items)

    def _find_exact_market_symbol(
        self,
        symbol: str,
        market: str,
    ) -> SymbolLookupResult | None:
        for result in get_symbol_lookup_provider().search(symbol, market):
            if result.symbol == symbol and result.market == market:
                return result
        return None

    def get_detail(self, asset_id: int) -> AssetDetailResponse:
        asset = self.repo.get_by_id(asset_id)
        if asset is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )
        market_provider = get_market_provider()
        quote = market_provider.get_quote([asset.symbol])[0]
        price_targets = market_provider.get_price_targets([asset.symbol])
        price_target = price_targets[0] if price_targets else None
        target_price = (
            price_target.target_price
            if price_target is not None and price_target.target_price is not None
            else quote.target_price
        )
        target_upside_percent = _target_upside_percent(target_price, quote.price)
        return AssetDetailResponse(
            id=asset.id,
            symbol=asset.symbol,
            name=asset.name,
            market=asset.market,
            price=str(quote.price),
            previous_close=str(quote.previous_close),
            change=str(quote.change),
            change_percent=str(quote.change_percent),
            currency=quote.currency,
            sector=asset.sector,
            industry=asset.industry,
            description=asset.description,
            updated_at=quote.as_of,
            market_cap=str(quote.market_cap) if quote.market_cap is not None else None,
            next_earnings_date=quote.next_earnings_date,
            per=str(quote.per) if quote.per is not None else None,
            peg=str(quote.peg) if quote.peg is not None else None,
            fifty_two_week_low=str(quote.fifty_two_week_low) if quote.fifty_two_week_low is not None else None,
            fifty_two_week_high=str(quote.fifty_two_week_high) if quote.fifty_two_week_high is not None else None,
            target_price=str(target_price) if target_price is not None else None,
            target_price_high=(
                str(price_target.target_price_high)
                if price_target is not None
                and price_target.target_price_high is not None
                else None
            ),
            target_price_low=(
                str(price_target.target_price_low)
                if price_target is not None
                and price_target.target_price_low is not None
                else None
            ),
            target_analyst_count=(
                price_target.target_analyst_count
                if price_target is not None
                else None
            ),
            target_upside_percent=(
                str(target_upside_percent)
                if target_upside_percent is not None
                else None
            ),
        )

    def get_analyst_opinions(
        self, asset_id: int, limit: int
    ) -> AnalystOpinionsResponse:
        asset = self.repo.get_by_id(asset_id)
        if asset is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )
        results = get_market_provider().get_analyst_opinions(asset.symbol, limit)
        return AnalystOpinionsResponse(
            asset_id=asset.id,
            opinions=[
                AnalystOpinionItem(
                    firm=result.firm,
                    action=result.action,
                    to_grade=result.to_grade,
                    from_grade=result.from_grade,
                    price_target=(
                        str(result.price_target)
                        if result.price_target is not None
                        else None
                    ),
                    prior_price_target=(
                        str(result.prior_price_target)
                        if result.prior_price_target is not None
                        else None
                    ),
                    price_target_action=result.price_target_action,
                    published_at=result.published_at,
                )
                for result in results
            ],
        )

    def get(self, asset_id: int) -> AssetResponse:
        asset = self.repo.get_by_id(asset_id)
        if asset is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )
        return AssetResponse.model_validate(asset)

    def list(
        self,
        is_active: bool | None = None,
        symbol: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[AssetResponse]:
        return [
            AssetResponse.model_validate(asset)
            for asset in self.repo.list_all(
                is_active=is_active,
                symbol=symbol,
                offset=offset,
                limit=limit,
            )
        ]

    def count(self, is_active: bool | None = None, symbol: str | None = None) -> int:
        return self.repo.count_all(is_active=is_active, symbol=symbol)


def _target_upside_percent(
    target_price: Decimal | None,
    current_price: Decimal,
) -> Decimal | None:
    if target_price is None:
        return None
    if current_price == Decimal("0"):
        return Decimal("0.00")
    return (
        (target_price - current_price) / current_price * Decimal("100")
    ).quantize(Decimal("0.01"))
