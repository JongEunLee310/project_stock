import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.signals.model import Signal
from app.domains.signals.schema import SignalCreate
from app.domains.signals.snapshot_model import AssetSignalSnapshot
from app.domains.signals.time import utc_now
from app.domains.signals.types import WATCHLIST_STATUS_PRIORITY


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

    def list_by_asset(
        self,
        asset_id: int,
        include_expired: bool,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Signal]:
        stmt = select(Signal).where(Signal.asset_id == asset_id)
        if not include_expired:
            stmt = stmt.where(self._active_clause())
        stmt = stmt.order_by(Signal.created_at.desc(), Signal.id.desc())
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def list_all(
        self,
        include_expired: bool,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Signal]:
        stmt = select(Signal)
        if not include_expired:
            stmt = stmt.where(self._active_clause())
        stmt = stmt.order_by(Signal.created_at.desc(), Signal.id.desc())
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def list_current_by_asset(
        self,
        asset_id: int | None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Signal]:
        rank_by_type = {
            signal_type.value: rank
            for rank, signal_type in enumerate(WATCHLIST_STATUS_PRIORITY)
        }
        rank_expression = case(
            rank_by_type,
            value=Signal.signal_type,
            else_=len(rank_by_type),
        )
        ranked_stmt = select(
            Signal.id.label("signal_id"),
            func.row_number()
            .over(
                partition_by=Signal.asset_id,
                order_by=(
                    rank_expression.asc(),
                    Signal.score.desc(),
                    Signal.created_at.desc(),
                    Signal.id.desc(),
                ),
            )
            .label("asset_rank"),
        ).where(self._active_clause())
        if asset_id is not None:
            ranked_stmt = ranked_stmt.where(Signal.asset_id == asset_id)
        ranked = ranked_stmt.subquery()
        stmt = (
            select(Signal)
            .join(ranked, Signal.id == ranked.c.signal_id)
            .where(ranked.c.asset_rank == 1)
            .order_by(Signal.score.desc(), Signal.created_at.desc(), Signal.asset_id.asc())
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def count_by_asset(self, asset_id: int, include_expired: bool) -> int:
        stmt = select(func.count()).select_from(Signal).where(Signal.asset_id == asset_id)
        if not include_expired:
            stmt = stmt.where(self._active_clause())
        return int(self.db.scalar(stmt) or 0)

    def count_all(self, include_expired: bool) -> int:
        stmt = select(func.count()).select_from(Signal)
        if not include_expired:
            stmt = stmt.where(self._active_clause())
        return int(self.db.scalar(stmt) or 0)

    def count_current(self, asset_id: int | None) -> int:
        stmt = select(func.count(func.distinct(Signal.asset_id))).select_from(Signal).where(
            self._active_clause()
        )
        if asset_id is not None:
            stmt = stmt.where(Signal.asset_id == asset_id)
        return int(self.db.scalar(stmt) or 0)

    def count_assets_with_active_signal(
        self,
        asset_ids: list[int],
        signal_type: str,
    ) -> int:
        if not asset_ids:
            return 0
        stmt = (
            select(func.count(func.distinct(Signal.asset_id)))
            .select_from(Signal)
            .where(
                Signal.asset_id.in_(asset_ids),
                Signal.signal_type == signal_type,
                self._active_clause(),
            )
        )
        return int(self.db.scalar(stmt) or 0)

    def count_assets_with_active_signal_as_of(
        self,
        asset_ids: list[int],
        signal_type: str,
        as_of: Any,
    ) -> int:
        if not asset_ids:
            return 0
        stmt = (
            select(func.count(func.distinct(Signal.asset_id)))
            .select_from(Signal)
            .where(
                Signal.asset_id.in_(asset_ids),
                Signal.signal_type == signal_type,
                Signal.created_at <= as_of,
                or_(Signal.expires_at.is_(None), Signal.expires_at > as_of),
            )
        )
        return int(self.db.scalar(stmt) or 0)

    def active_signal_types_by_asset(
        self,
        asset_ids: list[int],
    ) -> dict[int, set[str]]:
        if not asset_ids:
            return {}
        stmt = (
            select(Signal.asset_id, Signal.signal_type)
            .where(
                Signal.asset_id.in_(asset_ids),
                self._active_clause(),
            )
            .distinct()
        )
        active_types: dict[int, set[str]] = {}
        for asset_id, signal_type in self.db.execute(stmt):
            active_types.setdefault(asset_id, set()).add(signal_type)
        return active_types

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
        now = utc_now()
        return or_(Signal.expires_at.is_(None), Signal.expires_at > now)

    def _dump_evidence(self, value: dict[str, Any] | None) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)


class SignalSnapshotRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_daily(
        self,
        *,
        asset_id: int,
        snapshot_date: date,
        signal_id: int | None,
        signal_type: str | None,
        score: int | None,
        captured_at: datetime,
    ) -> AssetSignalSnapshot:
        snapshot = self.get_by_asset_date(asset_id, snapshot_date)
        if snapshot is None:
            snapshot = AssetSignalSnapshot(
                asset_id=asset_id,
                snapshot_date=snapshot_date,
                signal_id=signal_id,
                signal_type=signal_type,
                score=score,
                captured_at=captured_at,
            )
            self.db.add(snapshot)
            try:
                self.db.flush()
            except IntegrityError:
                self.db.rollback()
                snapshot = self.get_by_asset_date(asset_id, snapshot_date)
                if snapshot is None:
                    raise
        snapshot.signal_id = signal_id
        snapshot.signal_type = signal_type
        snapshot.score = score
        snapshot.captured_at = captured_at
        self.db.flush()
        return snapshot

    def get_by_asset_date(
        self,
        asset_id: int,
        snapshot_date: date,
    ) -> AssetSignalSnapshot | None:
        stmt = select(AssetSignalSnapshot).where(
            AssetSignalSnapshot.asset_id == asset_id,
            AssetSignalSnapshot.snapshot_date == snapshot_date,
        )
        return self.db.scalars(stmt).one_or_none()

    def get_latest(self, asset_id: int) -> AssetSignalSnapshot | None:
        stmt = (
            select(AssetSignalSnapshot)
            .where(AssetSignalSnapshot.asset_id == asset_id)
            .order_by(
                AssetSignalSnapshot.snapshot_date.desc(),
                AssetSignalSnapshot.captured_at.desc(),
                AssetSignalSnapshot.id.desc(),
            )
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def get_previous(
        self,
        asset_id: int,
        before_date: date,
    ) -> AssetSignalSnapshot | None:
        stmt = (
            select(AssetSignalSnapshot)
            .where(
                AssetSignalSnapshot.asset_id == asset_id,
                AssetSignalSnapshot.snapshot_date < before_date,
            )
            .order_by(
                AssetSignalSnapshot.snapshot_date.desc(),
                AssetSignalSnapshot.captured_at.desc(),
                AssetSignalSnapshot.id.desc(),
            )
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def latest_pair_by_asset(
        self,
        asset_ids: list[int],
    ) -> dict[int, tuple[AssetSignalSnapshot | None, AssetSignalSnapshot | None]]:
        if not asset_ids:
            return {}
        ranked = (
            select(
                AssetSignalSnapshot.id.label("snapshot_id"),
                AssetSignalSnapshot.asset_id.label("asset_id"),
                func.row_number()
                .over(
                    partition_by=AssetSignalSnapshot.asset_id,
                    order_by=(
                        AssetSignalSnapshot.snapshot_date.desc(),
                        AssetSignalSnapshot.captured_at.desc(),
                        AssetSignalSnapshot.id.desc(),
                    ),
                )
                .label("snapshot_rank"),
            )
            .where(AssetSignalSnapshot.asset_id.in_(asset_ids))
            .subquery()
        )
        stmt = (
            select(AssetSignalSnapshot, ranked.c.snapshot_rank)
            .join(ranked, AssetSignalSnapshot.id == ranked.c.snapshot_id)
            .where(ranked.c.snapshot_rank <= 2)
            .order_by(
                AssetSignalSnapshot.asset_id.asc(),
                ranked.c.snapshot_rank.asc(),
            )
        )
        pairs: dict[
            int,
            tuple[AssetSignalSnapshot | None, AssetSignalSnapshot | None],
        ] = {asset_id: (None, None) for asset_id in asset_ids}
        for snapshot, snapshot_rank in self.db.execute(stmt):
            latest, previous = pairs[snapshot.asset_id]
            if snapshot_rank == 1:
                latest = snapshot
            else:
                previous = snapshot
            pairs[snapshot.asset_id] = (latest, previous)
        return pairs

    def list_all_ordered(self) -> list[AssetSignalSnapshot]:
        stmt = select(AssetSignalSnapshot).order_by(
            AssetSignalSnapshot.asset_id.asc(),
            AssetSignalSnapshot.snapshot_date.asc(),
            AssetSignalSnapshot.captured_at.asc(),
            AssetSignalSnapshot.id.asc(),
        )
        return list(self.db.scalars(stmt).all())

    def latest_snapshot_date(self) -> date | None:
        stmt = select(func.max(AssetSignalSnapshot.snapshot_date))
        return self.db.scalar(stmt)

    def previous_snapshot_date(self, latest_date: date) -> date | None:
        stmt = select(func.max(AssetSignalSnapshot.snapshot_date)).where(
            AssetSignalSnapshot.snapshot_date < latest_date
        )
        return self.db.scalar(stmt)

    def count_by_category_for_date(self, snapshot_date: date) -> dict[str, int]:
        from app.domains.signals.types import SignalCategory, signal_category_for_type

        counts = {category.value: 0 for category in SignalCategory}
        stmt = select(AssetSignalSnapshot.signal_type).where(
            AssetSignalSnapshot.snapshot_date == snapshot_date,
            AssetSignalSnapshot.signal_type.is_not(None),
        )
        for signal_type in self.db.scalars(stmt):
            category = signal_category_for_type(signal_type)
            if category is not None:
                counts[category.value] += 1
        return counts
