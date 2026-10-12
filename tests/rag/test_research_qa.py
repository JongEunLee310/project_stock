from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.embedding.exceptions import EmbeddingError
from app.adapters.embedding.mock import MockEmbedder
from app.adapters.factory import get_llm_gateway
from app.adapters.llm.privacy import ResearchQAEvidenceProjection, ResearchQASnapshot
from app.adapters.llm.prompts.research_qa import build_research_qa_system_prompt
from app.adapters.llm.router import LLM_TASK_ROUTES
from app.adapters.llm.types import LLMTaskType
from app.adapters.vector.memory import InMemoryVectorStore
from app.adapters.vector.types import ChunkHit, ChunkRecord
from app.domains.assets.model import Asset
from app.domains.news.model import NewsItem
from app.domains.rag.indexing_service import EmbeddingIndexer
from app.domains.rag.retrieval import extract_source_name, postprocess_hits
from app.domains.rag.schema import AnswerPoint, ResearchQARequest, ResearchQAResult
from app.domains.rag.service import ResearchQAService, validate_citations
from app.domains.rag.types import ChunkContentQuality, ChunkSourceType
from app.domains.raw_news.model import RawNewsEvent
from app.domains.raw_news.repository import RawNewsEventRepository
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user

NOW = datetime(2026, 10, 12, tzinfo=UTC)
TITLE = "NVIDIA launches new product - Cybernews"


def hit(chunk_id: int, score: float, source_id: int = 1) -> ChunkHit:
    return ChunkHit(
        chunk_id,
        ChunkSourceType.NEWS,
        source_id,
        0,
        "news",
        ChunkContentQuality.FULL,
        NOW,
        score,
    )


def test_retrieval_threshold_weight_and_ties() -> None:
    title_only = replace(hit(4, 0.5), content_quality=ChunkContentQuality.TITLE_ONLY)
    inputs = [hit(3, 0.299), hit(2, 0.4, 2), title_only, hit(1, 0.3, 3)]
    selected = postprocess_hits(inputs)
    assert [h.chunk_id for h in selected] == [2, 4, 1]
    assert selected[1].score == pytest.approx(0.4)
    assert title_only.score == 0.5


def test_retrieval_source_limit_and_final_k() -> None:
    hits = [hit(i, 0.9, 1) for i in range(1, 4)]
    hits += [hit(i, 0.8, i) for i in range(4, 15)]
    assert [h.chunk_id for h in postprocess_hits(list(reversed(hits)))] == [
        1,
        2,
        4,
        5,
        6,
        7,
        8,
        9,
    ]


@pytest.mark.parametrize(
    "title,expected",
    [
        ("headline - Cybernews", "Cybernews"),
        ("headline", "feed"),
        ("headline - detail - Cybernews", "Cybernews"),
        ("headline - ", "feed"),
    ],
)
def test_source_name(title: str, expected: str) -> None:
    assert extract_source_name(title, "feed") == expected


def test_validate_citations() -> None:
    result = ResearchQAResult(
        answer_points=[
            AnswerPoint(text="valid", citations=[99, 2, 2, 1, 99]),
            AnswerPoint(text="missing", citations=[99]),
            AnswerPoint(text="empty", citations=[]),
        ],
        limitations="limit",
        insufficient_evidence=False,
    )
    validated, removed = validate_citations(result, {1, 2})
    assert removed == 2
    assert validated.answer_points == [AnswerPoint(text="valid", citations=[2, 1])]
    assert not validated.insufficient_evidence
    assert result.answer_points[0].citations == [99, 2, 2, 1, 99]
    empty, removed = validate_citations(result, set())
    assert removed == 3 and empty.insufficient_evidence and not empty.answer_points
    assert empty.limitations == "limit"


def test_prompt_and_cloud_contract() -> None:
    prompt = build_research_qa_system_prompt()
    for text in [
        "Do not invent facts, numbers, or dates",
        "buying or selling",
        "target prices",
        "guarantee returns",
        "headlines",
        "insufficient_evidence=true",
        '"$defs"',
        '"ResearchQAResult"',
        "citations",
    ]:
        assert text in prompt
    snapshot = ResearchQASnapshot(
        symbol="NVDA",
        asset_name="NVIDIA",
        question="질문",
        evidence=[
            ResearchQAEvidenceProjection(
                id=1,
                title=TITLE,
                source_name="Cybernews",
                published_at=NOW,
                excerpt="news",
            )
        ],
    )
    assert set(snapshot.as_payload()) == {
        "symbol",
        "asset_name",
        "question",
        "evidence",
    }
    assert set(snapshot.as_payload()["evidence"][0]) == {
        "id",
        "title",
        "source_name",
        "published_at",
        "excerpt",
    }
    for internal in ["user_id", "asset_id", "chunk_id", "source_id"]:
        assert internal not in snapshot.model_dump_json()
    route = LLM_TASK_ROUTES[LLMTaskType.RESEARCH_QA]
    assert route.launch == route.future_primary == "cloud"


def seed(db: Session) -> tuple[int, int]:
    asset = Asset(symbol="NVDA", name="NVIDIA", market="NASDAQ")
    other = Asset(symbol="AAPL", name="Apple", market="NASDAQ")
    db.add_all([asset, other])
    db.flush()
    event = RawNewsEvent(
        title=TITLE,
        source='"NVIDIA Corporation" - Google News',
        url="https://example.com/news",
        published_at=NOW,
    )
    db.add(event)
    db.flush()
    db.add(
        NewsItem(
            raw_news_event_id=event.id,
            asset_id=asset.id,
            title="normalized title",
            source="normalized source",
            url=event.url,
            published_at=NOW,
        )
    )
    db.commit()
    return asset.id, event.id


def test_service_filters_and_no_evidence(db: Session) -> None:
    asset_id, event_id = seed(db)
    embedder = MockEmbedder()
    store = InMemoryVectorStore()
    vector = embedder.embed(["question"])[0]
    record = ChunkRecord(
        ChunkSourceType.NEWS,
        event_id,
        0,
        "x" * 400,
        ChunkContentQuality.FULL,
        vector,
        embedder.model_name,
        [asset_id],
        NOW - timedelta(days=91),
        "hash",
    )
    store.upsert(
        [
            record,
            replace(
                record,
                source_id=event_id + 1,
                asset_ids=[asset_id + 1],
                published_at=NOW,
            ),
        ]
    )
    gateway = Mock(wraps=get_llm_gateway())
    service = ResearchQAService(db, embedder, store, gateway, now=lambda: NOW)
    response = service.ask(asset_id, ResearchQARequest(question="question"))
    assert (
        not response.evidence
        and not response.answer_points
        and response.insufficient_evidence
    )
    gateway.complete_json.assert_not_called()
    assert "90일" in (response.limitations or "")
    store.upsert([replace(record, published_at=NOW)])
    response = service.ask(asset_id, ResearchQARequest(question="question"))
    assert len(response.evidence) == 1 and response.evidence[0].source_id == event_id
    assert len(response.evidence[0].excerpt) == 300 and response.generated_at == NOW
    assert response.answer_points[0].citations == [1]
    payload = gateway.complete_json.call_args.args[1]
    assert isinstance(payload, ResearchQASnapshot)
    assert payload.asset_name == "NVIDIA"
    gateway.complete_json = Mock(
        return_value=Mock(
            output={
                "answer_points": [{"text": "invalid", "citations": [999]}],
                "limitations": None,
                "insufficient_evidence": False,
            }
        )
    )
    invalid = service.ask(asset_id, ResearchQARequest(question="question"))
    assert not invalid.answer_points and invalid.insufficient_evidence
    assert RawNewsEventRepository(db).list_by_ids([]) == []
    assert [
        event.id
        for event in RawNewsEventRepository(db).list_by_ids([event_id, event_id])
    ] == [event_id]


@pytest.mark.parametrize("failure", [None, "llm", "embedding"])
def test_indexer_to_api_contract(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    failure: str | None,
) -> None:
    with TestingSessionLocal() as db:
        asset_id, _ = seed(db)
        embedder = MockEmbedder()
        store = InMemoryVectorStore()
        assert EmbeddingIndexer(db, embedder, store).run().chunks_written == 1
    gateway = Mock(wraps=get_llm_gateway())
    if failure == "llm":
        gateway.complete_json.side_effect = RuntimeError("unavailable")
    if failure == "embedding":
        monkeypatch.setattr(
            embedder, "embed", Mock(side_effect=EmbeddingError("unavailable"))
        )
    monkeypatch.setattr("app.api.v1.endpoints.assets.get_embedder", lambda: embedder)
    monkeypatch.setattr(
        "app.api.v1.endpoints.assets.get_vector_store", lambda db: store
    )
    monkeypatch.setattr("app.api.v1.endpoints.assets.get_llm_gateway", lambda: gateway)
    monkeypatch.setattr(
        "app.api.v1.endpoints.assets.ResearchQAService",
        partial(ResearchQAService, now=lambda: NOW),
    )
    set_current_user(1)
    response = client.post(
        f"/api/v1/assets/{asset_id}/research-qa", json={"question": TITLE}
    )
    if failure == "embedding":
        assert response.status_code == 503
        assert api_error(response)["code"] == "RAG_EMBEDDING_UNAVAILABLE"
        gateway.complete_json.assert_not_called()
        return
    assert response.status_code == 200
    data = api_data(response)
    assert data["evidence"][0]["title"] == TITLE
    assert data["evidence"][0]["source_name"] == "Cybernews"
    assert data["evidence"][0]["content_quality"] == "TITLE_ONLY"
    assert data["evidence"][0]["score"] == pytest.approx(0.8)
    assert data["insufficient_evidence"] == (failure == "llm")
    if failure:
        assert data["answer_points"] == [] and "실패" in data["limitations"]
    else:
        assert data["answer_points"][0]["citations"] == [1]
    gateway.complete_json.assert_called_once()


def test_api_no_evidence(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    with TestingSessionLocal() as db:
        asset_id, _ = seed(db)
    gateway = Mock(wraps=get_llm_gateway())
    monkeypatch.setattr("app.api.v1.endpoints.assets.get_llm_gateway", lambda: gateway)
    set_current_user(1)
    response = client.post(
        f"/api/v1/assets/{asset_id}/research-qa", json={"question": "질문"}
    )
    assert response.status_code == 200
    data = api_data(response)
    assert data["insufficient_evidence"] and data["evidence"] == []
    gateway.complete_json.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        {"question": ""},
        {"question": "   "},
        {"question": "a" * 501},
        {"question": "질문", "lookback_days": 0},
        {"question": "질문", "lookback_days": 366},
    ],
)
def test_api_validation(client: TestClient, body: dict[str, Any]) -> None:
    set_current_user(1)
    assert client.post("/api/v1/assets/1/research-qa", json=body).status_code == 422


def test_api_auth_and_missing_asset(client: TestClient) -> None:
    path = "/api/v1/assets/999/research-qa"
    assert client.post(path, json={"question": "질문"}).status_code == 401
    set_current_user(1)
    response = client.post(path, json={"question": "질문"})
    assert (
        response.status_code == 404 and api_error(response)["code"] == "ASSET_NOT_FOUND"
    )
    assert ResearchQARequest(question="  질문  ").question == "질문"
    assert len(ResearchQARequest(question=" " + "a" * 500 + " ").question) == 500
