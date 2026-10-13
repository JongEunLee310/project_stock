from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.embedding.exceptions import EmbeddingError
from app.domains.agents.daily_research import preparation
from app.domains.agents.daily_research.schema import DailyResearchResult
from app.domains.jobs.model import JobRun
from app.worker.jobs import agents


@pytest.mark.parametrize("asset_ids", [None, [3, 9]])
@pytest.mark.parametrize("embedding_error", [False, True])
def test_research_job_prepares_backlog_once_and_records_partial_failures(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    asset_ids: list[int] | None,
    embedding_error: bool,
) -> None:
    monkeypatch.setattr(agents, "SessionLocal", lambda: db)
    events: list[str] = []
    indexer = Mock()

    def index() -> Mock:
        events.append("index")
        if embedding_error:
            raise EmbeddingError("unavailable")
        return Mock(has_more=len(events) == 1)

    indexer.run.side_effect = index
    factory = Mock(return_value=indexer)
    monkeypatch.setattr(preparation, "EmbeddingIndexer", factory)
    embedder, store, gateway, writer = Mock(), Mock(), Mock(), Mock()
    for name, value in [
        ("get_embedder", embedder),
        ("get_vector_store", store),
        ("get_llm_gateway", gateway),
        ("get_obsidian_writer", writer),
    ]:
        monkeypatch.setattr(agents, name, Mock(return_value=value))
    result = DailyResearchResult(
        failed={3: "analysis failed"}, note_failures={"index": "write failed"}
    )

    def run(ids: list[int] | None) -> DailyResearchResult:
        events.append("agent")
        assert ids == asset_ids
        return result

    agent = Mock()
    agent.run.side_effect = run
    agent_factory = Mock(return_value=agent)
    monkeypatch.setattr(agents, "DailyResearchAgent", agent_factory)
    agents.run_daily_research_job(asset_ids)
    assert events == (
        ["index", "agent"] if embedding_error else ["index", "index", "agent"]
    )
    factory.assert_called_once_with(db, embedder, store)
    agent_factory.assert_called_once_with(
        db, embedder, store, gateway, obsidian_writer=writer
    )
    record = db.scalars(select(JobRun)).one()
    assert record.job_type == "daily_research_agent"
    assert record.status == "success"
    assert record.finished_at is not None
    assert record.metadata_ == {
        "asset_ids": asset_ids,
        "partial_failures": {
            "failed": {"3": "analysis failed"},
            "note_failures": {"index": "write failed"},
        },
    }


def test_research_job_records_exception(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agents, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        agents, "get_embedder", Mock(side_effect=RuntimeError("broken"))
    )
    with pytest.raises(RuntimeError, match="broken"):
        agents.run_daily_research_job([3])
    record = db.scalars(select(JobRun)).one()
    assert record.status == "failed"
    assert record.error_message == "broken"
    assert record.finished_at is not None


def test_research_job_success_without_partial_failures(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agents, "SessionLocal", lambda: db)
    for name in [
        "get_embedder",
        "get_vector_store",
        "get_llm_gateway",
        "get_obsidian_writer",
    ]:
        monkeypatch.setattr(agents, name, Mock())
    monkeypatch.setattr(agents, "prepare_embeddings", Mock())
    agent = Mock()
    agent.run.return_value = DailyResearchResult(processed=2)
    monkeypatch.setattr(agents, "DailyResearchAgent", Mock(return_value=agent))
    agents.run_daily_research_job([3, 9])
    record = db.scalars(select(JobRun)).one()
    assert record.status == "success"
    assert record.metadata_ == {"asset_ids": [3, 9]}


def test_enqueue_failure_is_logged_and_swallowed(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(agents, "get_redis_connection", Mock())
    queue = Mock()
    queue.enqueue.side_effect = ConnectionError("enqueue unavailable")
    monkeypatch.setattr(agents, "Queue", Mock(return_value=queue))
    agents.enqueue_daily_research_safe([3])
    queue.enqueue.assert_called_once_with(
        agents.run_daily_research_job, [3], job_timeout=3600
    )
    assert "failed to enqueue daily research" in caplog.text


def test_enqueue_daily_research_sets_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents, "get_redis_connection", Mock())
    queue = Mock()
    monkeypatch.setattr(agents, "Queue", Mock(return_value=queue))
    agents.enqueue_daily_research_safe([3, 9])
    queue.enqueue.assert_called_once_with(
        agents.run_daily_research_job, [3, 9], job_timeout=3600
    )
