from datetime import date

from sqlalchemy.orm import Session

from app.adapters.factory import get_market_provider
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.signals.model import Signal
from app.domains.signals.repository import SignalRepository, SignalSnapshotRepository
from app.domains.signals.schema import (
    SignalChange,
    SignalChangeDirection,
    SignalChangeTimelineItem,
    SignalCreate,
    SignalCurrentExpandedResponse,
    SignalCurrentResponse,
    SignalDominantSummary,
    SignalExpandedResponse,
    SignalResponse,
    SignalSummary,
)
from app.domains.signals.snapshot_model import AssetSignalSnapshot
from app.domains.signals.time import utc_now
from app.domains.signals.types import (
    SignalCategory,
    signal_category_for_type,
    signal_priority_rank,
)
from app.domains.watchlists.schema import AssetBriefResponse


class SignalService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.asset_repo = AssetRepository(db)
        self.repo = SignalRepository(db)
        self.snapshot_repo = SignalSnapshotRepository(db)

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
        asset_id: int | None,
        include_expired: bool = False,
        offset: int = 0,
        limit: int | None = None,
        view: str = "all",
    ) -> list[Signal]:
        if view == "current":
            return self.repo.list_current_by_asset(
                asset_id,
                offset=offset,
                limit=limit,
            )
        if asset_id is None:
            return self.repo.list_all(
                include_expired,
                offset=offset,
                limit=limit,
            )
        return self.repo.list_by_asset(
            asset_id,
            include_expired,
            offset=offset,
            limit=limit,
        )

    def list_signals_expanded(
        self,
        asset_id: int | None,
        include_expired: bool = False,
        offset: int = 0,
        limit: int | None = None,
        view: str = "all",
    ) -> list[SignalExpandedResponse | SignalCurrentExpandedResponse]:
        signals = self.list_signals(
            asset_id,
            include_expired,
            offset=offset,
            limit=limit,
            view=view,
        )
        changes_by_asset = (
            self.changes_by_asset([signal.asset_id for signal in signals])
            if view == "current"
            else {}
        )
        asset_ids = [signal.asset_id for signal in signals]
        assets = {asset.id: asset for asset in self.asset_repo.list_by_ids(asset_ids)}
        symbols = [asset.symbol for asset in assets.values()]
        quotes = {
            quote.symbol: quote
            for quote in get_market_provider().get_quote(symbols)
        } if symbols else {}

        result: list[SignalExpandedResponse | SignalCurrentExpandedResponse] = []
        for signal in signals:
            asset = assets.get(signal.asset_id)
            asset_brief: AssetBriefResponse | None = None
            if asset is not None:
                quote = quotes.get(asset.symbol)
                asset_brief = AssetBriefResponse(
                    symbol=asset.symbol,
                    market=asset.market,
                    name=asset.name,
                    price=str(quote.price) if quote is not None else "0",
                    change_percent=str(quote.change_percent) if quote is not None else "0",
                    sector=asset.sector,
                )
            signal_data = SignalResponse.model_validate(signal).model_dump()
            if view == "current":
                result.append(
                    SignalCurrentExpandedResponse(
                        **signal_data,
                        asset=asset_brief,
                        change=changes_by_asset.get(signal.asset_id),
                    )
                )
            else:
                result.append(SignalExpandedResponse(**signal_data, asset=asset_brief))
        return result

    def list_current_signals(
        self,
        asset_id: int | None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[SignalCurrentResponse]:
        signals = self.repo.list_current_by_asset(
            asset_id,
            offset=offset,
            limit=limit,
        )
        changes_by_asset = self.changes_by_asset([signal.asset_id for signal in signals])
        return [
            SignalCurrentResponse(
                **SignalResponse.model_validate(signal).model_dump(),
                change=changes_by_asset.get(signal.asset_id),
            )
            for signal in signals
        ]

    def count_signals(
        self,
        asset_id: int | None,
        include_expired: bool = False,
        view: str = "all",
    ) -> int:
        if view == "current":
            return self.repo.count_current(asset_id)
        if asset_id is None:
            return self.repo.count_all(include_expired)
        return self.repo.count_by_asset(asset_id, include_expired)

    def capture_daily_snapshot(self, snapshot_date: date | None = None) -> int:
        effective_date = snapshot_date or utc_now().date()
        captured_at = utc_now()
        assets = self.asset_repo.list_all()
        dominant_by_asset = {
            signal.asset_id: signal
            for signal in self.repo.list_current_by_asset(asset_id=None)
        }
        for asset in assets:
            dominant = dominant_by_asset.get(asset.id)
            self.snapshot_repo.upsert_daily(
                asset_id=asset.id,
                snapshot_date=effective_date,
                signal_id=dominant.id if dominant is not None else None,
                signal_type=dominant.signal_type if dominant is not None else None,
                score=dominant.score if dominant is not None else None,
                captured_at=captured_at,
            )
        self.db.commit()
        return len(assets)

    def changes_by_asset(self, asset_ids: list[int]) -> dict[int, SignalChange | None]:
        pairs = self.snapshot_repo.latest_pair_by_asset(asset_ids)
        return {
            asset_id: build_change(latest, previous)
            for asset_id, (latest, previous) in pairs.items()
        }

    def list_recent_changes(
        self,
        *,
        limit: int,
        since: date | None,
    ) -> list[SignalChangeTimelineItem]:
        snapshots = self.snapshot_repo.list_all_ordered()
        previous_by_asset: dict[int, AssetSignalSnapshot | None] = {}
        change_rows: list[tuple[AssetSignalSnapshot, SignalChange]] = []
        for snapshot in snapshots:
            previous = previous_by_asset.get(snapshot.asset_id)
            previous_by_asset[snapshot.asset_id] = snapshot
            if since is not None and snapshot.snapshot_date < since:
                continue
            change = build_change(snapshot, previous)
            if change is None or change.direction == SignalChangeDirection.UNCHANGED:
                continue
            change_rows.append((snapshot, change))

        change_rows.sort(
            key=lambda row: (row[0].snapshot_date, row[0].captured_at, row[0].id),
            reverse=True,
        )
        limited_rows = change_rows[:limit]
        assets = {
            asset.id: asset
            for asset in self.asset_repo.list_by_ids(
                [snapshot.asset_id for snapshot, _change in limited_rows]
            )
        }
        return [
            SignalChangeTimelineItem(
                asset=AssetBriefResponse(
                    symbol=asset.symbol,
                    market=asset.market,
                    name=asset.name,
                    price="0",
                    change_percent="0",
                    sector=asset.sector,
                ),
                snapshot_date=snapshot.snapshot_date,
                captured_at=snapshot.captured_at,
                change=change,
                dominant=(
                    SignalDominantSummary(
                        signal_id=snapshot.signal_id,
                        signal_type=snapshot.signal_type,
                        score=snapshot.score,
                    )
                    if snapshot.signal_type is not None and snapshot.score is not None
                    else None
                ),
            )
            for snapshot, change in limited_rows
            if (asset := assets.get(snapshot.asset_id)) is not None
        ]

    def summary(self, view: str) -> SignalSummary:
        if view != "current":
            raise AppException(
                status_code=400,
                detail="summary는 view=current만 지원합니다.",
                error_code=ErrorCode.VALIDATION_ERROR,
            )
        by_category = _empty_category_counts()
        current_signals = self.repo.list_current_by_asset(asset_id=None)
        for signal in current_signals:
            category = signal_category_for_type(signal.signal_type)
            if category is not None:
                by_category[category.value] += 1

        delta_by_category = _empty_category_counts()
        latest_date = self.snapshot_repo.latest_snapshot_date()
        if latest_date is not None:
            previous_date = self.snapshot_repo.previous_snapshot_date(latest_date)
            if previous_date is not None:
                latest_counts = self.snapshot_repo.count_by_category_for_date(latest_date)
                previous_counts = self.snapshot_repo.count_by_category_for_date(previous_date)
                delta_by_category = {
                    category.value: latest_counts[category.value]
                    - previous_counts[category.value]
                    for category in SignalCategory
                }
        return SignalSummary(
            total=len(current_signals),
            by_category=by_category,
            delta_by_category=delta_by_category,
        )


def build_change(
    latest: AssetSignalSnapshot | None,
    previous: AssetSignalSnapshot | None,
) -> SignalChange | None:
    if latest is None:
        return None

    score_delta = (
        latest.score - previous.score
        if previous is not None
        and latest.score is not None
        and previous.score is not None
        else None
    )
    previous_type = previous.signal_type if previous is not None else None
    previous_captured_at = previous.captured_at if previous is not None else None

    if previous is None:
        direction = SignalChangeDirection.NEW
    elif previous.signal_type is None and latest.signal_type is not None:
        direction = SignalChangeDirection.NEW
    elif previous.signal_type is not None and latest.signal_type is None:
        direction = SignalChangeDirection.CLEARED
    elif latest.signal_type == previous.signal_type:
        direction = SignalChangeDirection.UNCHANGED
    else:
        latest_rank = signal_priority_rank(latest.signal_type)
        previous_rank = signal_priority_rank(previous.signal_type)
        if (
            latest_rank is not None
            and previous_rank is not None
            and latest_rank < previous_rank
        ):
            direction = SignalChangeDirection.ESCALATED
        elif (
            latest_rank is not None
            and previous_rank is not None
            and latest_rank > previous_rank
        ):
            direction = SignalChangeDirection.DEESCALATED
        else:
            direction = SignalChangeDirection.CHANGED

    return SignalChange(
        direction=direction,
        score_delta=score_delta,
        previous_type=previous_type,
        previous_captured_at=previous_captured_at,
    )


def _empty_category_counts() -> dict[str, int]:
    return {category.value: 0 for category in SignalCategory}
