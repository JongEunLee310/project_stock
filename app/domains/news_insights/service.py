from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import NoReturn

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.pagination import decode_datetime_cursor, encode_datetime_cursor
from app.domains.news_insights.briefing import build_briefing
from app.domains.news_insights.clock import utcnow
from app.domains.news_insights.repository import (
    AgentRunRecords,
    CalendarRecord,
    HIGH_IMPORTANCE_MIN,
    MEDIUM_IMPORTANCE_MIN,
    EventDetailRecords,
    EventRecord,
    EvidenceRecord,
    FundFlowOutlookRecords,
    InvestorFlowRecords,
    NewsInsightsRepository,
    SummaryCounts,
    TopicDetailRecords,
    TopicExplanationRecords,
    TopicGraphRecords,
    TopicMapRecords,
    TopicScenarioRecords,
    TopicTrendRecords,
)
from app.domains.news_insights.schema import (
    AffectedSymbol,
    AgentRunsResponse,
    AgentRunStageItem,
    CalendarItem,
    CalendarQuery,
    EventAffectedSymbol,
    EventDetailEvidence,
    EventDetailImportance,
    EventDetailResponse,
    EventImportance,
    EventListItem,
    EventRelatedTopic,
    EventSentiment,
    EventSource,
    EventsQuery,
    AlreadyPricedIn,
    ContradictingEvidenceItem,
    CounterView,
    ExplanationFactorItem,
    ExplanationMeta,
    FundFlowOutlookItem,
    FundFlowOutlookResponse,
    FundFlowScenarioItem,
    FundFlowScenariosResponse,
    InvestorFlowAvailability,
    InvestorFlowItem,
    InvestorFlowsQuery,
    InvestorFlowsResponse,
    NarrativeAlignment,
    OverviewQuery,
    OverviewResponse,
    OverviewSummary,
    SummaryMetric,
    TopicDetailResponse,
    TopicEvidenceItem,
    TopicEvidenceQuery,
    TopicExplanationResponse,
    TopicInsightResponse,
    TopicGraphEdge,
    TopicGraphNode,
    TopicGraphResponse,
    TopicMapEdge,
    TopicMapNode,
    TopicMapQuery,
    TopicMapResponse,
    TopicScores,
    TopicSymbolSensitivityItem,
    TopicSourceDistribution,
    TopicTrendMarker,
    TopicTrendPoint,
    TopicTrendQuery,
    TopicTrendResponse,
)
from app.domains.news_insights.types import (
    AgentRunStatus,
    AgentStage,
    DocumentType,
    EvidenceRole,
    EventType,
    FlowLikelihood,
    FlowDirection,
    FundFlowDirection,
    ImportanceLevel,
    InvestorType,
    LifecycleStatus,
    MarketEventKind,
    ScenarioKind,
    SentimentDirection,
    SymbolRelationship,
    TopicCategory,
    ValuationBurden,
)


@dataclass(frozen=True)
class EventsResult:
    items: list[EventListItem]
    has_more: bool
    next_cursor: str | None


@dataclass(frozen=True)
class TopicEvidenceResult:
    items: list[TopicEvidenceItem]
    has_more: bool
    next_cursor: str | None


@dataclass
class TrendBucket:
    mention_count: int = 0
    sentiment_total: float = 0.0
    impact_total: float = 0.0
    event_count: int = 0


class NewsInsightsService:
    def __init__(self, db: Session) -> None:
        self.repository = NewsInsightsRepository(db)

    def get_overview(
        self,
        query: OverviewQuery,
        *,
        as_of: datetime | None = None,
    ) -> OverviewResponse:
        generated_at = as_of or utcnow()
        current, previous = self.repository.aggregate_summary_with_change(
            as_of=generated_at,
            window=self._parse_window(query.window),
        )
        briefing = build_briefing(
            self.repository.briefing_candidates(),
            existing_event_ids=self.repository.active_event_ids(),
            generated_at=generated_at,
        )
        return OverviewResponse(
            as_of=generated_at,
            summary=self._summary(current, previous),
            briefing=briefing,
        )

    def list_events(self, query: EventsQuery) -> EventsResult:
        cursor = (
            decode_datetime_cursor(query.cursor) if query.cursor is not None else None
        )
        page = self.repository.list_events(query, cursor)
        items = [self._event_item(record) for record in page.records]
        next_cursor = None
        if page.has_more and page.records:
            last_event = page.records[-1].event
            next_cursor = encode_datetime_cursor(
                last_event.detected_at,
                last_event.id,
            )
        return EventsResult(
            items=items,
            has_more=page.has_more,
            next_cursor=next_cursor,
        )

    def get_calendar(
        self,
        query: CalendarQuery,
        *,
        as_of: datetime | None = None,
    ) -> list[CalendarItem]:
        start = as_of or utcnow()
        return [
            self._calendar_item(record)
            for record in self.repository.list_calendar_events(
                query,
                start=start,
                end=start + self._parse_window(query.window),
            )
        ]

    def get_agent_runs(self) -> AgentRunsResponse:
        records = self.repository.latest_agent_run_records()
        if records is None:
            raise RuntimeError("No agent run is available")
        return self._agent_runs_response(records)

    def get_event_detail(self, event_id: int) -> EventDetailResponse:
        records = self.repository.event_detail_records(event_id)
        if records is None:
            self._raise_event_not_found()
        return self._event_detail_response(records)

    def get_investor_flows(
        self,
        query: InvestorFlowsQuery,
        *,
        as_of: datetime | None = None,
    ) -> InvestorFlowsResponse:
        reference_time = as_of or utcnow()
        records = self.repository.investor_flow_records(
            query,
            as_of=reference_time,
            window=self._parse_window(query.window),
        )
        response_as_of = records.as_of or reference_time
        items = [
            InvestorFlowItem(
                investor_type=InvestorType(item.investor_type),
                net_value=item.net_value,
                direction=self._flow_direction(item.net_value),
                change=self._flow_change(
                    item.net_value,
                    item.previous_net_value,
                ),
            )
            for item in records.aggregates
        ]
        available = bool(items)
        return InvestorFlowsResponse(
            as_of=response_as_of,
            aggregation_windows=(
                list(records.aggregation_windows) if items else None
            ),
            by_investor_type=items,
            narrative_alignment=self._narrative_alignment(records),
            availability=InvestorFlowAvailability(
                available=available,
                fallback=(None if available else self._flow_fallback(records)),
            ),
        )

    def get_fund_flow_outlook(self) -> FundFlowOutlookResponse:
        records = self.repository.latest_fund_flow_outlooks()
        if records is None:
            return FundFlowOutlookResponse(
                as_of=utcnow(),
                analysis_version="unavailable",
                items=[],
            )
        return self._fund_flow_outlook_response(records)

    def get_topic_scenarios(self, topic_id: int) -> FundFlowScenariosResponse:
        if not self.repository.topic_exists(topic_id):
            self._raise_topic_not_found()
        records = self.repository.latest_topic_scenarios(topic_id)
        if records is None:
            raise RuntimeError("No fund flow scenarios are available for the topic")
        expected_kinds = set(ScenarioKind)
        actual_kinds = {
            ScenarioKind(scenario.scenario_kind)
            for scenario in records.scenarios
        }
        if len(records.scenarios) != 3 or actual_kinds != expected_kinds:
            raise RuntimeError("A topic scenario set must contain all three kinds")
        return self._topic_scenarios_response(topic_id, records)

    def get_topic_explanation(self, topic_id: int) -> TopicExplanationResponse:
        if not self.repository.topic_exists(topic_id):
            self._raise_topic_not_found()
        records = self.repository.latest_topic_explanation(topic_id)
        if records is None:
            raise RuntimeError("No explanation is available for the topic")
        return self._topic_explanation_response(records)

    def get_topic_map(
        self,
        query: TopicMapQuery,
        *,
        as_of: datetime | None = None,
    ) -> TopicMapResponse:
        generated_at = as_of or utcnow()
        records = self.repository.topic_map_records(
            start=generated_at - self._parse_window(query.window),
            limit=query.limit,
        )
        return self._topic_map_response(records)

    def get_topic_detail(self, topic_id: int) -> TopicDetailResponse:
        records = self.repository.topic_detail_records(topic_id)
        if records is None:
            self._raise_topic_not_found()
        return self._topic_detail_response(records)

    def get_topic_symbols(self, topic_id: int) -> list[TopicSymbolSensitivityItem]:
        if not self.repository.topic_exists(topic_id):
            self._raise_topic_not_found()
        return [
            TopicSymbolSensitivityItem(
                symbol=item.symbol,
                exposure_score=item.exposure_score,
                impact_direction=SentimentDirection(item.impact_direction),
                relationship=SymbolRelationship(item.relationship),
                valuation_burden=(
                    ValuationBurden(item.valuation_burden)
                    if item.valuation_burden is not None
                    else None
                ),
                portfolio_weight=None,
                current_signal=None,
            )
            for item in self.repository.list_topic_symbol_sensitivities(topic_id)
        ]

    def get_topic_graph(self, topic_id: int) -> TopicGraphResponse:
        if not self.repository.topic_exists(topic_id):
            self._raise_topic_not_found()
        return self._topic_graph_response(
            self.repository.topic_graph_records(topic_id)
        )

    def get_topic_trend(
        self,
        topic_id: int,
        query: TopicTrendQuery,
        *,
        as_of: datetime | None = None,
    ) -> TopicTrendResponse:
        if not self.repository.topic_exists(topic_id):
            self._raise_topic_not_found()
        end = as_of or utcnow()
        window = self._parse_window(query.window)
        interval = self._parse_window(query.interval)
        records = self.repository.topic_trend_records(
            topic_id,
            start=end - window,
            end=end,
        )
        return self._topic_trend_response(
            records,
            start=end - window,
            interval=interval,
        )

    def list_topic_evidence(
        self,
        topic_id: int,
        query: TopicEvidenceQuery,
    ) -> TopicEvidenceResult:
        if not self.repository.topic_exists(topic_id):
            self._raise_topic_not_found()
        cursor = (
            decode_datetime_cursor(query.cursor) if query.cursor is not None else None
        )
        page = self.repository.list_topic_evidence(topic_id, query, cursor)
        items = [self._topic_evidence_item(record) for record in page.records]
        next_cursor = None
        if page.has_more and page.records:
            last = page.records[-1]
            next_cursor = encode_datetime_cursor(
                last.document.published_at,
                last.evidence.id,
            )
        return TopicEvidenceResult(
            items=items,
            has_more=page.has_more,
            next_cursor=next_cursor,
        )

    @staticmethod
    def _parse_window(window: str) -> timedelta:
        value = int(window[:-1])
        return timedelta(hours=value) if window.endswith("h") else timedelta(days=value)

    @staticmethod
    def _raise_topic_not_found() -> NoReturn:
        raise AppException(
            status_code=404,
            detail="뉴스 인사이트 토픽을 찾을 수 없습니다.",
            error_code=ErrorCode.NEWS_INSIGHT_TOPIC_NOT_FOUND,
        )

    @staticmethod
    def _raise_event_not_found() -> NoReturn:
        raise AppException(
            status_code=404,
            detail="뉴스 인사이트 이벤트를 찾을 수 없습니다.",
            error_code=ErrorCode.NEWS_INSIGHT_EVENT_NOT_FOUND,
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _metric(current: int, previous: int) -> SummaryMetric:
        return SummaryMetric(count=current, change=current - previous)

    @classmethod
    def _summary(
        cls,
        current: SummaryCounts,
        previous: SummaryCounts,
    ) -> OverviewSummary:
        return OverviewSummary(
            high_importance_events=cls._metric(
                current.high_importance_events,
                previous.high_importance_events,
            ),
            sentiment_shifts=cls._metric(
                current.sentiment_shifts,
                previous.sentiment_shifts,
            ),
            active_topic_clusters=cls._metric(
                current.active_topic_clusters,
                previous.active_topic_clusters,
            ),
            fund_flow_signals=cls._metric(
                current.fund_flow_signals,
                previous.fund_flow_signals,
            ),
        )

    @staticmethod
    def _importance_level(score: float) -> ImportanceLevel:
        if score >= HIGH_IMPORTANCE_MIN:
            return ImportanceLevel.HIGH
        if score >= MEDIUM_IMPORTANCE_MIN:
            return ImportanceLevel.MEDIUM
        return ImportanceLevel.LOW

    @staticmethod
    def _flow_direction(net_value: Decimal) -> FlowDirection:
        if net_value > 0:
            return FlowDirection.BUY
        if net_value < 0:
            return FlowDirection.SELL
        return FlowDirection.NEUTRAL

    @staticmethod
    def _flow_change(current: Decimal, previous: Decimal | None) -> float:
        if previous is None or previous == 0:
            return 0.0
        return float((current - previous) / abs(previous) * Decimal("100"))

    @classmethod
    def _narrative_alignment(
        cls,
        records: InvestorFlowRecords,
    ) -> NarrativeAlignment:
        if not records.aggregates:
            return NarrativeAlignment(
                aligned=False,
                note="투자자 유형별 수급 데이터가 없어 뉴스 내러티브와 비교할 수 없습니다.",
            )
        if records.narrative_sentiment_score is None:
            return NarrativeAlignment(
                aligned=False,
                note="연결된 뉴스 내러티브가 없어 수급 방향 정렬 여부를 판단할 수 없습니다.",
            )
        flow_direction = cls._flow_direction(
            sum(
                (item.net_value for item in records.aggregates),
                start=Decimal("0"),
            )
        )
        sentiment_score = records.narrative_sentiment_score
        narrative_direction = (
            FlowDirection.BUY
            if sentiment_score > 0.5
            else FlowDirection.SELL
            if sentiment_score < 0.5
            else FlowDirection.NEUTRAL
        )
        aligned = flow_direction == narrative_direction
        relation = "일치" if aligned else "불일치"
        return NarrativeAlignment(
            aligned=aligned,
            note=f"뉴스 감성과 투자자 순수급 방향이 {relation}합니다.",
        )

    @staticmethod
    def _flow_fallback(records: InvestorFlowRecords) -> str:
        if records.fallback_source_kinds:
            source_labels = {
                "ETF_FLOW": "ETF 수급",
                "VOLUME_PROXY": "거래량",
            }
            labels = [
                source_labels.get(source_kind, source_kind)
                for source_kind in records.fallback_source_kinds
            ]
            return f"투자자 유형별 데이터 대신 {'·'.join(labels)} 지표를 확인하세요."
        return "투자자 유형별 데이터가 없어 ETF 수급·거래량 대체 지표를 확인하세요."

    @classmethod
    def _fund_flow_outlook_response(
        cls,
        records: FundFlowOutlookRecords,
    ) -> FundFlowOutlookResponse:
        return FundFlowOutlookResponse(
            as_of=cls._as_utc(records.as_of),
            analysis_version=records.analysis_version,
            items=[
                FundFlowOutlookItem(
                    sector=item.sector,
                    direction=FundFlowDirection(item.direction),
                    likelihood=FlowLikelihood(item.likelihood),
                    estimated_range=item.estimated_range,
                    horizon=item.horizon,
                    confidence=item.confidence,
                    key_assumptions=item.key_assumptions,
                    risk_factors=item.risk_factors,
                )
                for item in records.items
            ],
        )

    @classmethod
    def _topic_scenarios_response(
        cls,
        topic_id: int,
        records: TopicScenarioRecords,
    ) -> FundFlowScenariosResponse:
        order = {kind: index for index, kind in enumerate(ScenarioKind)}
        scenarios = sorted(
            records.scenarios,
            key=lambda item: order[ScenarioKind(item.scenario_kind)],
        )
        return FundFlowScenariosResponse(
            topic_id=topic_id,
            analysis_version=records.analysis_version,
            as_of=cls._as_utc(records.as_of),
            scenarios=[
                FundFlowScenarioItem(
                    scenario_kind=ScenarioKind(item.scenario_kind),
                    weight=item.weight,
                    expected_flow_direction=FundFlowDirection(
                        item.expected_flow_direction
                    ),
                    key_assumptions=item.key_assumptions,
                    benefiting_sectors=item.benefiting_sectors,
                    risk_sectors=item.risk_sectors,
                    related_symbols=item.related_symbols,
                    invalidation_conditions=item.invalidation_conditions,
                )
                for item in scenarios
            ],
        )

    @classmethod
    def _topic_explanation_response(
        cls,
        records: TopicExplanationRecords,
    ) -> TopicExplanationResponse:
        explanation = records.explanation
        return TopicExplanationResponse(
            factors=[
                ExplanationFactorItem(
                    label=factor.label,
                    contribution_ratio=factor.contribution_ratio,
                )
                for factor in records.factors
            ],
            meta=ExplanationMeta(
                analysis_version=explanation.analysis_version,
                data_coverage=explanation.data_coverage,
                last_updated=cls._as_utc(explanation.last_updated),
                missing_data=explanation.missing_data,
                counter_argument_count=len(records.counter_arguments),
                confidence=explanation.confidence,
                limitations=explanation.limitations,
            ),
            counter_view=CounterView(
                counter_arguments=list(records.counter_arguments),
                invalidation_conditions=list(records.invalidation_conditions),
                already_priced_in=AlreadyPricedIn(
                    likely=explanation.already_priced_in,
                    note=explanation.already_priced_in_note,
                ),
                contradicting_evidence=[
                    ContradictingEvidenceItem(
                        event_id=record.event.id,
                        document_id=record.document.id,
                        title=record.document.title,
                        source=record.document.source_name,
                        published_at=cls._as_utc(record.document.published_at),
                    )
                    for record in records.contradicting_evidence
                ],
            ),
        )

    @classmethod
    def _event_item(cls, record: EventRecord) -> EventListItem:
        event = record.event
        document = record.document
        return EventListItem(
            id=event.id,
            event_type=EventType(event.event_type),
            document_type=(
                DocumentType(document.document_type) if document is not None else None
            ),
            symbol=event.primary_symbol,
            title=event.title,
            summary=event.summary,
            importance=EventImportance(
                level=cls._importance_level(event.importance_score),
                score=event.importance_score,
            ),
            sentiment=EventSentiment(
                direction=SentimentDirection(event.sentiment_direction),
                score=event.sentiment_score,
            ),
            source=(
                EventSource(
                    name=document.source_name,
                    reliability=document.source_reliability,
                )
                if document is not None
                else None
            ),
            published_at=(
                document.published_at
                if document is not None
                else event.occurred_at or event.detected_at
            ),
            evidence_count=record.evidence_count,
            topic_ids=list(record.topic_ids),
        )

    @classmethod
    def _calendar_item(cls, record: CalendarRecord) -> CalendarItem:
        return CalendarItem(
            scheduled_at=cls._as_utc(record.event.scheduled_at),
            event_kind=MarketEventKind(record.event.event_kind),
            title=record.event.title,
            symbol=record.event.symbol,
            market=record.event.market,
            importance=record.event.importance_score,
            related_topic_ids=list(record.related_topic_ids),
        )

    @classmethod
    def _agent_runs_response(cls, records: AgentRunRecords) -> AgentRunsResponse:
        run = records.run
        stages_by_name = {stage.stage: stage for stage in records.stages}
        stages = [
            AgentRunStageItem(
                name=stage_name,
                status=AgentRunStatus(stage.status),
                delayed=stage.delayed,
            )
            for stage_name in AgentStage
            if (stage := stages_by_name.get(stage_name.value)) is not None
        ]
        return AgentRunsResponse(
            last_processed_at=cls._as_utc(run.finished_at or run.started_at),
            processed_documents=run.processed_documents,
            extracted_events=run.extracted_events,
            active_topics=run.active_topics,
            stages=stages,
            analysis_version=run.analysis_version,
            has_delay=(
                run.status == AgentRunStatus.DELAYED.value
                or any(stage.delayed for stage in records.stages)
            ),
        )

    @classmethod
    def _event_detail_response(
        cls,
        records: EventDetailRecords,
    ) -> EventDetailResponse:
        event = records.event
        evidence = [
            EventDetailEvidence(
                document_id=record.document.id,
                document_type=DocumentType(record.document.document_type),
                source=record.document.source_name,
                title=record.document.title,
                published_at=cls._as_utc(record.document.published_at),
                evidence_role=EvidenceRole(record.evidence.evidence_role),
            )
            for record in records.evidence
        ]
        exposure_score = max(
            (
                record.evidence.relevance_score
                for record in records.evidence
            ),
            default=event.importance_score,
        )
        affected_symbols = []
        if event.primary_symbol is not None:
            affected_symbols.append(
                EventAffectedSymbol(
                    symbol=event.primary_symbol,
                    direction=SentimentDirection(event.sentiment_direction),
                    exposure_score=exposure_score,
                    reason=event.summary,
                )
            )
        return EventDetailResponse(
            event_type=EventType(event.event_type),
            title=event.title,
            summary=event.summary,
            importance=EventDetailImportance(
                score=event.importance_score,
                level=cls._importance_level(event.importance_score),
                explanation=event.summary,
            ),
            sentiment=EventSentiment(
                direction=SentimentDirection(event.sentiment_direction),
                score=event.sentiment_score,
            ),
            affected_symbols=affected_symbols,
            evidence=evidence,
            related_topics=[
                EventRelatedTopic(topic_id=topic.id, title=topic.title)
                for topic in records.topics
            ],
        )

    @staticmethod
    def _topic_node_id(topic_id: int) -> str:
        return f"topic:{topic_id}"

    @staticmethod
    def _keyword_node_id(keyword_id: int) -> str:
        return f"keyword:{keyword_id}"

    @classmethod
    def _topic_map_response(cls, records: TopicMapRecords) -> TopicMapResponse:
        topic_nodes = [
            TopicMapNode(
                id=cls._topic_node_id(topic.id),
                label=topic.title,
                type="TOPIC",
                mention_count=topic.mention_count,
                momentum_score=topic.momentum_score,
                sentiment_score=topic.sentiment_score,
                category=(
                    TopicCategory(topic.category) if topic.category is not None else None
                ),
            )
            for topic in records.topics
        ]
        keyword_nodes = [
            TopicMapNode(
                id=cls._keyword_node_id(keyword.id),
                label=keyword.keyword,
                type="KEYWORD",
                mention_count=keyword.mention_count,
                momentum_score=keyword.weight,
                sentiment_score=keyword.sentiment_score,
                category=(
                    TopicCategory(keyword.category)
                    if keyword.category is not None
                    else None
                ),
            )
            for keyword in records.keywords
        ]
        keyword_ids = {
            (keyword.topic_id, keyword.keyword): cls._keyword_node_id(keyword.id)
            for keyword in records.keywords
        }
        edges = [
            TopicMapEdge(
                source=keyword_ids[(relation.topic_id, relation.source_keyword)],
                target=keyword_ids[(relation.topic_id, relation.target_keyword)],
                strength=relation.strength,
                cooccurrence_count=relation.cooccurrence_count,
            )
            for relation in records.relations
            if (relation.topic_id, relation.source_keyword) in keyword_ids
            and (relation.topic_id, relation.target_keyword) in keyword_ids
        ]
        return TopicMapResponse(nodes=[*topic_nodes, *keyword_nodes], edges=edges)

    @classmethod
    def _topic_graph_response(cls, records: TopicGraphRecords) -> TopicGraphResponse:
        node_ids = {
            keyword.keyword: cls._keyword_node_id(keyword.id)
            for keyword in records.keywords
        }
        return TopicGraphResponse(
            nodes=[
                TopicGraphNode(
                    id=cls._keyword_node_id(keyword.id),
                    label=keyword.keyword,
                    type="KEYWORD",
                    mention_count=keyword.mention_count,
                    sentiment_score=keyword.sentiment_score,
                    related_event_ids=list(records.related_event_ids),
                    related_symbols=list(records.related_symbols),
                )
                for keyword in records.keywords
            ],
            edges=[
                TopicGraphEdge(
                    source=node_ids[relation.source_keyword],
                    target=node_ids[relation.target_keyword],
                    strength=relation.strength,
                    cooccurrence_count=relation.cooccurrence_count,
                )
                for relation in records.relations
                if relation.source_keyword in node_ids
                and relation.target_keyword in node_ids
            ],
        )

    @classmethod
    def _topic_detail_response(
        cls,
        records: TopicDetailRecords,
    ) -> TopicDetailResponse:
        topic = records.topic
        insight = records.insight
        affected_by_symbol: dict[str, AffectedSymbol] = {}
        for record in records.affected_events:
            symbol = record.event.primary_symbol
            if symbol is None:
                continue
            candidate = AffectedSymbol(
                symbol=symbol,
                exposure_score=record.exposure_score,
                impact_direction=SentimentDirection(
                    record.event.sentiment_direction
                ),
                relationship=SymbolRelationship.DIRECT,
            )
            existing = affected_by_symbol.get(symbol)
            if existing is None or candidate.exposure_score > existing.exposure_score:
                affected_by_symbol[symbol] = candidate
        return TopicDetailResponse(
            title=topic.title,
            tags=[keyword.keyword for keyword in records.keywords],
            lifecycle=LifecycleStatus(topic.lifecycle_status),
            scores=TopicScores(
                impact=topic.impact_score,
                sentiment=topic.sentiment_score,
                confidence=topic.confidence_score,
                momentum=topic.momentum_score,
            ),
            affected_symbols=sorted(
                affected_by_symbol.values(),
                key=lambda item: (-item.exposure_score, item.symbol),
            ),
            insight=TopicInsightResponse(
                summary=insight.executive_summary,
                why_it_matters=insight.why_it_matters,
                key_evidence=insight.key_evidence,
                risk_points=insight.risk_points,
                counter_arguments=insight.counter_arguments,
            ),
            version=insight.version,
            updated_at=cls._as_utc(insight.created_at),
        )

    @classmethod
    def _topic_trend_response(
        cls,
        records: TopicTrendRecords,
        *,
        start: datetime,
        interval: timedelta,
    ) -> TopicTrendResponse:
        evidence_counts: dict[int, int] = {}
        source_counts: dict[DocumentType, int] = {}
        for record in records.evidence:
            event_id = record.event.id
            evidence_counts[event_id] = evidence_counts.get(event_id, 0) + 1
            source_type = DocumentType(record.document.document_type)
            source_counts[source_type] = source_counts.get(source_type, 0) + 1

        buckets: dict[int, TrendBucket] = {}
        for event in records.events:
            elapsed = cls._as_utc(event.detected_at) - cls._as_utc(start)
            index = int(elapsed.total_seconds() // interval.total_seconds())
            bucket = buckets.setdefault(index, TrendBucket())
            bucket.mention_count += max(evidence_counts.get(event.id, 0), 1)
            bucket.sentiment_total += event.sentiment_score
            bucket.impact_total += event.importance_score
            bucket.event_count += 1

        points = [
            TopicTrendPoint(
                timestamp=cls._as_utc(start) + interval * index,
                mention_count=bucket.mention_count,
                sentiment_score=bucket.sentiment_total / bucket.event_count,
                impact_score=bucket.impact_total / bucket.event_count,
            )
            for index, bucket in sorted(buckets.items())
        ]
        markers = [
            TopicTrendMarker(
                timestamp=cls._as_utc(event.detected_at),
                label=event.title,
                event_id=event.id,
            )
            for event in records.events
        ]
        total_sources = sum(source_counts.values())
        distribution = [
            TopicSourceDistribution(
                source_type=source_type,
                count=count,
                share=count / total_sources,
            )
            for source_type, count in sorted(
                source_counts.items(), key=lambda item: item[0].value
            )
        ]
        return TopicTrendResponse(
            points=points,
            markers=markers,
            source_distribution=distribution,
        )

    @classmethod
    def _topic_evidence_item(cls, record: EvidenceRecord) -> TopicEvidenceItem:
        return TopicEvidenceItem(
            event_id=record.event.id,
            document_id=record.document.id,
            evidence_role=EvidenceRole(record.evidence.evidence_role),
            document_type=DocumentType(record.document.document_type),
            symbol=record.event.primary_symbol,
            title=record.document.title,
            summary=record.event.summary,
            direction=SentimentDirection(record.event.sentiment_direction),
            relevance_score=record.evidence.relevance_score,
            source=record.document.source_name,
            published_at=cls._as_utc(record.document.published_at),
        )
