from unittest.mock import Mock
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.agents.filing_analysis.schema import FilingAnalysisResult
from app.domains.jobs.model import JobRun
from app.scheduler.registry import default_scheduler_registry
from app.worker.jobs import agents
from app.worker.jobs.timeouts import FILING_ANALYSIS_JOB_TIMEOUT


@pytest.mark.parametrize("asset_ids", [None, [3, 9]])
@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("note_failure", [False, True])
def test_job_records_success_and_partial_failures(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    asset_ids: list[int] | None,
    partial: bool,
    note_failure: bool,
) -> None:
    monkeypatch.setattr(agents, "SessionLocal", lambda: db)
    fake_gateway = Mock()
    monkeypatch.setattr(agents, "get_llm_gateway", Mock(return_value=fake_gateway))
    writer = Mock()
    monkeypatch.setattr(agents, "get_obsidian_writer", Mock(return_value=writer))
    agent = Mock()
    agent.run.return_value = FilingAnalysisResult(
        analyzed=1, failed={3: "section failed"} if partial else {},
        note_failures={3: "disk full"} if note_failure else {},
    )
    factory = Mock(return_value=agent)
    monkeypatch.setattr(agents, "FilingAnalysisAgent", factory)
    agents.run_filing_analysis_job(asset_ids)
    factory.assert_called_once_with(db, fake_gateway, obsidian_writer=writer)
    agent.run.assert_called_once_with(asset_ids)
    record = db.scalars(select(JobRun)).one()
    assert record.job_type == "filing_analysis_agent"
    assert record.status == "success" and record.finished_at is not None
    expected: dict[str, Any] = {"asset_ids": asset_ids}
    if partial or note_failure:
        expected["partial_failures"] = {
            "failed": {"3": "section failed"} if partial else {},
            "note_failures": {"3": "disk full"} if note_failure else {},
        }
    assert record.metadata_ == expected


def test_job_records_exception(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        agents, "get_llm_gateway", Mock(side_effect=RuntimeError("broken"))
    )
    with pytest.raises(RuntimeError, match="broken"):
        agents.run_filing_analysis_job([3])
    record = db.scalars(select(JobRun)).one()
    assert record.status == "failed"
    assert record.error_message == "broken" and record.finished_at is not None


def test_weekly_schedule_timeout() -> None:
    schedule = default_scheduler_registry.get("filing_analysis_agent")
    assert schedule is not None and schedule.enabled
    assert schedule.job.func is agents.run_filing_analysis_job
    assert schedule.cron == "30 1 * * 6"
    assert schedule.job_timeout == FILING_ANALYSIS_JOB_TIMEOUT == 1800


def test_manual_script_repeated_assets_and_json_output(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json
    import sys

    from app.adapters import factory
    from app.db import session
    from app.domains.agents.filing_analysis import service
    from scripts import run_filing_analysis

    monkeypatch.setattr(
        sys, "argv", ["run_filing_analysis.py", "--asset-id", "3", "--asset-id", "9"]
    )
    monkeypatch.setattr(session, "SessionLocal", lambda: db)
    fake_gateway, writer = Mock(), Mock()
    monkeypatch.setattr(factory, "get_llm_gateway", Mock(return_value=fake_gateway))
    monkeypatch.setattr(factory, "get_obsidian_writer", Mock(return_value=writer))
    agent = Mock()
    agent.run.return_value = FilingAnalysisResult(analyzed=2)
    constructor = Mock(return_value=agent)
    monkeypatch.setattr(service, "FilingAnalysisAgent", constructor)
    run_filing_analysis.main()
    constructor.assert_called_once_with(db, fake_gateway, obsidian_writer=writer)
    agent.run.assert_called_once_with([3, 9])
    assert json.loads(capsys.readouterr().out)["analyzed"] == 2
