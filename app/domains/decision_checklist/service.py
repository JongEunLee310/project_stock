from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.decision_checklist.model import BuyChecklistNote
from app.domains.decision_checklist.repository import BuyChecklistNoteRepository
from app.domains.decision_checklist.schema import (
    BuyChecklistItem,
    BuyChecklistNoteUpdate,
    BuyChecklistResponse,
    ChecklistItemKey,
)

_REQUIRED_KEYS: tuple[ChecklistItemKey, ...] = (
    "valuation",
    "news_overheated",
    "portfolio_concentration",
    "earnings_disclosure",
)

_ITEM_LABELS: dict[ChecklistItemKey, str] = {
    "valuation": "밸류에이션 확인",
    "news_overheated": "최근 뉴스 과열 여부",
    "portfolio_concentration": "포트폴리오 비중 초과 여부",
    "earnings_disclosure": "실적/공시 확인 여부",
}


class DecisionChecklistService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.note_repo = BuyChecklistNoteRepository(db)

    def get_checklist(self, asset_id: int, user_id: int) -> BuyChecklistResponse:
        self._ensure_asset(asset_id)
        note = self.note_repo.get_by_user_asset(user_id, asset_id)
        return self._build_response(asset_id, note)

    def save_note(
        self,
        asset_id: int,
        user_id: int,
        data: BuyChecklistNoteUpdate,
    ) -> BuyChecklistResponse:
        self._ensure_asset(asset_id)
        unique_keys = list(dict.fromkeys(data.checked_item_keys))
        existing_note = self.note_repo.get_by_user_asset(user_id, asset_id)
        is_complete = self._is_complete(data.memo, set(unique_keys))
        decided_at = self._next_decided_at(existing_note, is_complete)
        note = self.note_repo.upsert(
            user_id=user_id,
            asset_id=asset_id,
            memo=data.memo,
            checked_item_keys=unique_keys,
            decided_at=decided_at,
        )
        return self._build_response(asset_id, note)

    def _ensure_asset(self, asset_id: int) -> None:
        if self.asset_repo.get_by_id(asset_id) is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )

    def _build_response(
        self,
        asset_id: int,
        note: BuyChecklistNote | None,
    ) -> BuyChecklistResponse:
        checked_keys = set(note.checked_item_keys if note is not None else [])
        items = [
            BuyChecklistItem(
                id=key,
                label=_ITEM_LABELS[key],
                description=self._detail_for(key),
                checked=key in checked_keys,
            )
            for key in _REQUIRED_KEYS
        ]
        memo = note.memo if note is not None else None
        is_complete = self._is_complete(memo, checked_keys)
        return BuyChecklistResponse(
            asset_id=asset_id,
            items=items,
            memo=memo,
            checked_item_keys=[
                key for key in _REQUIRED_KEYS if key in checked_keys
            ],
            is_complete=is_complete,
            decided_at=note.decided_at if note is not None else None,
        )

    def _is_complete(self, memo: str | None, checked_keys: set[str]) -> bool:
        return bool(memo and memo.strip()) and checked_keys.issuperset(_REQUIRED_KEYS)

    def _next_decided_at(
        self,
        note: BuyChecklistNote | None,
        is_complete: bool,
    ) -> datetime | None:
        if not is_complete:
            return None
        if note is not None and note.decided_at is not None:
            return note.decided_at
        return datetime.now(timezone.utc)

    def _detail_for(self, key: ChecklistItemKey) -> str:
        details: dict[ChecklistItemKey, str] = {
            "valuation": "현재 가격과 최근 실적 기준 밸류에이션을 확인하세요.",
            "news_overheated": "단기 뉴스 급등락 요인이 있는지 확인하세요.",
            "portfolio_concentration": "매수 후 단일 종목 비중이 과도하지 않은지 확인하세요.",
            "earnings_disclosure": "최근 실적 발표와 주요 공시를 확인하세요.",
        }
        return details[key]
