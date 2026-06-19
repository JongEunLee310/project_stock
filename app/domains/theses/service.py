from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.theses.model import InvestmentThesis
from app.domains.theses.repository import ThesisRepository
from app.domains.theses.schema import ThesisCreate, ThesisResponse, ThesisUpdate


class ThesisService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.repo = ThesisRepository(db)

    def create(self, user_id: int, data: ThesisCreate) -> ThesisResponse:
        if self.asset_repo.get_by_id(data.asset_id) is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )
        thesis = self.repo.create(
            user_id=user_id,
            asset_id=data.asset_id,
            summary=data.summary,
            risk_factors=data.risk_factors,
            invalidation_conditions=data.invalidation_conditions,
        )
        return ThesisResponse.model_validate(thesis)

    def update(
        self, thesis_id: int, user_id: int, data: ThesisUpdate
    ) -> ThesisResponse:
        thesis = self._get_owned_thesis(thesis_id, user_id)
        updated = self.repo.update(
            thesis.id,
            data.model_dump(exclude_unset=True),
        )
        if updated is None:
            raise AppException(
                status_code=404,
                detail="투자 가설을 찾을 수 없습니다.",
                error_code=ErrorCode.THESIS_NOT_FOUND,
            )
        return ThesisResponse.model_validate(updated)

    def get_latest(self, asset_id: int, user_id: int) -> ThesisResponse:
        thesis = self.repo.get_latest_by_asset(asset_id, user_id)
        if thesis is None:
            raise AppException(
                status_code=404,
                detail="투자 가설을 찾을 수 없습니다.",
                error_code=ErrorCode.THESIS_NOT_FOUND,
            )
        return ThesisResponse.model_validate(thesis)

    def deactivate(self, thesis_id: int, user_id: int) -> ThesisResponse:
        thesis = self._get_owned_thesis(thesis_id, user_id)
        deactivated = self.repo.deactivate(thesis.id)
        if deactivated is None:
            raise AppException(
                status_code=404,
                detail="투자 가설을 찾을 수 없습니다.",
                error_code=ErrorCode.THESIS_NOT_FOUND,
            )
        return ThesisResponse.model_validate(deactivated)

    def _get_owned_thesis(
        self, thesis_id: int, user_id: int
    ) -> InvestmentThesis:
        thesis = self.repo.get_by_id(thesis_id)
        if thesis is None:
            raise AppException(
                status_code=404,
                detail="투자 가설을 찾을 수 없습니다.",
                error_code=ErrorCode.THESIS_NOT_FOUND,
            )
        if thesis.user_id != user_id:
            raise AppException(
                status_code=403,
                detail="투자 가설 접근 권한이 없습니다.",
                error_code=ErrorCode.THESIS_FORBIDDEN,
            )
        return thesis
