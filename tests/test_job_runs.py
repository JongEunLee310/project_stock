from collections.abc import Generator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.domains.jobs.service import JobRunService
from app.main import app


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


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db_session = TestingSessionLocal()
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_job_run_start_to_succeed_transition(db: Session) -> None:
    service = JobRunService(db)
    job_run = service.start("news_collection", {"source": "example"})

    assert job_run.status == "running"
    assert job_run.started_at is not None

    succeeded_job_run = service.succeed(job_run.id)

    assert succeeded_job_run.status == "success"
    assert succeeded_job_run.finished_at is not None


def test_job_run_start_to_fail_transition(db: Session) -> None:
    service = JobRunService(db)
    job_run = service.start("news_collection")

    failed_job_run = service.fail(job_run.id, "adapter timeout")

    assert failed_job_run.status == "failed"
    assert failed_job_run.finished_at is not None
    assert failed_job_run.error_message == "adapter timeout"


def test_job_runs_api_lists_recent_runs(client: TestClient) -> None:
    with TestingSessionLocal() as db:
        job_run = JobRunService(db).start("news_collection", {"source": "example"})
        JobRunService(db).succeed(job_run.id)

    response = client.get("/api/v1/job-runs")

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], response.json())
    assert len(data) == 1
    assert data[0]["job_type"] == "news_collection"
    assert data[0]["status"] == "success"
    assert data[0]["started_at"] is not None
    assert data[0]["finished_at"] is not None
