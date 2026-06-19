from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.assets.schema import AssetCreate, AssetResponse


class AssetService:
    def __init__(self, db: Session) -> None:
        self.repo = AssetRepository(db)

    def register(self, data: AssetCreate) -> AssetResponse:
        if self.repo.get_by_symbol_market(data.symbol, data.market):
            raise AppException(status_code=400, detail="이미 등록된 종목입니다.")
        try:
            asset = self.repo.create(
                symbol=data.symbol,
                name=data.name,
                market=data.market,
            )
        except IntegrityError as exc:
            raise AppException(status_code=400, detail="이미 등록된 종목입니다.") from exc
        return AssetResponse.model_validate(asset)

    def get(self, asset_id: int) -> AssetResponse:
        asset = self.repo.get_by_id(asset_id)
        if asset is None:
            raise AppException(status_code=404, detail="종목을 찾을 수 없습니다.")
        return AssetResponse.model_validate(asset)

    def list(
        self,
        is_active: bool | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[AssetResponse]:
        return [
            AssetResponse.model_validate(asset)
            for asset in self.repo.list_all(
                is_active=is_active,
                offset=offset,
                limit=limit,
            )
        ]

    def count(self, is_active: bool | None = None) -> int:
        return self.repo.count_all(is_active=is_active)
