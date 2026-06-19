import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domains.signals.model import Signal
from app.domains.signals.schema import SignalCreate


class SignalRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, data: SignalCreate) -> Signal:
        signal = Signal(
            asset_id=data.asset_id,
            thesis_id=data.thesis_id,
            news_item_id=data.news_item_id,
            signal_type=data.signal_type.value,
            score=data.score,
            risk_level=data.risk_level,
            reason=data.reason,
            evidence=self._dump_evidence(data.evidence),
            expires_at=data.expires_at,
        )
        self.db.add(signal)
        self.db.commit()
        self.db.refresh(signal)
        return signal

    def get_by_id(self, signal_id: int) -> Signal | None:
        return self.db.get(Signal, signal_id)

    def list_by_asset(self, asset_id: int, include_expired: bool) -> list[Signal]:
        stmt = select(Signal).where(Signal.asset_id == asset_id)
        if not include_expired:
            stmt = stmt.where(self._active_clause())
        stmt = stmt.order_by(Signal.created_at.desc(), Signal.id.desc())
        return list(self.db.scalars(stmt).all())

    def exists_active(
        self,
        asset_id: int,
        signal_type: str,
        news_item_id: int | None,
    ) -> bool:
        stmt = (
            select(Signal.id)
            .where(
                Signal.asset_id == asset_id,
                Signal.signal_type == signal_type,
                Signal.news_item_id == news_item_id,
                self._active_clause(),
            )
            .limit(1)
        )
        return self.db.scalar(stmt) is not None

    def _active_clause(self) -> Any:
        now = datetime.now(timezone.utc)
        return or_(Signal.expires_at.is_(None), Signal.expires_at > now)

    def _dump_evidence(self, value: dict[str, Any] | None) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)
