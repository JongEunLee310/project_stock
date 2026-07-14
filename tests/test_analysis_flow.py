from collections.abc import Generator
from datetime import datetime, timezone
from typing import Literal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters.llm.gateway import CLOUD, LOCAL, LLMGateway
from app.adapters.llm.mock import MockLLMClient
from app.adapters.news.base import NewsAdapter, NewsAdapterResult
from app.adapters.news.mock import MockNewsAdapter
from app.core.exceptions import AppException
from app.db.base import Base
from app.domains.alerts.model import Alert
from app.domains.analysis.schema import AnalysisFlowResult
from app.domains.analysis.service import WatchlistAnalysisService
from app.domains.assets.model import Asset
from app.domains.jobs.model import JobRun
from app.domains.news.model import NewsItem
from app.domains.raw_news.model import RawNewsEvent
from app.domains.reports.model import ResearchReport
from app.domains.signals.model import Signal
from app.domains.signals.types import SignalType
from app.domains.theses.model import InvestmentThesis
from app.domains.users.model import User
from app.domains.watchlists.model import Watchlist, WatchlistItem
from app.worker.jobs import analysis
from app.worker.jobs.analysis import analyze_watchlist_job


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class StaticNewsAdapter(NewsAdapter):
    def __init__(self, results_by_query: dict[str, list[NewsAdapterResult]]) -> None:
        self.results_by_query = results_by_query
        self.queries: list[tuple[str, str]] = []

    def fetch(self, symbols: list[str]) -> list[NewsAdapterResult]:
        raise AssertionError("analysis must use query-based news collection")

    def fetch_query(self, query: str, market: str) -> list[NewsAdapterResult]:
        self.queries.append((query, market))
        return self.results_by_query.get(query, [])


class FailingNewsAdapter(StaticNewsAdapter):
    def __init__(
        self,
        results_by_query: dict[str, list[NewsAdapterResult]],
        failing_query: str,
    ) -> None:
        super().__init__(results_by_query)
        self.failing_query = failing_query

    def fetch_query(self, query: str, market: str) -> list[NewsAdapterResult]:
        if query == self.failing_query:
            raise RuntimeError(f"{query} query failed")
        return super().fetch_query(query, market)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def patch_worker_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(analysis, "get_llm_gateway", lambda: llm_gateway())
    monkeypatch.setattr(analysis, "get_news_adapter", MockNewsAdapter)


def llm_client(
    conflict_status: Literal["SUPPORTS", "NEUTRAL", "CONFLICTS"] = "NEUTRAL",
    invalidation_triggered: bool = False,
) -> MockLLMClient:
    return MockLLMClient(
        {
            "NewsSummaryResult": {
                "summary": "Management update materially affects the thesis.",
                "positive_factors": ["Revenue growth"],
                "negative_factors": ["Margin pressure"],
                "impact_level": "HIGH",
                "sentiment": "NEGATIVE",
            },
            "ThesisConflictResult": {
                "status": conflict_status,
                "reason": "The update conflicts with the active thesis.",
                "invalidation_triggered": invalidation_triggered,
            },
        }
    )


def llm_gateway(
    conflict_status: Literal["SUPPORTS", "NEUTRAL", "CONFLICTS"] = "NEUTRAL",
    invalidation_triggered: bool = False,
) -> LLMGateway:
    client = llm_client(conflict_status, invalidation_triggered)
    return LLMGateway({CLOUD: client, LOCAL: client})


def news_result(symbol: str, index: int = 1) -> NewsAdapterResult:
    query = f"{symbol} Inc."
    return NewsAdapterResult(
        title=f"{query} mock news {index}",
        url=(
            "https://example.com/mock-news/query/"
            f"nasdaq/{query.lower().replace(' ', '-')}/{index}"
        ),
        body=f"Mock news body for {query} #{index}",
        source="mock",
        published_at=datetime.now(timezone.utc),
        payload={"query": query, "market": "NASDAQ", "index": index},
    )


def create_user(db: Session, email: str = "owner@example.com") -> User:
    user = User(email=email, hashed_password="test-hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_asset(db: Session, symbol: str) -> Asset:
    asset = Asset(symbol=symbol, name=f"{symbol} Inc.", market="NASDAQ")
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def create_watchlist(
    db: Session,
    user_id: int,
    assets: list[Asset],
) -> Watchlist:
    watchlist = Watchlist(user_id=user_id, name="Core")
    db.add(watchlist)
    db.commit()
    db.refresh(watchlist)
    for priority, asset in enumerate(assets):
        db.add(
            WatchlistItem(
                watchlist_id=watchlist.id,
                asset_id=asset.id,
                priority=priority,
            )
        )
    db.commit()
    return watchlist


def create_thesis(db: Session, user_id: int, asset_id: int) -> InvestmentThesis:
    thesis = InvestmentThesis(
        user_id=user_id,
        asset_id=asset_id,
        summary="The company can grow earnings through durable demand.",
        invalidation_conditions="Management cuts guidance.",
    )
    db.add(thesis)
    db.commit()
    db.refresh(thesis)
    return thesis


def run_service(
    db: Session,
    watchlist_id: int,
    adapter: NewsAdapter,
    gateway: LLMGateway | None = None,
) -> AnalysisFlowResult:
    return WatchlistAnalysisService(
        db,
        gateway or llm_gateway(),
        adapter,
    ).run(watchlist_id)


def test_watchlist_analysis_flow_creates_news_report_signal_and_alert(
    db: Session,
) -> None:
    user = create_user(db)
    asset = create_asset(db, "AAPL")
    watchlist = create_watchlist(db, user.id, [asset])
    adapter = StaticNewsAdapter({asset.name: [news_result("AAPL")]})

    result = run_service(db, watchlist.id, adapter)

    assert result.watchlist_id == watchlist.id
    assert result.processed_assets == 1
    assert result.created_news_items == 1
    assert result.created_reports == 1
    assert result.created_signals == 1
    assert result.created_alerts == 1
    assert result.failures == []
    news_item = db.scalar(select(NewsItem).where(NewsItem.asset_id == asset.id))
    assert news_item is not None
    assert news_item.category == "OTHER"
    assert db.scalar(select(ResearchReport)) is not None
    assert db.scalar(select(Signal)) is not None
    assert db.scalar(select(Alert).where(Alert.user_id == user.id)) is not None
    assert adapter.queries == [(asset.name, asset.market.upper())]


def test_watchlist_analysis_flow_uses_mock_query_results(db: Session) -> None:
    user = create_user(db)
    asset = create_asset(db, "AAPL")
    watchlist = create_watchlist(db, user.id, [asset])

    result = run_service(db, watchlist.id, MockNewsAdapter())

    news_items = db.scalars(select(NewsItem).order_by(NewsItem.id)).all()
    assert result.created_news_items == 2
    assert result.created_reports == 2
    assert result.created_signals == 2
    assert [item.source for item in news_items] == ["mock", "mock"]
    assert [item.url for item in news_items] == [
        "https://example.com/mock-news/query/nasdaq/aapl-inc./1",
        "https://example.com/mock-news/query/nasdaq/aapl-inc./2",
    ]


def test_watchlist_analysis_flow_skips_duplicate_news_urls(db: Session) -> None:
    user = create_user(db)
    asset = create_asset(db, "AAPL")
    watchlist = create_watchlist(db, user.id, [asset])
    adapter = StaticNewsAdapter({asset.name: [news_result("AAPL")]})

    first = run_service(db, watchlist.id, adapter)
    second = run_service(db, watchlist.id, adapter)

    assert first.created_news_items == 1
    assert second.created_news_items == 0
    assert second.created_reports == 0
    assert db.scalars(select(NewsItem)).all()
    assert len(db.scalars(select(NewsItem)).all()) == 1
    assert len(db.scalars(select(RawNewsEvent)).all()) == 1


def test_watchlist_analysis_flow_routes_conflict_to_signal_and_alert(
    db: Session,
) -> None:
    user = create_user(db)
    asset = create_asset(db, "AAPL")
    create_thesis(db, user.id, asset.id)
    watchlist = create_watchlist(db, user.id, [asset])
    adapter = StaticNewsAdapter({asset.name: [news_result("AAPL")]})

    result = run_service(
        db,
        watchlist.id,
        adapter,
        llm_gateway(conflict_status="CONFLICTS"),
    )

    signal = db.scalars(select(Signal)).one()
    report = db.scalars(select(ResearchReport)).one()
    assert result.created_reports == 1
    assert result.created_signals == 1
    assert result.created_alerts == 1
    assert signal.signal_type == SignalType.RISK_ALERT.value
    assert signal.thesis_id is not None
    assert report.thesis_conflict_status == "CONFLICTS"


def test_watchlist_analysis_flow_isolates_asset_failures(db: Session) -> None:
    user = create_user(db)
    good_asset = create_asset(db, "AAPL")
    failing_asset = create_asset(db, "TSLA")
    watchlist = create_watchlist(db, user.id, [good_asset, failing_asset])
    adapter = FailingNewsAdapter(
        {good_asset.name: [news_result("AAPL")]},
        failing_query=failing_asset.name,
    )

    result = run_service(db, watchlist.id, adapter)

    assert result.processed_assets == 1
    assert result.created_news_items == 1
    assert result.failures == [
        {"asset_id": failing_asset.id, "error": "TSLA Inc. query failed"}
    ]
    assert (
        db.scalar(select(NewsItem).where(NewsItem.asset_id == good_asset.id))
        is not None
    )


def test_analyze_watchlist_job_records_success(db: Session) -> None:
    user = create_user(db)
    asset = create_asset(db, "AAPL")
    watchlist = create_watchlist(db, user.id, [asset])

    analyze_watchlist_job(watchlist.id)

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.job_type == "watchlist_analysis"
    assert job_run.status == "success"
    assert job_run.finished_at is not None
    assert job_run.metadata_ == {"watchlist_id": watchlist.id}


def test_analyze_watchlist_job_records_partial_failures_in_metadata(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user(db)
    good_asset = create_asset(db, "AAPL")
    failing_asset = create_asset(db, "TSLA")
    watchlist = create_watchlist(db, user.id, [good_asset, failing_asset])

    adapter = FailingNewsAdapter(
        {good_asset.name: [news_result("AAPL")]},
        failing_query=failing_asset.name,
    )
    monkeypatch.setattr(analysis, "get_news_adapter", lambda: adapter)

    analyze_watchlist_job(watchlist.id)

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.status == "success"
    assert job_run.metadata_ == {
        "watchlist_id": watchlist.id,
        "partial_failures": [
            {"asset_id": failing_asset.id, "error": "TSLA Inc. query failed"}
        ],
    }


def test_analyze_watchlist_job_records_failure_for_missing_watchlist(
    db: Session,
) -> None:
    with pytest.raises(AppException):
        analyze_watchlist_job(999)

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.status == "failed"
    assert job_run.error_message == "관심 목록을 찾을 수 없습니다."
