from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.llm.types import LLMTaskType
from app.domains.llm_analysis.model import LLMAnalysisRun
from app.domains.llm_analysis.repository import LLMAnalysisRunRepository
from app.domains.llm_analysis.schema import LLMAnalysisRunCreate, RunStatus
from app.domains.users.model import User
from tests.conftest import TestingSessionLocal, api_data, set_current_user


def test_llm_analysis_repository_lists_user_runs_by_latest_with_limit(
    db: Session,
) -> None:
    owner = _create_user(db, email="owner@example.com")
    other_user = _create_user(db, email="other@example.com")
    repository = LLMAnalysisRunRepository(db)
    first = _create_run(repository, user_id=owner.id, symbols=["AAPL"])
    second = _create_run(repository, user_id=owner.id, symbols=["TSLA"])
    third = _create_run(repository, user_id=owner.id, symbols=["MSFT"])
    _create_run(repository, user_id=other_user.id, symbols=["NVDA"])

    runs = repository.list_by_user(owner.id, limit=2)

    assert [run.id for run in runs] == [third.id, second.id]
    assert first.id not in [run.id for run in runs]


def test_llm_analysis_repository_get_by_id_for_user_filters_owner(
    db: Session,
) -> None:
    owner = _create_user(db, email="owner@example.com")
    other_user = _create_user(db, email="other@example.com")
    repository = LLMAnalysisRunRepository(db)
    run = _create_run(repository, user_id=owner.id, symbols=["AAPL"])

    assert repository.get_by_id_for_user(run.id, owner.id) is not None
    assert repository.get_by_id_for_user(run.id, other_user.id) is None


def test_list_llm_analysis_runs_returns_owned_summaries_latest_first(
    client: TestClient,
) -> None:
    with TestingSessionLocal() as db:
        owner = _create_user(db, email="owner@example.com")
        other_user = _create_user(db, email="other@example.com")
        repository = LLMAnalysisRunRepository(db)
        first = _create_run(repository, user_id=owner.id, symbols=["AAPL"])
        second = _create_run(repository, user_id=owner.id, symbols=["TSLA"])
        _create_run(repository, user_id=other_user.id, symbols=["NVDA"])
        owner_id = owner.id
        first_id = first.id
        second_id = second.id

    set_current_user(owner_id)

    response = client.get("/api/v1/llm-analysis/runs")

    assert response.status_code == 200
    data = cast(list[dict[str, object]], api_data(response))
    assert [item["id"] for item in data] == [second_id, first_id]
    assert [item["related_symbols"] for item in data] == [["TSLA"], ["AAPL"]]
    assert "input_context_json" not in data[0]
    assert "output_json" not in data[0]
    assert data[0]["created_at"] is not None


def test_get_llm_analysis_run_returns_owned_detail(client: TestClient) -> None:
    with TestingSessionLocal() as db:
        owner = _create_user(db, email="owner@example.com")
        repository = LLMAnalysisRunRepository(db)
        run = _create_run(repository, user_id=owner.id, symbols=["AAPL"])
        owner_id = owner.id
        run_id = run.id

    set_current_user(owner_id)

    response = client.get(f"/api/v1/llm-analysis/runs/{run_id}")

    assert response.status_code == 200
    data = cast(dict[str, object], api_data(response))
    assert data["id"] == run_id
    assert data["input_context_json"] == {"symbols": ["AAPL"]}
    assert data["output_json"] == {"summary": "AAPL summary"}


def test_get_llm_analysis_run_returns_404_for_other_user(
    client: TestClient,
) -> None:
    with TestingSessionLocal() as db:
        owner = _create_user(db, email="owner@example.com")
        other_user = _create_user(db, email="other@example.com")
        repository = LLMAnalysisRunRepository(db)
        run = _create_run(repository, user_id=owner.id, symbols=["AAPL"])
        other_user_id = other_user.id
        run_id = run.id

    set_current_user(other_user_id)

    response = client.get(f"/api/v1/llm-analysis/runs/{run_id}")

    assert response.status_code == 404


def test_llm_analysis_runs_require_auth(client: TestClient) -> None:
    response = client.get("/api/v1/llm-analysis/runs")

    assert response.status_code == 401


def _create_user(db: Session, *, email: str) -> User:
    user = User(email=email, hashed_password="test-hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_run(
    repository: LLMAnalysisRunRepository,
    *,
    user_id: int,
    symbols: list[str],
) -> LLMAnalysisRun:
    return repository.create(
        LLMAnalysisRunCreate(
            user_id=user_id,
            task_type=LLMTaskType.WATCHLIST_NOTE,
            related_symbols=symbols,
            input_context_json={"symbols": symbols},
            output_json={"summary": f"{symbols[0]} summary"},
            status=RunStatus.SUCCEEDED,
            model_name="mock-model",
            prompt_version="v1",
            provider="mock",
        )
    )
