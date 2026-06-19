from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.decision_checklist.model import BuyChecklistNote


class BuyChecklistNoteRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_user_asset(self, user_id: int, asset_id: int) -> BuyChecklistNote | None:
        stmt = select(BuyChecklistNote).where(
            BuyChecklistNote.user_id == user_id,
            BuyChecklistNote.asset_id == asset_id,
        )
        return self.db.scalars(stmt).first()

    def upsert(
        self,
        user_id: int,
        asset_id: int,
        memo: str | None,
        checked_item_keys: Sequence[str],
        decided_at: datetime | None,
    ) -> BuyChecklistNote:
        note = self.get_by_user_asset(user_id, asset_id)
        if note is None:
            note = BuyChecklistNote(
                user_id=user_id,
                asset_id=asset_id,
                memo=memo,
                checked_item_keys=list(checked_item_keys),
                decided_at=decided_at,
            )
            self.db.add(note)
        else:
            note.memo = memo
            note.checked_item_keys = list(checked_item_keys)
            note.decided_at = decided_at

        self.db.commit()
        self.db.refresh(note)
        return note
