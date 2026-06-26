from sqlalchemy.orm import Session

from app.adapters.factory import get_market_provider
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.signals.model import Signal
from app.domains.signals.repository import SignalRepository
from app.domains.signals.schema import SignalCreate, SignalExpandedResponse, SignalResponse
from app.domains.watchlists.schema import AssetBriefResponse


class SignalService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.repo = SignalRepository(db)

    def create_signal(self, data: SignalCreate) -> Signal:
        return self.repo.create(data)

    def get_signal(self, signal_id: int) -> Signal:
        signal = self.repo.get_by_id(signal_id)
        if signal is None:
            raise AppException(
                status_code=404,
                detail="신호를 찾을 수 없습니다.",
                error_code=ErrorCode.SIGNAL_NOT_FOUND,
            )
        return signal

    def list_signals(
        self,
        asset_id: int,
        include_expired: bool = False,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Signal]:
        return self.repo.list_by_asset(
            asset_id,
            include_expired,
            offset=offset,
            limit=limit,
        )

    def list_signals_expanded(
        self,
        asset_id: int,
        include_expired: bool = False,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[SignalExpandedResponse]:
        signals = self.list_signals(
            asset_id,
            include_expired,
            offset=offset,
            limit=limit,
        )
        asset_ids = [signal.asset_id for signal in signals]
        assets = {
            asset.id: asset
            for asset in [self.asset_repo.get_by_id(aid) for aid in asset_ids]
            if asset is not None
        }
        symbols = [asset.symbol for asset in assets.values()]
        quotes = {
            quote.symbol: quote
            for quote in get_market_provider().get_quote(symbols)
        } if symbols else {}

        result = []
        for signal in signals:
            asset = assets.get(signal.asset_id)
            asset_brief: AssetBriefResponse | None = None
            if asset is not None:
                quote = quotes.get(asset.symbol)
                asset_brief = AssetBriefResponse(
                    symbol=asset.symbol,
                    name=asset.name,
                    price=str(quote.price) if quote is not None else "0",
                    change_percent=str(quote.change_percent) if quote is not None else "0",
                    sector=asset.sector,
                )
            signal_data = SignalResponse.model_validate(signal).model_dump()
            result.append(SignalExpandedResponse(**signal_data, asset=asset_brief))
        return result

    def count_signals(
        self,
        asset_id: int,
        include_expired: bool = False,
    ) -> int:
        return self.repo.count_by_asset(asset_id, include_expired)
