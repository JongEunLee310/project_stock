"""고정된 평가 세트로 RAG 검색 지표와 유사도 하한 sweep을 출력한다."""

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.db.models  # noqa: E402, F401 — registers all models before DB use
from app.adapters.embedding.base import Embedder  # noqa: E402
from app.adapters.llm.gateway import LLMCompletionResult, LLMGateway  # noqa: E402
from app.adapters.vector.base import VectorStore  # noqa: E402
from app.adapters.vector.types import ChunkFilter, ChunkHit, ChunkRecord  # noqa: E402
from app.domains.rag import retrieval  # noqa: E402
from app.domains.rag.retrieval import (  # noqa: E402
    CANDIDATE_K,
    postprocess_hits,
)
from app.domains.rag.schema import ResearchQARequest, ResearchQAResult  # noqa: E402
from app.domains.rag.service import ResearchQAService  # noqa: E402
from app.domains.rag.types import ChunkSourceType  # noqa: E402

DEFAULT_THRESHOLDS = "0.30,0.35,0.40,0.45,0.50,0.55,0.60"


@dataclass
class EvaluationCase:
    id: str
    positive: bool
    relevant_ids: set[int]
    candidates: list[ChunkHit]


def question_metrics(
    case: EvaluationCase, min_score: float | None = None
) -> dict[str, Any]:
    evidence = postprocess_hits(case.candidates, min_score=min_score)
    relevant = [h.score for h in case.candidates if h.source_id in case.relevant_ids]
    irrelevant = [
        h.score for h in case.candidates if h.source_id not in case.relevant_ids
    ]
    found = sum(h.source_id in case.relevant_ids for h in evidence)
    return {
        "id": case.id,
        "positive": case.positive,
        "relevant_total": len(case.relevant_ids),
        "evidence_count": len(evidence),
        "hit_at_k": bool(found) if case.positive else None,
        "precision_at_k": found / len(evidence) if evidence else None,
        "top1_relevant": (
            bool(evidence and evidence[0].source_id in case.relevant_ids)
            if case.positive
            else None
        ),
        "max_score": max((h.score for h in case.candidates), default=None),
        "relevant_max_score": max(relevant, default=None),
        "relevant_min_score": min(relevant, default=None),
        "irrelevant_max_score": max(irrelevant, default=None),
    }


def mean_present(values: list[Any]) -> float | None:
    present = [v for v in values if v is not None]
    return float(mean(present)) if present else None


def aggregate_metrics(
    cases: list[EvaluationCase], min_score: float | None = None
) -> dict[str, Any]:
    rows = [question_metrics(case, min_score) for case in cases]
    positive = [row for row in rows if row["positive"]]
    negative = [row for row in rows if not row["positive"]]
    relevant = [
        h.score for c in cases for h in c.candidates if h.source_id in c.relevant_ids
    ]
    irrelevant = [
        h.score
        for c in cases
        for h in c.candidates
        if h.source_id not in c.relevant_ids
    ]
    return {
        "positive_hit_at_k": mean_present([r["hit_at_k"] for r in positive]),
        "positive_precision_at_k": mean_present(
            [r["precision_at_k"] for r in positive]
        ),
        "positive_top1_rate": mean_present([r["top1_relevant"] for r in positive]),
        "negative_zero_evidence_rate": mean_present(
            [r["evidence_count"] == 0 for r in negative]
        ),
        "negative_mean_evidence_count": mean_present(
            [r["evidence_count"] for r in negative]
        ),
        "negative_mean_max_score": mean_present([r["max_score"] for r in negative]),
        "relevant_score_median": median(relevant) if relevant else None,
        "relevant_score_max": max(relevant, default=None),
        "irrelevant_score_median": median(irrelevant) if irrelevant else None,
        "irrelevant_score_max": max(irrelevant, default=None),
    }


def threshold_sweep(
    cases: list[EvaluationCase], thresholds: list[float]
) -> list[dict[str, Any]]:
    keys = (
        "positive_hit_at_k",
        "positive_precision_at_k",
        "negative_zero_evidence_rate",
    )
    rows = []
    for threshold in thresholds:
        metrics = aggregate_metrics(cases, threshold)
        rows.append({"threshold": threshold, **{key: metrics[key] for key in keys}})
    return rows


def aggregate_llm(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "positive_insufficient_rate": mean_present(
            [r["llm"]["insufficient_evidence"] for r in rows if r["positive"]]
        ),
        "negative_insufficient_rate": mean_present(
            [r["llm"]["insufficient_evidence"] for r in rows if not r["positive"]]
        ),
        "mean_elapsed_seconds": mean_present(
            [r["llm"]["elapsed_seconds"] for r in rows]
        ),
        "error_count": sum(r["llm"]["error"] is not None for r in rows),
    }


def parse_thresholds(value: str) -> list[float]:
    try:
        thresholds = [float(part.strip()) for part in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "하한은 쉼표로 구분한 숫자여야 합니다."
        ) from exc
    if any(not math.isfinite(t) or not 0 <= t <= 1 for t in thresholds):
        raise argparse.ArgumentTypeError(
            "하한은 0 이상 1 이하의 유한한 값이어야 합니다."
        )
    return thresholds


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-set", type=Path, required=True)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--with-llm", action="store_true")
    parser.add_argument(
        "--thresholds", type=parse_thresholds, default=DEFAULT_THRESHOLDS
    )
    return parser


class ReplayEmbedder(Embedder):
    """서비스가 같은 질문의 임베딩을 재사용하도록 한다."""

    def __init__(self, original: Embedder, question: str, vector: list[float]) -> None:
        self.original = original
        self.question = question
        self.vector = vector

    @property
    def model_name(self) -> str:
        return self.original.model_name

    @property
    def dimensions(self) -> int:
        return self.original.dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        if texts != [self.question]:
            raise ValueError("평가 질문과 서비스 질문이 다릅니다.")
        return [self.vector]


class ReplayVectorStore(VectorStore):
    def __init__(
        self, vector: list[float], filters: ChunkFilter, hits: list[ChunkHit]
    ) -> None:
        self.vector = vector
        self.filters = filters
        self.hits = hits

    def search(
        self, query_vector: list[float], filters: ChunkFilter, k: int
    ) -> list[ChunkHit]:
        if query_vector != self.vector or filters != self.filters or k != CANDIDATE_K:
            raise ValueError("평가 검색 조건과 서비스 검색 조건이 다릅니다.")
        return list(self.hits)

    def upsert(self, records: list[ChunkRecord]) -> int:
        raise NotImplementedError("평가에서는 읽기만 지원합니다.")

    def delete_by_source(self, source_type: ChunkSourceType, source_id: int) -> int:
        raise NotImplementedError("평가에서는 읽기만 지원합니다.")

    def get_content_hashes(
        self, source_type: ChunkSourceType, source_ids: list[int], embedding_model: str
    ) -> dict[int, str]:
        raise NotImplementedError("평가에서는 검색만 지원합니다.")


class RecordingGateway(LLMGateway):
    """서비스가 처리하는 LLM 오류도 평가 결과에 남긴다."""

    def __init__(self, original: LLMGateway) -> None:
        self.original = original
        self.error: str | None = None

    def complete_json(self, *args: Any, **kwargs: Any) -> LLMCompletionResult:
        try:
            completion = self.original.complete_json(*args, **kwargs)
            ResearchQAResult.model_validate(completion.output)
            return completion
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            raise


def evaluate_llm(
    service: ResearchQAService,
    asset_id: int,
    request: ResearchQARequest,
    gateway: RecordingGateway,
) -> dict[str, Any]:
    started = perf_counter()
    result: dict[str, Any] = {
        "insufficient_evidence": None,
        "answer_point_count": None,
        "error": None,
    }
    try:
        answer = service.ask(asset_id, request)
        result.update(
            insufficient_evidence=answer.insufficient_evidence,
            answer_point_count=len(answer.answer_points),
            error=gateway.error,
        )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["elapsed_seconds"] = perf_counter() - started
    return result


def evaluate(
    eval_set: dict[str, Any], thresholds: list[float], with_llm: bool
) -> dict[str, Any]:
    from sqlalchemy import text

    from app.adapters.factory import get_embedder, get_llm_gateway, get_vector_store
    from app.db.session import SessionLocal

    reference_now = datetime.fromisoformat(eval_set["reference_now"])
    if reference_now.tzinfo is None:
        raise ValueError("reference_now에는 시간대가 필요합니다.")
    cases = []
    rows = []
    embedder = get_embedder()
    with SessionLocal() as db:
        store = get_vector_store(db)
        for question in eval_set["questions"]:
            request = ResearchQARequest(
                question=question["question"], lookback_days=eval_set["lookback_days"]
            )
            asset_ids = list(
                db.execute(
                    text("SELECT id FROM assets WHERE symbol = :symbol"),
                    {"symbol": question["symbol"]},
                ).scalars()
            )
            if len(asset_ids) != 1:
                raise ValueError(
                    f"{question['symbol']}: 종목은 정확히 1개여야 합니다 (조회 {len(asset_ids)}개)."
                )
            asset_id = asset_ids[0]
            pattern = question["relevant_title_pattern"]
            relevant_ids = (
                set(
                    db.execute(
                        text("""
                SELECT DISTINCT r.id FROM raw_news_events r
                JOIN news_items n ON n.raw_news_event_id = r.id
                WHERE n.asset_id = :asset_id AND r.title ~* :pattern
            """),
                        {"asset_id": asset_id, "pattern": pattern},
                    ).scalars()
                )
                if pattern is not None
                else set()
            )
            filters = ChunkFilter(
                embedding_model=embedder.model_name,
                asset_id=asset_id,
                source_types=(ChunkSourceType.NEWS,),
                published_after=reference_now - timedelta(days=request.lookback_days),
            )
            vector = embedder.embed([request.question])[0]
            hits = store.search(vector, filters, CANDIDATE_K)
            case = EvaluationCase(
                question["id"], pattern is not None, relevant_ids, hits
            )
            cases.append(case)
            row = {
                **question_metrics(case),
                "symbol": question["symbol"],
                "question": request.question,
            }
            if with_llm:
                try:
                    gateway = RecordingGateway(get_llm_gateway())
                    service = ResearchQAService(
                        db,
                        ReplayEmbedder(embedder, request.question, vector),
                        ReplayVectorStore(vector, filters, hits),
                        gateway,
                        now=lambda: reference_now,
                    )
                    row["llm"] = evaluate_llm(service, asset_id, request, gateway)
                except Exception as exc:
                    row["llm"] = {
                        "insufficient_evidence": None,
                        "answer_point_count": None,
                        "elapsed_seconds": 0.0,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
            rows.append(row)
    report = {
        "reference_now": reference_now.isoformat(),
        "lookback_days": eval_set["lookback_days"],
        "embedding_model": embedder.model_name,
        "min_score": retrieval.MIN_SCORE,
        "questions": rows,
        "aggregate": aggregate_metrics(cases),
        "sweep": threshold_sweep(cases, thresholds),
    }
    if with_llm:
        report["llm_aggregate"] = aggregate_llm(rows)
    return report


def format_cell(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, (float, bool)):
        return f"{value:.3f}"
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def markdown_table(rows: list[dict[str, Any]], keys: list[str]) -> str:
    lines = [
        "| " + " | ".join(keys) + " |",
        "| " + " | ".join("---" for _ in keys) + " |",
    ]
    lines.extend(
        "| " + " | ".join(format_cell(row[key]) for key in keys) + " |" for row in rows
    )
    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    parts = [
        "# RAG Retrieval Evaluation",
        markdown_table(
            [
                {
                    k: v
                    for k, v in report.items()
                    if k
                    in (
                        "reference_now",
                        "lookback_days",
                        "embedding_model",
                        "min_score",
                    )
                }
            ],
            ["reference_now", "lookback_days", "embedding_model", "min_score"],
        ),
        "## Questions",
    ]
    keys = [
        "id",
        "symbol",
        "question",
        "positive",
        "relevant_total",
        "evidence_count",
        "hit_at_k",
        "precision_at_k",
        "top1_relevant",
        "max_score",
        "relevant_max_score",
        "relevant_min_score",
        "irrelevant_max_score",
    ]
    parts.append(markdown_table(report["questions"], keys))
    parts.extend(
        [
            "## Aggregate",
            markdown_table(
                [{"metric": k, "value": v} for k, v in report["aggregate"].items()],
                ["metric", "value"],
            ),
            "## Threshold Sweep",
            markdown_table(
                report["sweep"],
                [
                    "threshold",
                    "positive_hit_at_k",
                    "positive_precision_at_k",
                    "negative_zero_evidence_rate",
                ],
            ),
        ]
    )
    if "llm_aggregate" in report:
        parts.extend(
            [
                "## LLM Questions",
                markdown_table(
                    [{"id": row["id"], **row["llm"]} for row in report["questions"]],
                    [
                        "id",
                        "insufficient_evidence",
                        "answer_point_count",
                        "elapsed_seconds",
                        "error",
                    ],
                ),
                "## LLM Aggregate",
                markdown_table(
                    [
                        {"metric": k, "value": v}
                        for k, v in report["llm_aggregate"].items()
                    ],
                    ["metric", "value"],
                ),
            ]
        )
    return "\n\n".join(parts)


def main() -> None:
    args = build_parser().parse_args()
    eval_set = json.loads(args.eval_set.read_text(encoding="utf-8"))
    report = evaluate(eval_set, args.thresholds, args.with_llm)
    print(render_markdown(report))
    if args.json_out is not None:
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
