from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.research_summary.schema import (
    ResearchSummaryResponse,
    ResearchSummarySource,
)

_UPDATED_AT = datetime(2026, 6, 19, 0, 0, tzinfo=timezone.utc)

_SUMMARY_TEMPLATES = [
    {
        "positive_factors": ["견조한 매출 성장", "현금흐름 개선", "주요 제품 수요 유지"],
        "negative_factors": ["밸류에이션 부담", "환율 변동성", "경쟁 심화"],
        "items_to_verify": ["최근 실적 발표 원문 확인", "가이던스 변화 확인"],
    },
    {
        "positive_factors": ["비용 효율화 진행", "신규 고객 증가", "마진 방어력 확인"],
        "negative_factors": ["단기 뉴스 과열", "재고 부담", "규제 리스크"],
        "items_to_verify": ["공시 일정 확인", "섹터 평균 대비 밸류에이션 확인"],
    },
]


class ResearchSummaryService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)

    def get_summary(self, asset_id: int) -> ResearchSummaryResponse:
        asset = self.asset_repo.get_by_id(asset_id)
        if asset is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )

        template = _SUMMARY_TEMPLATES[asset.id % len(_SUMMARY_TEMPLATES)]
        return ResearchSummaryResponse(
            asset_id=asset.id,
            positive_factors=list(template["positive_factors"]),
            negative_factors=list(template["negative_factors"]),
            items_to_verify=list(template["items_to_verify"]),
            sources=[
                ResearchSummarySource(type="news", label=f"{asset.symbol} mock news"),
                ResearchSummarySource(
                    type="disclosure",
                    label=f"{asset.symbol} mock disclosure",
                ),
                ResearchSummarySource(type="report", label="Mock research report"),
            ],
            updated_at=_UPDATED_AT,
        )
