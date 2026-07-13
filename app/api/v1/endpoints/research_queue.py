from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.pagination import PaginationParams
from app.core.response import ApiResponse, PageMeta
from app.db.session import get_db
from app.domains.research_queue.schema import (
    ResearchQueueData,
    ResearchQueueFilter,
)
from app.domains.research_queue.service import ResearchQueueService
from app.domains.users.model import User

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[ResearchQueueData],
    summary="List research queue",
    description="Return paginated active assets with derived research metadata and unfiltered summary counts.",
)
def list_research_queue(
    pagination: Annotated[PaginationParams, Depends()],
    filter: ResearchQueueFilter | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[ResearchQueueData]:
    items, summary, total = ResearchQueueService(db).list_queue(
        filter=filter.value if filter is not None else None,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return ApiResponse(
        data=ResearchQueueData(summary=summary, items=items),
        meta=PageMeta(page=pagination.page, size=pagination.size, total=total),
    )
