from datetime import datetime, timezone
from typing import TypedDict

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.research_summary.schema import ResearchRisk, ResearchSummaryResponse

_CREATED_AT = datetime(2026, 6, 19, 0, 0, tzinfo=timezone.utc)


class _RiskTemplate(TypedDict):
    id: str
    title: str
    level: str
    description: str


class _SummaryTemplate(TypedDict):
    stance: str
    stance_confidence: str
    headline: str
    body: str
    key_risks: list[_RiskTemplate]


_SUMMARY_TEMPLATES: tuple[_SummaryTemplate, ...] = (
    {
        "stance": "BUY_CANDIDATE",
        "stance_confidence": "0.72",
        "headline": "견조한 매출 성장과 현금흐름 개선이 확인됩니다.",
        "body": "주요 제품 수요가 유지되고 있으나 밸류에이션 부담과 환율 변동성은 함께 점검해야 합니다.",
        "key_risks": [
            {
                "id": "valuation",
                "title": "밸류에이션 부담",
                "level": "MEDIUM",
                "description": "현재 가격이 실적 개선 기대를 상당 부분 반영했는지 확인하세요.",
            },
            {
                "id": "competition",
                "title": "경쟁 심화",
                "level": "LOW",
                "description": "주요 제품군의 경쟁 강도와 마진 영향을 추적하세요.",
            },
        ],
    },
    {
        "stance": "WATCH",
        "stance_confidence": "0.64",
        "headline": "비용 효율화는 긍정적이나 단기 과열 여부를 확인해야 합니다.",
        "body": "신규 고객 증가와 마진 방어력이 관찰되지만 재고 부담과 규제 리스크가 남아 있습니다.",
        "key_risks": [
            {
                "id": "news_overheated",
                "title": "단기 뉴스 과열",
                "level": "MEDIUM",
                "description": "최근 뉴스 흐름이 가격에 과도하게 반영되었는지 확인하세요.",
            },
            {
                "id": "regulation",
                "title": "규제 리스크",
                "level": "HIGH",
                "description": "사업 모델에 영향을 줄 수 있는 규제 일정을 점검하세요.",
            },
        ],
    },
)


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
            stance=template["stance"],
            stance_confidence=template["stance_confidence"],
            headline=template["headline"],
            body=template["body"],
            key_risks=[
                ResearchRisk.model_validate(risk)
                for risk in template["key_risks"]
            ],
            created_at=_CREATED_AT,
        )
