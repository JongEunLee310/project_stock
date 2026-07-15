from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.pagination import PaginationParams, SortParams, sort_param
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.alert_rules.schema import (
    AlertRuleCreate,
    AlertRuleProjection,
    AlertRuleTemplateProjection,
    AlertRuleUpdate,
)
from app.domains.alert_rules.service import AlertRuleService
from app.domains.alert_rules.types import AlertTargetType
from app.domains.users.model import User

router = APIRouter()
alert_rule_sort = sort_param(
    allowed_fields={"created_at", "name"},
    default="-created_at",
)


@router.get(
    "/templates",
    response_model=ApiResponse[list[AlertRuleTemplateProjection]],
    summary="List alert rule templates",
)
def list_alert_rule_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[AlertRuleTemplateProjection]]:
    return success(AlertRuleService(db).list_templates())


@router.get(
    "",
    response_model=ApiResponse[list[AlertRuleProjection]],
    summary="List alert rules",
)
def list_alert_rules(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends(alert_rule_sort)],
    status: Literal["ACTIVE", "PAUSED"] | None = None,
    target_type: AlertTargetType | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[AlertRuleProjection]]:
    service = AlertRuleService(db)
    items = service.list_rules(
        current_user.id,
        status=status,
        target_type=target_type,
        offset=pagination.offset,
        limit=pagination.limit,
        sort=sort.value,
    )
    total = service.count_rules(
        current_user.id,
        status=status,
        target_type=target_type,
    )
    return paginated(
        items,
        page=pagination.page,
        size=pagination.size,
        total=total,
    )


@router.post(
    "",
    response_model=ApiResponse[AlertRuleProjection],
    status_code=201,
    summary="Create alert rule",
)
def create_alert_rule(
    data: AlertRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[AlertRuleProjection]:
    return success(AlertRuleService(db).create_rule(current_user.id, data))


@router.patch(
    "/{alert_rule_id}",
    response_model=ApiResponse[AlertRuleProjection],
    summary="Update alert rule",
)
def update_alert_rule(
    alert_rule_id: int,
    data: AlertRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[AlertRuleProjection]:
    return success(
        AlertRuleService(db).update_rule(alert_rule_id, current_user.id, data)
    )


@router.post(
    "/{alert_rule_id}/pause",
    response_model=ApiResponse[AlertRuleProjection],
    summary="Pause alert rule",
)
def pause_alert_rule(
    alert_rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[AlertRuleProjection]:
    return success(AlertRuleService(db).pause_rule(alert_rule_id, current_user.id))


@router.post(
    "/{alert_rule_id}/resume",
    response_model=ApiResponse[AlertRuleProjection],
    summary="Resume alert rule",
)
def resume_alert_rule(
    alert_rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[AlertRuleProjection]:
    return success(AlertRuleService(db).resume_rule(alert_rule_id, current_user.id))


@router.delete(
    "/{alert_rule_id}",
    status_code=204,
    summary="Delete alert rule",
)
def delete_alert_rule(
    alert_rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    AlertRuleService(db).delete_rule(alert_rule_id, current_user.id)
    return Response(status_code=204)
