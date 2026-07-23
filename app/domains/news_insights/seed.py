from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domains.news_insights.model import (
    AgentRun,
    AgentRunStage,
    EventEvidence,
    ExplanationFactor,
    ExtractedEvent,
    FundFlowOutlook,
    FundFlowScenario,
    InvestorFlow,
    KeywordRelation,
    MarketEvent,
    MarketEventTopic,
    SourceDocument,
    TopicCluster,
    TopicExplanation,
    TopicInsight,
    TopicKeyword,
    TopicSymbolSensitivity,
)
from app.domains.news_insights.types import (
    AgentRunStatus,
    AgentStage,
    DocumentType,
    EventStatus,
    EventType,
    EvidenceRole,
    FlowLikelihood,
    FlowDirection,
    FundFlowDirection,
    InvestorType,
    LifecycleStatus,
    MarketEventKind,
    ProcessingStatus,
    ScenarioKind,
    SentimentDirection,
    SymbolRelationship,
    TopicCategory,
    ValuationBurden,
)


@dataclass(frozen=True)
class SeededNewsInsights:
    documents: tuple[SourceDocument, ...]
    events: tuple[ExtractedEvent, ...]
    evidence: tuple[EventEvidence, ...]
    topics: tuple[TopicCluster, ...]
    keywords: tuple[TopicKeyword, ...]
    relations: tuple[KeywordRelation, ...]
    insights: tuple[TopicInsight, ...]
    investor_flows: tuple[InvestorFlow, ...]
    symbol_sensitivities: tuple[TopicSymbolSensitivity, ...]
    market_events: tuple[MarketEvent, ...]
    market_event_topics: tuple[MarketEventTopic, ...]
    agent_runs: tuple[AgentRun, ...]
    agent_run_stages: tuple[AgentRunStage, ...]
    fund_flow_outlooks: tuple[FundFlowOutlook, ...]
    fund_flow_scenarios: tuple[FundFlowScenario, ...]
    topic_explanations: tuple[TopicExplanation, ...]
    explanation_factors: tuple[ExplanationFactor, ...]


def seed_mock_news_insights(
    session: Session,
    *,
    now: datetime | None = None,
) -> SeededNewsInsights:
    """Insert a small connected dataset for contract demonstrations and tests."""
    seeded_at = now or datetime.now(UTC)
    document = SourceDocument(
        document_type=DocumentType.DISCLOSURE.value,
        source_name="DART",
        source_url="https://dart.fss.or.kr/mock/202607210001",
        external_id="202607210001",
        title="반도체 장기 공급계약 체결",
        raw_content="회사는 글로벌 고객사와 장기 공급계약을 체결했다.",
        normalized_content="글로벌 고객사와 반도체 장기 공급계약 체결",
        language="ko",
        published_at=seeded_at - timedelta(hours=2),
        collected_at=seeded_at - timedelta(hours=1, minutes=55),
        content_hash="mock-news-insight-document-00000000000000000000000000000001",
        source_reliability=0.98,
        processing_status=ProcessingStatus.EXTRACTED.value,
    )
    contradicting_document = SourceDocument(
        document_type=DocumentType.ANALYST_REPORT.value,
        source_name="한국투자리서치",
        source_url="https://example.com/mock/semiconductor-demand-risk",
        external_id="MOCK-20260721-RISK",
        title="반도체 수요 회복 속도 점검",
        raw_content="재고 조정이 길어지면 신규 계약의 단기 실적 기여는 제한될 수 있다.",
        normalized_content="재고 조정 장기화 시 단기 실적 기여 제한 가능성",
        language="ko",
        published_at=seeded_at - timedelta(hours=1, minutes=30),
        collected_at=seeded_at - timedelta(hours=1, minutes=25),
        content_hash="mock-news-insight-document-00000000000000000000000000000003",
        source_reliability=0.84,
        processing_status=ProcessingStatus.EXTRACTED.value,
    )
    event = ExtractedEvent(
        event_type=EventType.SUPPLY_CONTRACT.value,
        title="글로벌 고객사 장기 공급계약",
        summary="신규 장기 계약으로 반도체 공급 가시성이 높아졌다.",
        importance_score=0.88,
        sentiment_direction=SentimentDirection.POSITIVE.value,
        sentiment_score=0.79,
        confidence_score=0.94,
        occurred_at=seeded_at - timedelta(hours=3),
        detected_at=seeded_at - timedelta(hours=1, minutes=50),
        primary_symbol="005930",
        sector_code="SEMICONDUCTOR",
        event_fingerprint="005930:SUPPLY_CONTRACT:2026-07:GLOBAL_CUSTOMER",
        status=EventStatus.ACTIVE.value,
    )
    topic = TopicCluster(
        slug="semiconductor-long-term-demand",
        title="반도체 장기 수요 회복",
        summary="장기 공급계약과 AI 수요가 공급 가시성을 높이고 있다.",
        category=TopicCategory.DEMAND.value,
        mention_count=12,
        momentum_score=0.81,
        sentiment_score=0.76,
        impact_score=0.87,
        confidence_score=0.9,
        lifecycle_status=LifecycleStatus.RISING.value,
        first_seen_at=seeded_at - timedelta(days=3),
        last_activity_at=seeded_at - timedelta(hours=1),
    )
    session.add_all([document, contradicting_document, event, topic])
    session.flush()

    evidence = EventEvidence(
        event_id=event.id,
        document_id=document.id,
        relevance_score=0.96,
        evidence_role=EvidenceRole.PRIMARY.value,
        extracted_quote="글로벌 고객사와 장기 공급계약을 체결했다.",
    )
    contradicting_evidence = EventEvidence(
        event_id=event.id,
        document_id=contradicting_document.id,
        relevance_score=0.78,
        evidence_role=EvidenceRole.CONTRADICTING.value,
        extracted_quote="신규 계약의 단기 실적 기여는 제한될 수 있다.",
    )
    keywords = (
        TopicKeyword(
            topic_id=topic.id,
            keyword="장기 공급계약",
            weight=0.92,
            sentiment_score=0.78,
            category=TopicCategory.DEMAND.value,
            mention_count=8,
        ),
        TopicKeyword(
            topic_id=topic.id,
            keyword="AI 반도체",
            weight=0.84,
            sentiment_score=0.74,
            category=TopicCategory.GROWTH.value,
            mention_count=6,
        ),
    )
    relation = KeywordRelation(
        topic_id=topic.id,
        source_keyword="장기 공급계약",
        target_keyword="AI 반도체",
        strength=0.86,
        cooccurrence_count=5,
    )
    insight = TopicInsight(
        topic_id=topic.id,
        version=1,
        executive_summary="장기 계약이 반도체 수요 회복의 가시성을 높인다.",
        why_it_matters="계약 기간 동안 매출 변동성이 낮아질 가능성이 있다.",
        key_evidence=[{"event_id": event.id}],
        risk_points=["고객사 주문 일정 변경"],
        counter_arguments=["계약 규모가 전체 매출에서 차지하는 비중은 제한적일 수 있다."],
        impact_score=0.87,
        confidence_score=0.9,
        model_name="mock-news-intelligence",
        prompt_version="v1",
    )
    session.add_all(
        [evidence, contradicting_evidence, *keywords, relation, insight]
    )
    session.flush()

    investor_flow = InvestorFlow(
        market="KR",
        topic_id=topic.id,
        investor_type=InvestorType.FOREIGN.value,
        net_value=Decimal("12500000000.0000"),
        direction=FlowDirection.BUY.value,
        window="5d",
        as_of=seeded_at,
        source_kind="INVESTOR_TYPE",
    )
    symbol_sensitivity = TopicSymbolSensitivity(
        topic_id=topic.id,
        symbol="005930",
        exposure_score=0.91,
        impact_direction=SentimentDirection.POSITIVE.value,
        relationship=SymbolRelationship.DIRECT.value,
        valuation_burden=ValuationBurden.MEDIUM.value,
        note="장기 공급계약의 직접 수혜 가능성이 있다.",
    )
    market_event = MarketEvent(
        scheduled_at=seeded_at + timedelta(days=2),
        event_kind=MarketEventKind.IR_EVENT.value,
        title="반도체 사업부 기업설명회",
        symbol="005930",
        market="KR",
        importance_score=0.82,
    )
    agent_run = AgentRun(
        started_at=seeded_at - timedelta(minutes=15),
        finished_at=seeded_at - timedelta(minutes=2),
        status=AgentRunStatus.COMPLETED.value,
        processed_documents=1,
        extracted_events=1,
        active_topics=1,
        analysis_version="mock-news-intelligence-v2",
    )
    session.add_all([investor_flow, symbol_sensitivity, market_event, agent_run])
    session.flush()

    market_event_topic = MarketEventTopic(
        market_event_id=market_event.id,
        topic_id=topic.id,
    )
    agent_run_stages = tuple(
        AgentRunStage(
            agent_run_id=agent_run.id,
            stage=stage.value,
            status=AgentRunStatus.COMPLETED.value,
            delayed=False,
        )
        for stage in AgentStage
    )
    session.add_all([market_event_topic, *agent_run_stages])
    session.flush()

    analysis_version = "mock-news-intelligence-v3"
    fund_flow_outlooks = (
        FundFlowOutlook(
            sector="반도체",
            direction=FundFlowDirection.INFLOW.value,
            likelihood=FlowLikelihood.HIGH.value,
            estimated_flow_low=Decimal("800000000000.0000"),
            estimated_flow_high=Decimal("1800000000000.0000"),
            estimated_flow_currency="KRW",
            horizon="2~4주",
            confidence=0.76,
            key_assumptions=["AI 서버 수요가 현재 추세를 유지한다."],
            risk_factors=["고객사 재고 조정이 예상보다 길어질 수 있다."],
            analysis_version=analysis_version,
            as_of=seeded_at,
            created_at=seeded_at,
        ),
        FundFlowOutlook(
            sector="2차전지",
            direction=FundFlowDirection.NEUTRAL.value,
            likelihood=FlowLikelihood.MEDIUM.value,
            estimated_flow_low=Decimal("-300000000000.0000"),
            estimated_flow_high=Decimal("300000000000.0000"),
            estimated_flow_currency="KRW",
            horizon="2~4주",
            confidence=0.61,
            key_assumptions=["전기차 수요 지표가 혼조세를 보인다."],
            risk_factors=["원재료 가격 변동성이 확대될 수 있다."],
            analysis_version=analysis_version,
            as_of=seeded_at,
            created_at=seeded_at,
        ),
    )
    fund_flow_scenarios = (
        FundFlowScenario(
            topic_id=topic.id,
            scenario_kind=ScenarioKind.OPTIMISTIC.value,
            weight=0.3,
            expected_flow_direction=FundFlowDirection.INFLOW.value,
            expected_net_flow_low=Decimal("1800000000000.0000"),
            expected_net_flow_high=Decimal("3000000000000.0000"),
            expected_net_flow_currency="KRW",
            key_assumptions=["추가 장기 공급계약이 공개된다."],
            benefiting_sectors=["반도체", "반도체 장비"],
            risk_sectors=[],
            related_symbols=["005930", "000660"],
            invalidation_conditions=["주요 고객사가 주문 계획을 축소한다."],
            analysis_version=analysis_version,
            created_at=seeded_at,
        ),
        FundFlowScenario(
            topic_id=topic.id,
            scenario_kind=ScenarioKind.BASE.value,
            weight=0.5,
            expected_flow_direction=FundFlowDirection.INFLOW.value,
            expected_net_flow_low=Decimal("800000000000.0000"),
            expected_net_flow_high=Decimal("1800000000000.0000"),
            expected_net_flow_currency="KRW",
            key_assumptions=["현재 계약 일정이 계획대로 이행된다."],
            benefiting_sectors=["반도체"],
            risk_sectors=["반도체 소재"],
            related_symbols=["005930"],
            invalidation_conditions=["계약 이행 일정이 한 분기 이상 지연된다."],
            analysis_version=analysis_version,
            created_at=seeded_at,
        ),
        FundFlowScenario(
            topic_id=topic.id,
            scenario_kind=ScenarioKind.CONSERVATIVE.value,
            weight=0.2,
            expected_flow_direction=FundFlowDirection.OUTFLOW.value,
            expected_net_flow_low=None,
            expected_net_flow_high=None,
            expected_net_flow_currency=None,
            key_assumptions=["재고 조정이 예상보다 장기화된다."],
            benefiting_sectors=[],
            risk_sectors=["반도체", "반도체 장비"],
            related_symbols=["005930", "000660"],
            invalidation_conditions=["재고 지표가 두 달 연속 빠르게 개선된다."],
            analysis_version=analysis_version,
            created_at=seeded_at,
        ),
    )
    topic_explanation = TopicExplanation(
        topic_id=topic.id,
        analysis_version=analysis_version,
        data_coverage=0.82,
        confidence=0.76,
        missing_data=["일부 고객사의 세부 주문 일정"],
        limitations=["소규모 연결 데이터 기반 시연 결과"],
        already_priced_in=True,
        already_priced_in_note="최근 주가 상승에 기대 일부가 반영됐을 가능성이 있다.",
        last_updated=seeded_at,
        created_at=seeded_at,
    )
    session.add_all([*fund_flow_outlooks, *fund_flow_scenarios, topic_explanation])
    session.flush()
    explanation_factors = (
        ExplanationFactor(
            topic_explanation_id=topic_explanation.id,
            label="장기 공급계약 근거",
            contribution_ratio=0.55,
            display_order=1,
        ),
        ExplanationFactor(
            topic_explanation_id=topic_explanation.id,
            label="AI 반도체 수요 모멘텀",
            contribution_ratio=0.3,
            display_order=2,
        ),
        ExplanationFactor(
            topic_explanation_id=topic_explanation.id,
            label="반대 근거와 데이터 공백",
            contribution_ratio=0.15,
            display_order=3,
        ),
    )
    session.add_all(explanation_factors)
    session.flush()

    return SeededNewsInsights(
        documents=(document, contradicting_document),
        events=(event,),
        evidence=(evidence, contradicting_evidence),
        topics=(topic,),
        keywords=keywords,
        relations=(relation,),
        insights=(insight,),
        investor_flows=(investor_flow,),
        symbol_sensitivities=(symbol_sensitivity,),
        market_events=(market_event,),
        market_event_topics=(market_event_topic,),
        agent_runs=(agent_run,),
        agent_run_stages=agent_run_stages,
        fund_flow_outlooks=fund_flow_outlooks,
        fund_flow_scenarios=fund_flow_scenarios,
        topic_explanations=(topic_explanation,),
        explanation_factors=explanation_factors,
    )
