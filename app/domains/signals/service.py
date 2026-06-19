from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.domains.signals.model import Signal
from app.domains.signals.repository import SignalRepository
from app.domains.signals.schema import SignalCreate


class SignalService:
    def __init__(self, db: Session) -> None:
        self.repo = SignalRepository(db)

    def create_signal(self, data: SignalCreate) -> Signal:
        return self.repo.create(data)

    def get_signal(self, signal_id: int) -> Signal:
        signal = self.repo.get_by_id(signal_id)
        if signal is None:
            raise AppException(status_code=404, detail="신호를 찾을 수 없습니다.")
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

    def count_signals(
        self,
        asset_id: int,
        include_expired: bool = False,
    ) -> int:
        return self.repo.count_by_asset(asset_id, include_expired)
