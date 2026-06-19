from collections.abc import Generator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.domains.jobs.model import JobRun
from app.domains.raw_news.model import RawNewsEvent
from app.main import app
from app.worker.jobs import news
from app.worker.jobs.analysis import analyze_watchlist_job
from app.worker.jobs.news import collect_news_job
from tests.conftest import api_data

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
    collect_news_job(["AAPL"])

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.job_type == "news_collection"
    assert job_run.status == "success"
    assert job_run.finished_at is not None
    assert job_run.metadata_ == {"symbols": ["AAPL"]}

    raw_news_events = db.scalars(
        select(RawNewsEvent).order_by(RawNewsEvent.url)
    ).all()
    assert len(raw_news_events) == 2
    assert [event.title for event in raw_news_events] == [
        "AAPL mock news 1",
        "AAPL mock news 2",
    ]
    assert [event.payload for event in raw_news_events] == [
        {"symbol": "AAPL", "index": 1},
        {"symbol": "AAPL", "index": 2},
    ]


def test_collect_news_job_records_failure(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_error(self: object, symbols: list[str]) -> list[Any]:
        raise RuntimeError("adapter timeout")

    monkeypatch.setattr("app.worker.jobs.news.MockNewsAdapter.fetch", raise_error)

    with pytest.raises(RuntimeError, match="adapter timeout"):
        collect_news_job(["AAPL"])

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.status == "failed"
    assert job_run.error_message == "adapter timeout"


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

    redis_connection = object()
    monkeypatch.setattr("app.api.v1.endpoints.worker.Queue", FakeQueue)
    monkeypatch.setattr(
        "app.api.v1.endpoints.worker.get_redis_connection",
        lambda: redis_connection,
    )

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
