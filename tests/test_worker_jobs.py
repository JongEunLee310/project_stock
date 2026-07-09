from collections.abc import Generator
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.adapters.llm.types import LLMTaskType
from app.domains.assets.model import Asset
from app.domains.jobs.model import JobRun
from app.domains.llm_analysis.schema import RunStatus
from app.domains.raw_news.model import RawNewsEvent
from app.domains.watchlists.model import Watchlist
from app.main import app
from app.worker.jobs import analysis
from app.worker.jobs import llm_analysis
from app.worker.jobs import news
from app.worker.jobs.analysis import analyze_watchlist_job
from app.worker.jobs.llm_analysis import run_llm_analysis_job
from app.worker.jobs.news import collect_news_job
from tests.conftest import api_data, set_current_user

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
    monkeypatch.setattr(news, "SessionLocal", TestingSessionLocal)


def test_collect_news_job_records_success(db: Session) -> None:
    db.add(Asset(symbol="AAPL", name="Apple Inc.", market="NASDAQ"))
    db.commit()

    collect_news_job(["AAPL"])

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.job_type == "news_collection"
    assert job_run.status == "success"
    assert job_run.finished_at is not None
    assert job_run.metadata_ == {
        "symbols": ["AAPL"],
        "targets": [{"symbol": "AAPL", "market": "NASDAQ", "name": "Apple Inc."}],
    }

    raw_news_events = db.scalars(
        select(RawNewsEvent).order_by(RawNewsEvent.url)
    ).all()
    assert len(raw_news_events) == 2
    assert [event.title for event in raw_news_events] == [
        "Apple Inc. mock news 1",
        "Apple Inc. mock news 2",
    ]
    assert [(event.symbol, event.market) for event in raw_news_events] == [
        ("AAPL", "NASDAQ"),
        ("AAPL", "NASDAQ"),
    ]
    assert [event.payload for event in raw_news_events] == [
        {"query": "Apple Inc.", "market": "NASDAQ", "index": 1},
        {"query": "Apple Inc.", "market": "NASDAQ", "index": 2},
    ]


def test_collect_news_job_records_failure(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db.add(Asset(symbol="AAPL", name="Apple Inc.", market="NASDAQ"))
    db.commit()

    def raise_error() -> Any:
        raise RuntimeError("adapter timeout")

    monkeypatch.setattr(news, "get_news_adapter", raise_error)

    with pytest.raises(RuntimeError, match="adapter timeout"):
        collect_news_job(["AAPL"])

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.status == "failed"
    assert job_run.error_message == "adapter timeout"


def test_collect_news_job_records_success_with_target_failure(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingTargetAdapter:
        def fetch(self, symbols: list[str]) -> list[Any]:
            return []

        def fetch_query(self, query: str, market: str) -> list[Any]:
            raise RuntimeError("target timeout")

    db.add(Asset(symbol="AAPL", name="Apple Inc.", market="NASDAQ"))
    db.commit()
    monkeypatch.setattr(news, "get_news_adapter", lambda: FailingTargetAdapter())

    collect_news_job(["AAPL"])

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.status == "success"
    assert job_run.finished_at is not None
    assert db.scalars(select(RawNewsEvent)).all() == []


def test_analyze_all_watchlists_job_isolates_watchlist_failures(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db.add_all(
        [
            Watchlist(user_id=1, name="First"),
            Watchlist(user_id=1, name="Second"),
        ]
    )
    db.commit()
    analyzed_watchlist_ids: list[int] = []

    class PartiallyFailingService:
        def __init__(
            self,
            db: Session,
            gateway: object,
            news_adapter: object,
        ) -> None:
            pass

        def run(self, watchlist_id: int) -> SimpleNamespace:
            analyzed_watchlist_ids.append(watchlist_id)
            if watchlist_id == 1:
                raise RuntimeError("first failed")
            return SimpleNamespace(failures=[])

    monkeypatch.setattr(analysis, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(analysis, "get_llm_gateway", object)
    monkeypatch.setattr(analysis, "get_news_adapter", object)
    monkeypatch.setattr(
        analysis,
        "WatchlistAnalysisService",
        PartiallyFailingService,
    )

    analysis.analyze_all_watchlists_job()

    job_run = db.scalars(select(JobRun)).one()
    assert analyzed_watchlist_ids == [1, 2]
    assert job_run.job_type == "all_watchlists_analysis"
    assert job_run.status == "success"
    assert job_run.metadata_ == {
        "watchlist_ids": [1, 2],
        "partial_failures": [
            {"watchlist_id": 1, "error": "first failed"},
        ],
    }


@dataclass
class FakeLLMAnalysisRun:
    status: str
    error_message: str | None = None


def test_run_llm_analysis_job_records_success(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SuccessfulService:
        def __init__(self, db: Session, gateway: object) -> None:
            self.db = db
            self.gateway = gateway

        def run_analysis(
            self,
            task_type: LLMTaskType,
            user_id: int,
            symbols: list[tuple[str, str]],
        ) -> FakeLLMAnalysisRun:
            assert task_type == LLMTaskType.WATCHLIST_NOTE
            assert user_id == 42
            assert symbols == [("AAPL", "NASDAQ")]
            return FakeLLMAnalysisRun(status=RunStatus.SUCCEEDED.value)

    monkeypatch.setattr(llm_analysis, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(llm_analysis, "get_llm_gateway", lambda: object())
    monkeypatch.setattr(llm_analysis, "LLMAnalysisService", SuccessfulService)

    run_llm_analysis_job(42, LLMTaskType.WATCHLIST_NOTE.value, [("AAPL", "NASDAQ")])

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.job_type == "llm_analysis"
    assert job_run.status == "success"
    assert job_run.finished_at is not None
    assert job_run.error_message is None


def test_run_llm_analysis_job_records_failed_run_status(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailedService:
        def __init__(self, db: Session, gateway: object) -> None:
            self.db = db
            self.gateway = gateway

        def run_analysis(
            self,
            task_type: LLMTaskType,
            user_id: int,
            symbols: list[tuple[str, str]],
        ) -> FakeLLMAnalysisRun:
            return FakeLLMAnalysisRun(
                status=RunStatus.FAILED.value,
                error_message="schema validation failed",
            )

    monkeypatch.setattr(llm_analysis, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(llm_analysis, "get_llm_gateway", lambda: object())
    monkeypatch.setattr(llm_analysis, "LLMAnalysisService", FailedService)

    run_llm_analysis_job(42, LLMTaskType.WATCHLIST_NOTE.value, [("AAPL", "NASDAQ")])

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.job_type == "llm_analysis"
    assert job_run.status == "failed"
    assert job_run.error_message == "schema validation failed"
    assert job_run.finished_at is not None


def test_run_llm_analysis_job_records_wrapper_exception(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_error() -> object:
        raise RuntimeError("gateway unavailable")

    monkeypatch.setattr(llm_analysis, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(llm_analysis, "get_llm_gateway", raise_error)

    with pytest.raises(RuntimeError, match="gateway unavailable"):
        run_llm_analysis_job(
            42,
            LLMTaskType.WATCHLIST_NOTE.value,
            [("AAPL", "NASDAQ")],
        )

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.job_type == "llm_analysis"
    assert job_run.status == "failed"
    assert job_run.error_message == "gateway unavailable"
    assert job_run.finished_at is not None


def test_enqueue_news_job_api(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeJob:
        id = "rq-job-1"

    class FakeQueue:
        def __init__(self, name: str, connection: object) -> None:
            self.name = name
            self.connection = connection

        def enqueue(self, func: object, symbols: list[str]) -> FakeJob:
            assert symbols == ["AAPL", "TSLA"]
            return FakeJob()

    monkeypatch.setattr("app.api.v1.endpoints.worker.Queue", FakeQueue)
    monkeypatch.setattr(
        "app.api.v1.endpoints.worker.get_redis_connection", lambda: object()
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/worker/jobs/news", json={"symbols": ["AAPL", "TSLA"]}
        )

    assert response.status_code == 200
    data = cast(dict[str, str], api_data(response))
    assert data == {"job_id": "rq-job-1", "status": "queued"}


def test_enqueue_analysis_job_api(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeJob:
        id = "rq-job-2"

    class FakeQueue:
        def __init__(self, name: str, connection: object) -> None:
            self.name = name
            self.connection = connection

        def enqueue(self, func: object, watchlist_id: int) -> FakeJob:
            captured["queue_name"] = self.name
            captured["connection"] = self.connection
            captured["func"] = func
            captured["watchlist_id"] = watchlist_id
            return FakeJob()

    class FakeRedis:
        def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
            assert key == "rate_limit:analysis_manual:42"
            assert value == "1"
            assert nx is True
            assert ex == 60
            return True

    redis_connection = FakeRedis()
    monkeypatch.setattr("app.api.v1.endpoints.worker.Queue", FakeQueue)
    monkeypatch.setattr(
        "app.api.v1.endpoints.worker.get_redis_connection",
        lambda: redis_connection,
    )
    set_current_user(42)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/worker/jobs/analysis", json={"watchlist_id": 7}
        )

    assert response.status_code == 200
    data = cast(dict[str, str], api_data(response))
    assert data == {"job_id": "rq-job-2", "status": "queued"}
    assert captured == {
        "queue_name": "default",
        "connection": redis_connection,
        "func": analyze_watchlist_job,
        "watchlist_id": 7,
    }
    app.dependency_overrides.clear()


def test_enqueue_analysis_job_requires_auth() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/worker/jobs/analysis",
            json={"watchlist_id": 7},
        )

    assert response.status_code == 401


def test_enqueue_analysis_job_rate_limit_allows_first_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRedis:
        def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
            return True

    class FakeJob:
        id = "rq-job-first"

    class FakeQueue:
        def __init__(self, name: str, connection: object) -> None:
            pass

        def enqueue(self, func: object, watchlist_id: int) -> FakeJob:
            return FakeJob()

    monkeypatch.setattr("app.api.v1.endpoints.worker.Queue", FakeQueue)
    monkeypatch.setattr(
        "app.api.v1.endpoints.worker.get_redis_connection",
        FakeRedis,
    )
    set_current_user(42)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/worker/jobs/analysis",
            json={"watchlist_id": 7},
        )

    app.dependency_overrides.clear()
    assert response.status_code == 200


def test_enqueue_analysis_job_rate_limit_blocks_second_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRedis:
        def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
            return False

    monkeypatch.setattr(
        "app.api.v1.endpoints.worker.get_redis_connection",
        FakeRedis,
    )
    set_current_user(42)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/worker/jobs/analysis",
            json={"watchlist_id": 7},
        )

    app.dependency_overrides.clear()
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"


def test_enqueue_llm_analysis_job_api(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeJob:
        id = "rq-job-3"

    class FakeQueue:
        def __init__(self, name: str, connection: object) -> None:
            self.name = name
            self.connection = connection

        def enqueue(
            self,
            func: object,
            user_id: int,
            task_type: str,
            symbols: list[tuple[str, str]],
        ) -> FakeJob:
            captured["queue_name"] = self.name
            captured["connection"] = self.connection
            captured["func"] = func
            captured["user_id"] = user_id
            captured["task_type"] = task_type
            captured["symbols"] = symbols
            return FakeJob()

    redis_connection = object()
    monkeypatch.setattr("app.api.v1.endpoints.worker.Queue", FakeQueue)
    monkeypatch.setattr(
        "app.api.v1.endpoints.worker.get_redis_connection",
        lambda: redis_connection,
    )
    set_current_user(42)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/worker/jobs/llm-analysis",
            json={
                "task_type": "WATCHLIST_NOTE",
                "symbols": [{"symbol": "AAPL", "market": "NASDAQ"}],
            },
        )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    data = cast(dict[str, str], api_data(response))
    assert data == {"job_id": "rq-job-3", "status": "queued"}
    assert captured == {
        "queue_name": "default",
        "connection": redis_connection,
        "func": run_llm_analysis_job,
        "user_id": 42,
        "task_type": "WATCHLIST_NOTE",
        "symbols": [("AAPL", "NASDAQ")],
    }


def test_enqueue_llm_analysis_job_requires_auth() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/worker/jobs/llm-analysis",
            json={
                "task_type": "WATCHLIST_NOTE",
                "symbols": [{"symbol": "AAPL", "market": "NASDAQ"}],
            },
        )

    assert response.status_code == 401


def test_enqueue_llm_analysis_job_rejects_empty_symbols() -> None:
    set_current_user(42)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/worker/jobs/llm-analysis",
            json={"task_type": "WATCHLIST_NOTE", "symbols": []},
        )

    app.dependency_overrides.clear()
    assert response.status_code == 422
