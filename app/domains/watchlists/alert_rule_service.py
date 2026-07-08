from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.watchlists.model import Watchlist
from app.domains.watchlists.repository import (
    WatchlistAlertRuleRepository,
    WatchlistRepository,
)
from app.domains.watchlists.schema import (
    WatchlistAlertRuleTemplateBulkRequest,
    WatchlistAlertRuleTemplateProjection,
)
from app.domains.watchlists.types import WatchlistAlertTemplateType


_TEMPLATE_LABELS: dict[WatchlistAlertTemplateType, str] = {
    WatchlistAlertTemplateType.PRICE_SPIKE: "가격 급변",
    WatchlistAlertTemplateType.NEWS_RISK_HIGH: "뉴스 위험도 상승",
    WatchlistAlertTemplateType.AI_JUDGMENT_CHANGE: "AI 판단 변경",
    WatchlistAlertTemplateType.THEME_OVERHEAT: "테마 과열",
}

_TEMPLATE_CONDITION_DESCRIPTIONS: dict[WatchlistAlertTemplateType, str] = {
    WatchlistAlertTemplateType.PRICE_SPIKE: "일간 변동률 ±3% 이상",
    WatchlistAlertTemplateType.NEWS_RISK_HIGH: "NewsRisk.HIGH",
    WatchlistAlertTemplateType.AI_JUDGMENT_CHANGE: "AiJudgment 상태 전이 발생",
    WatchlistAlertTemplateType.THEME_OVERHEAT: "ThemeHeat.OVERHEATED",
}


class WatchlistAlertRuleService:
    def __init__(self, db: Session) -> None:
        self.watchlist_repo = WatchlistRepository(db)
        self.rule_repo = WatchlistAlertRuleRepository(db)

    def get_template_statuses(
        self,
        watchlist_id: int,
        user_id: int,
    ) -> list[WatchlistAlertRuleTemplateProjection]:
        watchlist = self._get_owned_watchlist(watchlist_id, user_id)
        return self._build_template_statuses(watchlist.id)

    def apply_templates(
        self,
        watchlist_id: int,
        user_id: int,
        data: WatchlistAlertRuleTemplateBulkRequest,
    ) -> list[WatchlistAlertRuleTemplateProjection]:
        watchlist = self._get_owned_watchlist(watchlist_id, user_id)
        validated_templates = [
            (self._validate_template_type(template.template_type), template.is_active)
            for template in data.templates
        ]
        for template_type, is_active in validated_templates:
            self.rule_repo.upsert_template(
                watchlist.id,
                template_type.value,
                is_active,
            )
        return self._build_template_statuses(watchlist.id)

    def _get_owned_watchlist(self, watchlist_id: int, user_id: int) -> Watchlist:
        watchlist = self.watchlist_repo.get_by_id(watchlist_id)
        if watchlist is None:
            raise AppException(
                status_code=404,
                detail="관심 목록을 찾을 수 없습니다.",
                error_code=ErrorCode.WATCHLIST_NOT_FOUND,
            )
        if watchlist.user_id != user_id:
            raise AppException(
                status_code=403,
                detail="관심 목록 접근 권한이 없습니다.",
                error_code=ErrorCode.WATCHLIST_FORBIDDEN,
            )
        return watchlist

    def _build_template_statuses(
        self,
        watchlist_id: int,
    ) -> list[WatchlistAlertRuleTemplateProjection]:
        rules_by_template = {
            rule.template_type: rule
            for rule in self.rule_repo.list_by_watchlist(watchlist_id)
        }
        statuses: list[WatchlistAlertRuleTemplateProjection] = []
        for template_type in WatchlistAlertTemplateType:
            rule = rules_by_template.get(template_type.value)
            statuses.append(
                WatchlistAlertRuleTemplateProjection(
                    template_type=template_type.value,
                    label=_TEMPLATE_LABELS[template_type],
                    condition_description=_TEMPLATE_CONDITION_DESCRIPTIONS[
                        template_type
                    ],
                    is_active=rule.is_active if rule is not None else False,
                )
            )
        return statuses

    def _validate_template_type(
        self,
        template_type: str,
    ) -> WatchlistAlertTemplateType:
        try:
            return WatchlistAlertTemplateType(template_type)
        except ValueError as exc:
            raise AppException(
                status_code=422,
                detail="알림 규칙 템플릿 값이 올바르지 않습니다.",
                error_code=ErrorCode.VALIDATION_ERROR,
            ) from exc
