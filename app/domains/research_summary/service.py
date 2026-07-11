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
    evidence: list[str]


class _SummaryTemplate(TypedDict):
    stance: str
    stance_confidence: str
    stance_comment: str
    headline: str
    body: str
    positive_factors: list[str]
    caution_factors: list[str]
    next_checks: list[str]
    counter_view: list[str]
    confidence_basis: str
    key_risks: list[_RiskTemplate]


_SUMMARY_TEMPLATES: tuple[_SummaryTemplate, ...] = (
    {
        "stance": "BUY_CANDIDATE",
        "stance_confidence": "0.72",
        "stance_comment": "성장성과 현금흐름 개선을 확인하되 가격 부담을 함께 검토할 단계입니다.",
        "headline": "견조한 매출 성장과 현금흐름 개선이 확인됩니다.",
        "body": "주요 제품 수요가 유지되고 있으나 밸류에이션 부담과 환율 변동성은 함께 점검해야 합니다.",
        "positive_factors": [
            "주요 제품 수요가 유지되며 매출 성장의 기반이 이어지고 있습니다.",
            "영업 현금흐름 개선이 투자 여력을 뒷받침하는지 확인할 수 있습니다.",
        ],
        "caution_factors": [
            "현재 밸류에이션에 실적 개선 기대가 선반영됐는지 점검해야 합니다.",
            "환율 변동이 매출과 수익성에 미치는 영향을 함께 살펴야 합니다.",
        ],
        "next_checks": [
            "다음 실적 발표에서 제품군별 매출 성장률과 마진을 확인하세요.",
            "현금흐름 개선이 일회성이 아닌지 분기 추세를 점검하세요.",
        ],
        "counter_view": [
            "현재 가격에 성장 기대가 과도하게 반영되어 추가 상승 여력이 제한적인지 점검하세요.",
            "경쟁 심화로 점유율이나 수익성이 예상보다 빠르게 약화될 가능성을 확인하세요.",
        ],
        "confidence_basis": "매출 성장과 현금흐름 지표는 긍정적이지만 밸류에이션과 환율 변수의 불확실성이 남아 있습니다.",
        "key_risks": [
            {
                "id": "valuation",
                "title": "밸류에이션 부담",
                "level": "MEDIUM",
                "description": "현재 가격이 실적 개선 기대를 상당 부분 반영했는지 확인하세요.",
                "evidence": [
                    "동종 업계 대비 밸류에이션 수준과 이익 성장률의 격차를 비교하세요.",
                    "실적 추정치 상향 없이 주가만 상승하는지 확인하세요.",
                ],
            },
            {
                "id": "competition",
                "title": "경쟁 심화",
                "level": "LOW",
                "description": "주요 제품군의 경쟁 강도와 마진 영향을 추적하세요.",
                "evidence": [
                    "주요 제품군의 점유율과 판촉비 추이를 확인하세요.",
                    "경쟁사 가격 인하가 마진에 미치는 영향을 점검하세요.",
                ],
            },
        ],
    },
    {
        "stance": "WATCH",
        "stance_confidence": "0.64",
        "stance_comment": "비용 효율화 효과를 확인하면서 단기 과열과 규제 일정을 관찰할 단계입니다.",
        "headline": "비용 효율화는 긍정적이나 단기 과열 여부를 확인해야 합니다.",
        "body": "신규 고객 증가와 마진 방어력이 관찰되지만 재고 부담과 규제 리스크가 남아 있습니다.",
        "positive_factors": [
            "비용 효율화가 마진 방어에 기여하는 흐름이 관찰됩니다.",
            "신규 고객 증가가 매출 기반 확대로 이어지는지 확인할 수 있습니다.",
        ],
        "caution_factors": [
            "최근 뉴스 집중도가 단기 가격 과열로 이어졌는지 점검해야 합니다.",
            "재고 부담과 규제 변화가 향후 수익성에 미칠 영향을 살펴야 합니다.",
        ],
        "next_checks": [
            "다음 분기의 재고 회전율과 할인 판매 비중을 확인하세요.",
            "주요 규제 일정과 회사의 대응 계획을 점검하세요.",
        ],
        "counter_view": [
            "비용 효율화와 신규 고객 증가가 예상보다 강해 관찰보다 적극적인 판단이 필요한지 확인하세요.",
            "재고와 규제 우려가 이미 가격에 충분히 반영되어 상승 여력이 커졌는지 점검하세요.",
        ],
        "confidence_basis": "비용과 고객 지표는 개선됐지만 재고와 규제 영향의 확인 자료가 충분하지 않습니다.",
        "key_risks": [
            {
                "id": "news_overheated",
                "title": "단기 뉴스 과열",
                "level": "MEDIUM",
                "description": "최근 뉴스 흐름이 가격에 과도하게 반영되었는지 확인하세요.",
                "evidence": [
                    "뉴스 빈도 증가와 거래량 급증이 같은 시기에 나타났는지 비교하세요.",
                    "실적 변화 없이 단기 주가 변동성만 확대됐는지 확인하세요.",
                ],
            },
            {
                "id": "regulation",
                "title": "규제 리스크",
                "level": "HIGH",
                "description": "사업 모델에 영향을 줄 수 있는 규제 일정을 점검하세요.",
                "evidence": [
                    "예고된 규제 시행 일정과 적용 대상 사업의 매출 비중을 확인하세요.",
                    "회사가 공시한 대응 계획과 예상 비용을 점검하세요.",
                ],
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
            stance_comment=template["stance_comment"],
            headline=template["headline"],
            body=template["body"],
            positive_factors=template["positive_factors"],
            caution_factors=template["caution_factors"],
            next_checks=template["next_checks"],
            counter_view=template["counter_view"],
            confidence_basis=template["confidence_basis"],
            key_risks=[
                ResearchRisk.model_validate(risk)
                for risk in template["key_risks"]
            ],
            created_at=_CREATED_AT,
        )
