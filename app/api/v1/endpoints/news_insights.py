from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.response import ApiResponse, cursor_paginated, success
from app.db.session import get_db
from app.domains.news_insights.schema import (
    EventListItem,
    EventsQuery,
    OverviewQuery,
    OverviewResponse,
    TopicMapQuery,
    TopicMapResponse,
)
from app.domains.news_insights.service import NewsInsightsService
from app.domains.news_insights.types import (
    EventType,
    ImportanceLevel,
    SentimentDirection,
)
from app.domains.users.model import User

router = APIRouter()


@router.get(
    "/overview",
    response_model=ApiResponse[OverviewResponse],
    summary="Get news insights overview",
    description="Return the top summary metrics and evidence-grounded briefing.",
)
def get_news_insights_overview(
    market: str | None = None,
    window: Annotated[str, Query(pattern=r"^[1-9]\d*[hd]$")] = "24h",
    portfolio_id: Annotated[int | None, Query(ge=1)] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[OverviewResponse]:
    query = OverviewQuery(
        market=market,
        window=window,
        portfolio_id=portfolio_id,
    )
    return success(NewsInsightsService(db).get_overview(query))


@router.get(
    "/events",
    response_model=ApiResponse[list[EventListItem]],
    summary="List news insight events",
    description="Return an event-centered feed using opaque cursor pagination.",
)
def list_news_insight_events(
    types: Annotated[list[EventType] | None, Query()] = None,
    symbols: Annotated[list[str] | None, Query()] = None,
    importance: Annotated[list[ImportanceLevel] | None, Query()] = None,
    sentiment: Annotated[list[SentimentDirection] | None, Query()] = None,
    market: str | None = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[EventListItem]]:
    query = EventsQuery(
        types=types or [],
        symbols=symbols or [],
        importance=importance or [],
        sentiment=sentiment or [],
        market=market,
        from_=from_,
        to=to,
        cursor=cursor,
        limit=limit,
    )
    result = NewsInsightsService(db).list_events(query)
    return cursor_paginated(
        result.items,
        limit=limit,
        has_more=result.has_more,
        next_cursor=result.next_cursor,
    )


@router.get(
    "/topics/map",
    response_model=ApiResponse[TopicMapResponse],
    summary="Get news insight topic map",
    description="Return precomputed topic and keyword nodes with relation edges.",
)
def get_news_insight_topic_map(
    window: Annotated[str, Query(pattern=r"^[1-9]\d*[hd]$")] = "7d",
    market: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[TopicMapResponse]:
    query = TopicMapQuery(window=window, market=market, limit=limit)
    return success(NewsInsightsService(db).get_topic_map(query))
