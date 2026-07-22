from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.response import ApiResponse, cursor_paginated, success
from app.db.session import get_db
from app.domains.news_insights.schema import (
    AgentRunsResponse,
    CalendarItem,
    CalendarQuery,
    EventDetailResponse,
    EventListItem,
    EventsQuery,
    FundFlowOutlookResponse,
    FundFlowScenariosResponse,
    InvestorFlowsQuery,
    InvestorFlowsResponse,
    OverviewQuery,
    OverviewResponse,
    TopicDetailResponse,
    TopicEvidenceItem,
    TopicEvidenceQuery,
    TopicExplanationResponse,
    TopicGraphResponse,
    TopicMapQuery,
    TopicMapResponse,
    TopicSymbolSensitivityItem,
    TopicTrendQuery,
    TopicTrendResponse,
)
from app.domains.news_insights.service import NewsInsightsService
from app.domains.news_insights.types import (
    DocumentType,
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
    "/investor-flows",
    response_model=ApiResponse[InvestorFlowsResponse],
    summary="Get investor flows",
    description="Return aggregated investor flows and news narrative alignment.",
)
def get_news_insight_investor_flows(
    market: Annotated[str, Query(min_length=1)],
    window: Annotated[str, Query(pattern=r"^[1-9]\d*[hd]$")],
    topic_id: Annotated[int | None, Query(ge=1)] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[InvestorFlowsResponse]:
    query = InvestorFlowsQuery(
        market=market,
        window=window,
        topic_id=topic_id,
    )
    return success(NewsInsightsService(db).get_investor_flows(query))


@router.get(
    "/fund-flow-outlook",
    response_model=ApiResponse[FundFlowOutlookResponse],
    summary="Get fund flow outlook",
    description="Return labeled sector fund-flow ranges, assumptions, and risks.",
)
def get_news_insight_fund_flow_outlook(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[FundFlowOutlookResponse]:
    return success(NewsInsightsService(db).get_fund_flow_outlook())


@router.get(
    "/calendar",
    response_model=ApiResponse[list[CalendarItem]],
    summary="List news insight calendar events",
    description="Return upcoming market events with their related topic IDs.",
)
def list_news_insight_calendar(
    window: Annotated[str, Query(pattern=r"^[1-9]\d*[hd]$")],
    market: Annotated[str, Query(min_length=1)],
    topic_id: Annotated[int | None, Query(ge=1)] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[CalendarItem]]:
    query = CalendarQuery(window=window, market=market, topic_id=topic_id)
    return success(NewsInsightsService(db).get_calendar(query))


@router.get(
    "/agent-runs",
    response_model=ApiResponse[AgentRunsResponse],
    summary="Get latest news insight agent run",
    description="Return verifiable processing counts and stage statuses only.",
)
def get_news_insight_agent_runs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[AgentRunsResponse]:
    return success(NewsInsightsService(db).get_agent_runs())


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
    "/events/{event_id}",
    response_model=ApiResponse[EventDetailResponse],
    summary="Get news insight event detail",
    description="Return an event with affected symbols, evidence, and related topics.",
)
def get_news_insight_event_detail(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[EventDetailResponse]:
    return success(NewsInsightsService(db).get_event_detail(event_id))


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


@router.get(
    "/topics/{topic_id}",
    response_model=ApiResponse[TopicDetailResponse],
    summary="Get news insight topic detail",
    description="Return a topic with its latest versioned insight.",
)
def get_news_insight_topic_detail(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[TopicDetailResponse]:
    return success(NewsInsightsService(db).get_topic_detail(topic_id))


@router.get(
    "/topics/{topic_id}/scenarios",
    response_model=ApiResponse[FundFlowScenariosResponse],
    summary="Get topic fund flow scenarios",
    description="Return optimistic, base, and conservative weighted scenarios.",
)
def get_news_insight_topic_scenarios(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[FundFlowScenariosResponse]:
    return success(NewsInsightsService(db).get_topic_scenarios(topic_id))


@router.get(
    "/topics/{topic_id}/explanation",
    response_model=ApiResponse[TopicExplanationResponse],
    summary="Get topic insight explanation",
    description="Return contribution factors and a required counter view.",
)
def get_news_insight_topic_explanation(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[TopicExplanationResponse]:
    return success(NewsInsightsService(db).get_topic_explanation(topic_id))


@router.get(
    "/topics/{topic_id}/symbols",
    response_model=ApiResponse[list[TopicSymbolSensitivityItem]],
    summary="List news insight topic symbol sensitivities",
    description="Return symbol exposure and impact direction for a topic.",
)
def list_news_insight_topic_symbols(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[TopicSymbolSensitivityItem]]:
    return success(NewsInsightsService(db).get_topic_symbols(topic_id))


@router.get(
    "/topics/{topic_id}/graph",
    response_model=ApiResponse[TopicGraphResponse],
    summary="Get news insight topic keyword graph",
    description="Return topic-scoped keyword nodes, references, and relation edges.",
)
def get_news_insight_topic_graph(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[TopicGraphResponse]:
    return success(NewsInsightsService(db).get_topic_graph(topic_id))


@router.get(
    "/topics/{topic_id}/trend",
    response_model=ApiResponse[TopicTrendResponse],
    summary="Get news insight topic trend",
    description="Return interval aggregates, event markers, and source distribution.",
)
def get_news_insight_topic_trend(
    topic_id: int,
    window: Annotated[str, Query(pattern=r"^[1-9]\d*[hd]$")] = "7d",
    interval: Annotated[str, Query(pattern=r"^[1-9]\d*[hd]$")] = "1d",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[TopicTrendResponse]:
    query = TopicTrendQuery(window=window, interval=interval)
    return success(NewsInsightsService(db).get_topic_trend(topic_id, query))


@router.get(
    "/topics/{topic_id}/evidence",
    response_model=ApiResponse[list[TopicEvidenceItem]],
    summary="List news insight topic evidence",
    description="Return topic evidence using opaque cursor pagination.",
)
def list_news_insight_topic_evidence(
    topic_id: int,
    types: Annotated[list[DocumentType] | None, Query()] = None,
    direction: SentimentDirection | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[TopicEvidenceItem]]:
    query = TopicEvidenceQuery(
        types=types or [],
        direction=direction,
        cursor=cursor,
        limit=limit,
    )
    result = NewsInsightsService(db).list_topic_evidence(topic_id, query)
    return cursor_paginated(
        result.items,
        limit=limit,
        has_more=result.has_more,
        next_cursor=result.next_cursor,
    )
