from datetime import datetime, timedelta, timezone
from typing import TypedDict

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.catalysts.schema import (
    CatalystEventProjection,
    CatalystEventType,
    CatalystTimelineResponse,
)


class _CatalystTemplate(TypedDict):
    days_from_today: int
    title: str
    event_type: CatalystEventType
    is_estimated: bool


_CATALYST_TEMPLATES: tuple[tuple[_CatalystTemplate, ...], ...] = (
    (
        {
            "days_from_today": 18,
            "title": "분기 실적 발표에서 성장률과 수익성을 확인하세요.",
            "event_type": CatalystEventType.EARNINGS,
            "is_estimated": False,
        },
        {
            "days_from_today": 33,
            "title": "신제품 공개가 수요 확대의 계기가 되는지 점검하세요.",
            "event_type": CatalystEventType.PRODUCT,
            "is_estimated": True,
        },
        {
            "days_from_today": 47,
            "title": "정기 주주총회에서 주요 경영 안건을 확인하세요.",
            "event_type": CatalystEventType.SHAREHOLDER_MEETING,
            "is_estimated": False,
        },
        {
            "days_from_today": 62,
            "title": "배당 기준일 전후의 주주환원 정책을 점검하세요.",
            "event_type": CatalystEventType.DIVIDEND,
            "is_estimated": False,
        },
        {
            "days_from_today": 81,
            "title": "예정된 규제 결정이 사업에 미칠 영향을 확인하세요.",
            "event_type": CatalystEventType.REGULATORY,
            "is_estimated": True,
        },
    ),
    (
        {
            "days_from_today": 12,
            "title": "주요 계약의 갱신 조건과 매출 영향을 확인하세요.",
            "event_type": CatalystEventType.CONTRACT,
            "is_estimated": True,
        },
        {
            "days_from_today": 29,
            "title": "락업 해제 이후 잠재 매도 물량을 점검하세요.",
            "event_type": CatalystEventType.LOCKUP,
            "is_estimated": False,
        },
        {
            "days_from_today": 44,
            "title": "산업 콘퍼런스에서 신규 전략 발표를 확인하세요.",
            "event_type": CatalystEventType.CONFERENCE,
            "is_estimated": False,
        },
        {
            "days_from_today": 58,
            "title": "주요 경제지표 발표가 수요 전망에 미칠 영향을 점검하세요.",
            "event_type": CatalystEventType.ECONOMIC,
            "is_estimated": True,
        },
        {
            "days_from_today": 76,
            "title": "예정된 사업 업데이트에서 핵심 지표 변화를 확인하세요.",
            "event_type": CatalystEventType.OTHER,
            "is_estimated": True,
        },
    ),
)


class CatalystService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)

    def get_timeline(
        self,
        asset_id: int,
        limit: int = 10,
    ) -> CatalystTimelineResponse:
        asset = self.asset_repo.get_by_id(asset_id)
        if asset is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )

        today = datetime.now(timezone.utc).date()
        template = _CATALYST_TEMPLATES[asset.id % len(_CATALYST_TEMPLATES)]
        events = sorted(
            (
                CatalystEventProjection(
                    event_date=today + timedelta(days=item["days_from_today"]),
                    title=item["title"],
                    event_type=item["event_type"],
                    is_estimated=item["is_estimated"],
                )
                for item in template
                if today + timedelta(days=item["days_from_today"]) > today
            ),
            key=lambda event: event.event_date,
        )
        return CatalystTimelineResponse(asset_id=asset.id, events=events[:limit])
