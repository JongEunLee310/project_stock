from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.asset_events.schema import (
    AssetEventHistoryResponse,
    AssetEventProjection,
    AssetEventRange,
    AssetEventType,
)
from app.domains.assets.repository import AssetRepository
from app.domains.earnings.model import EarningsEvent
from app.domains.earnings.repository import EarningsRepository

_RANGE_DELTAS: dict[AssetEventRange, timedelta] = {
    AssetEventRange.ONE_MONTH: timedelta(days=31),
    AssetEventRange.THREE_MONTHS: timedelta(days=92),
    AssetEventRange.SIX_MONTHS: timedelta(days=183),
    AssetEventRange.ONE_YEAR: timedelta(days=366),
}
_PERCENT_PRECISION = Decimal("0.01")


class AssetEventService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.earnings_repo = EarningsRepository(db)

    def get_history(
        self,
        asset_id: int,
        range_: AssetEventRange,
    ) -> AssetEventHistoryResponse:
        asset = self.asset_repo.get_by_id(asset_id)
        if asset is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )
        end = date.today()
        start = end - _RANGE_DELTAS[range_]
        events = self.earnings_repo.get_events(
            asset.symbol,
            asset.market,
            start,
            end,
        )
        return AssetEventHistoryResponse(
            asset_id=asset.id,
            range=range_,
            events=[self._projection(event) for event in events],
        )

    @staticmethod
    def _projection(event: EarningsEvent) -> AssetEventProjection:
        surprise = None
        if (
            event.eps_actual is not None
            and event.eps_estimate is not None
            and event.eps_estimate != 0
        ):
            surprise = (
                (event.eps_actual - event.eps_estimate)
                / abs(event.eps_estimate)
                * 100
            ).quantize(_PERCENT_PRECISION)
        return AssetEventProjection(
            event_date=event.event_date,
            event_type=AssetEventType.EARNINGS,
            eps_actual=event.eps_actual,
            eps_estimate=event.eps_estimate,
            eps_surprise_percent=surprise,
        )
