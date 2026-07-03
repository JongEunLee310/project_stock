from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.response import ApiResponse, success
from app.db.session import get_db
from app.domains.llm_analysis.repository import LLMAnalysisRunRepository
from app.domains.llm_analysis.schema import (
    LLMAnalysisRunDetail,
    LLMAnalysisRunSummary,
)
from app.domains.users.model import User

router = APIRouter()


@router.get(
    "/runs",
    response_model=ApiResponse[list[LLMAnalysisRunSummary]],
    summary="List LLM analysis runs",
    description="Return recent LLM analysis runs owned by the authenticated user.",
)
def list_llm_analysis_runs(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[LLMAnalysisRunSummary]]:
    runs = LLMAnalysisRunRepository(db).list_by_user(current_user.id, limit=limit)
    return success([LLMAnalysisRunSummary.model_validate(run) for run in runs])


@router.get(
    "/runs/{run_id}",
    response_model=ApiResponse[LLMAnalysisRunDetail],
    summary="Get LLM analysis run",
    description="Return one LLM analysis run owned by the authenticated user.",
)
def get_llm_analysis_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[LLMAnalysisRunDetail]:
    run = LLMAnalysisRunRepository(db).get_by_id_for_user(run_id, current_user.id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM analysis run not found",
        )
    return success(LLMAnalysisRunDetail.model_validate(run))
