from collections.abc import Generator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.domains.jobs.model import JobRun
from app.main import app
from app.worker.jobs import news
from app.worker.jobs.news import collect_news_job

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
    data = cast(dict[str, str], response.json())
    assert data == {"job_id": "rq-job-1", "status": "queued"}
