from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.domains.rag.retrieval import MIN_SCORE, postprocess_hits
from app.adapters.vector.types import ChunkHit
from app.domains.rag.types import ChunkContentQuality, ChunkSourceType
from scripts.evaluate_rag_retrieval import (
    EvaluationCase,
    aggregate_metrics,
    build_parser,
    question_metrics,
    threshold_sweep,
)


def hit(chunk_id: int, score: float, source_id: int = 1) -> ChunkHit:
    return ChunkHit(
        chunk_id,
        ChunkSourceType.NEWS,
        source_id,
        0,
        "news",
        ChunkContentQuality.FULL,
        datetime(2026, 7, 23, tzinfo=UTC),
        score,
    )


def test_question_metrics_and_raw_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.domains.rag.retrieval.TITLE_ONLY_WEIGHT", 0.8)
    candidates = [
        replace(hit(1, 0.9, 1), content_quality=ChunkContentQuality.TITLE_ONLY),
        hit(2, 0.8, 2),
        hit(3, 0.2, 1),
    ]
    result = question_metrics(EvaluationCase("positive", True, {1, 3}, candidates))
    assert result["relevant_total"] == 2
    assert result["evidence_count"] == 2
    assert result["hit_at_k"] is True
    assert result["precision_at_k"] == 0.5
    assert result["top1_relevant"] is False
    assert result["max_score"] == 0.9
    assert result["relevant_max_score"] == 0.9
    assert result["relevant_min_score"] == 0.2
    assert result["irrelevant_max_score"] == 0.8
    assert candidates[0].score == 0.9


def test_empty_evidence_and_positive_without_labels() -> None:
    result = question_metrics(EvaluationCase("positive", True, set(), [hit(1, 0.2)]))
    assert result["hit_at_k"] is False
    assert result["top1_relevant"] is False
    assert result["precision_at_k"] is None
    assert result["relevant_max_score"] is None
    negative = question_metrics(EvaluationCase("negative", False, set(), []))
    assert negative["hit_at_k"] is None
    assert negative["top1_relevant"] is None
    assert negative["max_score"] is None


def test_aggregation_and_candidate_distribution() -> None:
    cases = [
        EvaluationCase("p1", True, {1}, [hit(1, 0.8), hit(2, 0.4, 2)]),
        EvaluationCase("p2", True, {3}, [hit(3, 0.2, 3)]),
        EvaluationCase("n1", False, set(), [hit(4, 0.5, 4)]),
        EvaluationCase("n2", False, set(), []),
    ]
    result = aggregate_metrics(cases, min_score=0.3)
    assert result["positive_hit_at_k"] == 0.5
    assert result["positive_precision_at_k"] == 0.5
    assert result["positive_top1_rate"] == 0.5
    assert result["negative_zero_evidence_rate"] == 0.5
    assert result["negative_mean_evidence_count"] == 0.5
    assert result["negative_mean_max_score"] == 0.5
    assert result["relevant_score_median"] == 0.5
    assert result["relevant_score_max"] == 0.8
    assert result["irrelevant_score_median"] == 0.45
    assert result["irrelevant_score_max"] == 0.5
    assert all(value is None for value in aggregate_metrics([]).values())


def test_sweep_reuses_candidates_and_threshold_compatibility() -> None:
    candidates = [hit(1, 0.3), hit(2, 0.5, 2), hit(3, 0.8, 3)]
    assert postprocess_hits(candidates) == postprocess_hits(
        candidates, min_score=MIN_SCORE
    )
    assert [
        len(postprocess_hits(candidates, min_score=t)) for t in [0.3, 0.5, 0.9]
    ] == [3, 2, 0]
    cases = [
        EvaluationCase("p", True, {1}, candidates),
        EvaluationCase("n", False, set(), candidates),
    ]
    rows = threshold_sweep(cases, [0.3, 0.5, 0.9])
    assert [row["positive_hit_at_k"] for row in rows] == [1.0, 0.0, 0.0]
    assert [row["positive_precision_at_k"] for row in rows] == [1 / 3, 0.0, None]
    assert [row["negative_zero_evidence_rate"] for row in rows] == [0.0, 0.0, 1.0]
    assert candidates[0].score == 0.3


@pytest.mark.parametrize("threshold", [0.0, 0.7])
def test_metrics_default_reads_current_min_score(
    monkeypatch: pytest.MonkeyPatch, threshold: float
) -> None:
    monkeypatch.setattr("app.domains.rag.retrieval.MIN_SCORE", threshold)
    case = EvaluationCase(
        "p", True, {1}, [hit(1, threshold - 0.001), hit(2, threshold, 2)]
    )
    assert question_metrics(case)["evidence_count"] == 1
    assert question_metrics(case)["hit_at_k"] is False
    assert aggregate_metrics([case])["positive_hit_at_k"] == 0.0
    assert question_metrics(case, threshold - 0.001)["hit_at_k"] is True
    assert aggregate_metrics([case], threshold - 0.001)["positive_hit_at_k"] == 1.0


@pytest.mark.parametrize("value", ["", "abc", "0.3,", "nan", "inf", "-0.1", "1.1"])
def test_invalid_thresholds(value: str) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--eval-set", "set.json", f"--thresholds={value}"])


def test_argument_parsing() -> None:
    args = build_parser().parse_args(
        ["--eval-set", "set.json", "--thresholds", "0.3, 0.5", "--with-llm"]
    )
    assert args.thresholds == [0.3, 0.5]
    assert args.with_llm is True
    assert build_parser().parse_args(["--eval-set", "set.json"]).thresholds == [
        0.3,
        0.35,
        0.4,
        0.45,
        0.5,
        0.55,
        0.6,
    ]


def test_llm_errors_and_aggregation() -> None:
    from unittest.mock import Mock

    from app.adapters.llm.gateway import LLMGateway
    from app.domains.rag.schema import ResearchQARequest
    from app.domains.rag.service import ResearchQAService
    from scripts.evaluate_rag_retrieval import (
        RecordingGateway,
        aggregate_llm,
        evaluate_llm,
    )

    original = Mock(spec=LLMGateway)
    original.complete_json.side_effect = RuntimeError("LLM unavailable")
    gateway = RecordingGateway(original)
    with pytest.raises(RuntimeError):
        gateway.complete_json()
    assert gateway.error == "RuntimeError: LLM unavailable"
    service = Mock(spec=ResearchQAService)
    service.ask.return_value = Mock(insufficient_evidence=True, answer_points=[])
    result = evaluate_llm(service, 1, ResearchQARequest(question="질문"), gateway)
    assert result["insufficient_evidence"] is True
    assert result["answer_point_count"] == 0
    assert result["error"] == gateway.error
    assert result["elapsed_seconds"] >= 0
    service.ask.side_effect = ValueError("failed")
    failure = evaluate_llm(service, 1, ResearchQARequest(question="질문"), gateway)
    assert failure["insufficient_evidence"] is None
    assert failure["error"] == "ValueError: failed"
    assert (
        aggregate_llm(
            [
                {"positive": True, "llm": result},
                {"positive": False, "llm": {**result, "error": None}},
                {"positive": True, "llm": failure},
            ]
        )["positive_insufficient_rate"]
        == 1.0
    )
    assert aggregate_llm([])["mean_elapsed_seconds"] is None


@pytest.mark.parametrize("with_llm", [False, True])
def test_evaluate_reuses_one_search_and_fixed_time(
    with_llm: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime, timedelta
    from unittest.mock import Mock

    from app.adapters.embedding.base import Embedder
    from app.adapters.vector.base import VectorStore
    from app.domains.rag.retrieval import CANDIDATE_K
    from scripts.evaluate_rag_retrieval import evaluate

    db = Mock()
    db.execute.return_value.scalars.side_effect = [[7], [1], [7]]
    session = Mock()
    session.__enter__ = Mock(return_value=db)
    session.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: session)
    monkeypatch.setattr("app.domains.rag.retrieval.MIN_SCORE", 0.85)
    embedder = Mock(spec=Embedder, model_name="test-model", dimensions=2)
    embedder.embed.return_value = [[0.1, 0.2]]
    store = Mock(spec=VectorStore)
    store.search.return_value = [hit(1, 0.8)]
    monkeypatch.setattr("app.adapters.factory.get_embedder", lambda: embedder)
    monkeypatch.setattr("app.adapters.factory.get_vector_store", lambda db: store)
    original_gateway = Mock()
    monkeypatch.setattr(
        "app.adapters.factory.get_llm_gateway", lambda: original_gateway
    )

    def ask(service: object, asset_id: int, request: object) -> object:
        # Replay the same retrieval path through the actual service dependencies.
        assert isinstance(service, ResearchQAService)
        assert isinstance(request, ResearchQARequest)
        vector = service.embedder.embed([request.question])[0]
        from app.adapters.vector.types import ChunkFilter
        from app.domains.rag.types import ChunkSourceType

        filters = ChunkFilter(
            service.embedder.model_name,
            asset_id,
            (ChunkSourceType.NEWS,),
            service.now() - timedelta(days=request.lookback_days),
        )
        assert (
            service.vector_store.search(vector, filters, CANDIDATE_K)
            == store.search.return_value
        )
        return Mock(insufficient_evidence=False, answer_points=[Mock()])

    from app.domains.rag.schema import ResearchQARequest
    from app.domains.rag.service import ResearchQAService

    monkeypatch.setattr(ResearchQAService, "ask", ask)
    eval_set: dict[str, Any] = {
        "reference_now": "2026-07-24T00:00:00+00:00",
        "lookback_days": 365,
        "questions": [
            {
                "id": "p",
                "symbol": "NVDA",
                "question": "질문",
                "relevant_title_pattern": "China",
            },
            {
                "id": "n",
                "symbol": "NVDA",
                "question": "부정",
                "relevant_title_pattern": None,
            },
        ],
    }
    report = evaluate(eval_set, [0.3, 0.9], with_llm)
    assert report["min_score"] == 0.85
    assert report["questions"][0]["evidence_count"] == 0
    assert report["aggregate"]["positive_hit_at_k"] == 0.0
    assert embedder.embed.call_count == 2
    assert store.search.call_count == 2
    filters = store.search.call_args.args[1]
    assert filters.embedding_model == "test-model"
    assert filters.asset_id == 7
    assert filters.published_after == datetime.fromisoformat(
        eval_set["reference_now"]
    ) - timedelta(days=365)
    assert report["questions"][0]["relevant_total"] == 1
    assert report["questions"][1]["relevant_total"] == 0
    assert ("llm_aggregate" in report) is with_llm


def test_markdown_and_json_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json
    from pathlib import Path
    from scripts.evaluate_rag_retrieval import main, render_markdown

    assert isinstance(tmp_path, Path)
    report = {
        "reference_now": "2026-07-24T00:00:00+00:00",
        "lookback_days": 365,
        "embedding_model": "model",
        "min_score": 0.3,
        "questions": [
            {
                **question_metrics(EvaluationCase("p", True, {1}, [])),
                "symbol": "NVDA",
                "question": "a|b\nc",
            }
        ],
        "aggregate": aggregate_metrics([]),
        "sweep": threshold_sweep([], [0.3]),
    }
    markdown = render_markdown(report)
    assert "0.300" in markdown and "null" in markdown
    assert "a\\|b<br>c" in markdown
    source = tmp_path / "eval.json"
    source.write_text("{}", encoding="utf-8")
    output = tmp_path / "output.json"
    monkeypatch.setattr(
        "sys.argv", ["evaluate", "--eval-set", str(source), "--json-out", str(output)]
    )
    monkeypatch.setattr("scripts.evaluate_rag_retrieval.evaluate", lambda *args: report)
    main()
    assert json.loads(output.read_text()) == report
    assert capsys.readouterr().out.strip() == markdown
