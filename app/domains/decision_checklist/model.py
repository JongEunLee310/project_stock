from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class BuyChecklistNote(Base, TimestampMixin):
    __tablename__ = "buy_checklist_notes"
    __table_args__ = (
        UniqueConstraint("user_id", "asset_id", name="uq_buy_checklist_notes_user_asset"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_item_keys: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        server_default="[]",
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
