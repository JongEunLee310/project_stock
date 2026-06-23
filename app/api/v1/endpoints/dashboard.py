from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.response import ApiResponse, success
from app.db.session import get_db
from app.domains.dashboard.schema import DashboardSummaryResponse
from app.domains.dashboard.service import DashboardService
from app.domains.users.model import User

router = APIRouter()


@router.get(
    "/summary",
    response_model=ApiResponse[DashboardSummaryResponse],
    summary="Dashboard summary",
    description="Return aggregated counts and weights for the authenticated user's dashboard cards.",
)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[DashboardSummaryResponse]:
    return success(DashboardService(db).get_summary(current_user.id))
