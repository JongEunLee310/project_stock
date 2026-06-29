from sqlalchemy.orm import Session

from app.adapters.factory import get_market_provider
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.alert_candidates.model import AlertCandidate
from app.domains.alert_candidates.repository import AlertCandidateRepository
from app.domains.alert_candidates.schema import (
    AlertCandidateCreate,
    AlertCandidateExpandedResponse,
    AlertCandidateResponse,
)
from app.domains.alert_candidates.types import AlertCandidateStatus
from app.domains.watchlists.schema import AssetBriefResponse


class AlertCandidateService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.repo = AlertCandidateRepository(db)

    def create_candidate(self, data: AlertCandidateCreate) -> AlertCandidate:
        return self.repo.create(data)

    def list_candidates(
        self,
        user_id: int,
        candidate_type: str | None = None,
        importance: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int | None = None,
        sort: str = "-created_at",
    ) -> list[AlertCandidate]:
        return self.repo.list_by_user(
            user_id,
            candidate_type=candidate_type,
            importance=importance,
            status=status,
            offset=offset,
            limit=limit,
            sort=sort,
        )

    def count_candidates(
        self,
        user_id: int,
        candidate_type: str | None = None,
        importance: str | None = None,
        status: str | None = None,
    ) -> int:
        return self.repo.count_by_user(
            user_id,
            candidate_type=candidate_type,
            importance=importance,
            status=status,
        )

    def list_candidates_expanded(
        self,
        user_id: int,
        candidate_type: str | None = None,
        importance: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int | None = None,
        sort: str = "-created_at",
    ) -> list[AlertCandidateExpandedResponse]:
        candidates = self.list_candidates(
            user_id,
            candidate_type=candidate_type,
            importance=importance,
            status=status,
            offset=offset,
            limit=limit,
            sort=sort,
        )
        asset_ids = {
            candidate.asset_id
            for candidate in candidates
            if candidate.asset_id is not None
        }
        assets = {
            asset.id: asset
            for asset in [self.asset_repo.get_by_id(aid) for aid in asset_ids]
            if asset is not None
        }
        symbols = [asset.symbol for asset in assets.values()]
        quotes = (
            {
                quote.symbol: quote
                for quote in get_market_provider().get_quote(symbols)
            }
            if symbols
            else {}
        )

        result = []
        for candidate in candidates:
            asset = (
                assets.get(candidate.asset_id)
                if candidate.asset_id is not None
                else None
            )
            asset_brief: AssetBriefResponse | None = None
            if asset is not None:
                quote = quotes.get(asset.symbol)
                asset_brief = AssetBriefResponse(
                    symbol=asset.symbol,
                    name=asset.name,
                    price=str(quote.price) if quote is not None else "0",
                    change_percent=str(quote.change_percent)
                    if quote is not None
                    else "0",
                    sector=asset.sector,
                )
            candidate_data = AlertCandidateResponse.model_validate(
                candidate
            ).model_dump()
            result.append(
                AlertCandidateExpandedResponse(**candidate_data, asset=asset_brief)
            )
        return result

    def mark_read(self, candidate_id: int, user_id: int) -> AlertCandidate:
        return self._update_owned_candidate(
            candidate_id,
            user_id,
            AlertCandidateStatus.READ.value,
        )

    def confirm(self, candidate_id: int, user_id: int) -> AlertCandidate:
        return self._update_owned_candidate(
            candidate_id,
            user_id,
            AlertCandidateStatus.CONFIRMED.value,
        )

    def _update_owned_candidate(
        self,
        candidate_id: int,
        user_id: int,
        status: str,
    ) -> AlertCandidate:
        candidate = self.repo.get_by_id(candidate_id)
        if candidate is None or candidate.user_id != user_id:
            raise AppException(
                status_code=404,
                detail="알림 후보를 찾을 수 없습니다.",
                error_code=ErrorCode.ALERT_CANDIDATE_NOT_FOUND,
            )
        return self.repo.update_status(candidate, status)
