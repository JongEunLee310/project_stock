import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.adapters.embedding.base import Embedder
from app.adapters.embedding.exceptions import EmbeddingError
from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.privacy import ResearchQAEvidenceProjection, ResearchQASnapshot
from app.adapters.llm.prompts.research_qa import build_research_qa_system_prompt
from app.adapters.llm.types import LLMTaskType
from app.adapters.obsidian.writer import ObsidianWriter, ResearchNote
from app.adapters.vector.base import VectorStore
from app.adapters.vector.types import ChunkFilter
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.rag.retrieval import CANDIDATE_K, extract_source_name, postprocess_hits
from app.domains.rag.schema import (
    EvidenceItem,
    ResearchAnswer,
    ResearchQARequest,
    ResearchQAResult,
)
from app.domains.rag.types import ChunkSourceType
from app.domains.raw_news.repository import RawNewsEventRepository

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


def validate_citations(
    result: ResearchQAResult, evidence_ids: set[int]
) -> tuple[ResearchQAResult, int]:
    points = []
    for point in result.answer_points:
        citations = list(dict.fromkeys(c for c in point.citations if c in evidence_ids))
        if citations:
            points.append(point.model_copy(update={"citations": citations}))
    return result.model_copy(
        update={
            "answer_points": points,
            "insufficient_evidence": result.insufficient_evidence or not points,
        }
    ), len(result.answer_points) - len(points)


class ResearchQAService:
    def __init__(
        self,
        db: Session,
        embedder: Embedder,
        vector_store: VectorStore,
        gateway: LLMGateway,
        now: Callable[[], datetime] = utc_now,
        obsidian_writer: ObsidianWriter | None = None,
    ) -> None:
        self.db = db
        self.embedder = embedder
        self.vector_store = vector_store
        self.gateway = gateway
        self.now = now
        self.obsidian_writer = obsidian_writer

    def ask(self, asset_id: int, request: ResearchQARequest) -> ResearchAnswer:
        asset = AssetRepository(self.db).get_by_id(asset_id)
        if asset is None:
            raise AppException(
                404, "종목을 찾을 수 없습니다.", ErrorCode.ASSET_NOT_FOUND
            )
        generated_at = self.now()
        try:
            vector = self.embedder.embed([request.question])[0]
        except EmbeddingError as exc:
            raise AppException(
                503,
                "질문 임베딩을 생성할 수 없습니다.",
                ErrorCode.RAG_EMBEDDING_UNAVAILABLE,
            ) from exc
        hits = postprocess_hits(
            self.vector_store.search(
                vector,
                ChunkFilter(
                    embedding_model=self.embedder.model_name,
                    asset_id=asset_id,
                    source_types=(ChunkSourceType.NEWS,),
                    published_after=generated_at
                    - timedelta(days=request.lookback_days),
                ),
                CANDIDATE_K,
            )
        )
        events = {
            event.id: event
            for event in RawNewsEventRepository(self.db).list_by_ids(
                list(dict.fromkeys(hit.source_id for hit in hits))
            )
        }
        evidence: list[EvidenceItem] = []
        for hit in hits:
            event = events.get(hit.source_id)
            if event is None:
                continue
            evidence.append(
                EvidenceItem(
                    id=len(evidence) + 1,
                    source_type=hit.source_type,
                    source_id=hit.source_id,
                    title=event.title,
                    source_name=extract_source_name(event.title, event.source),
                    source_url=event.url,
                    published_at=hit.published_at,
                    excerpt=hit.content[:300],
                    score=hit.score,
                    content_quality=hit.content_quality,
                )
            )
        result = ResearchQAResult(
            answer_points=[],
            insufficient_evidence=True,
            limitations=f"최근 {request.lookback_days}일 안에 이 종목과 관련된 근거를 찾지 못했습니다.",
        )
        if evidence:
            snapshot = ResearchQASnapshot(
                symbol=asset.symbol,
                asset_name=asset.name,
                question=request.question,
                evidence=[
                    ResearchQAEvidenceProjection(
                        id=item.id,
                        title=item.title,
                        source_name=item.source_name,
                        published_at=item.published_at,
                        excerpt=item.excerpt,
                    )
                    for item in evidence
                ],
            )
            try:
                completion = self.gateway.complete_json(
                    LLMTaskType.RESEARCH_QA,
                    snapshot,
                    ResearchQAResult,
                    build_research_qa_system_prompt(),
                )
                result = ResearchQAResult.model_validate(completion.output)
            except Exception:
                logger.warning(
                    "Research QA generation failed: asset_id=%s",
                    asset_id,
                    exc_info=True,
                )
                result = ResearchQAResult(
                    answer_points=[],
                    insufficient_evidence=True,
                    limitations="근거를 찾았지만 답변 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.",
                )
            result, removed = validate_citations(result, {item.id for item in evidence})
            logger.info("Research QA citation validation: removed_points=%s", removed)
        answer = ResearchAnswer(
            **result.model_dump(), evidence=evidence, generated_at=generated_at
        )
        if request.save_to_obsidian:
            if self.obsidian_writer is None:
                logger.warning(
                    "Obsidian vault is not configured: asset_id=%s", asset_id
                )
            else:
                try:
                    path = self.obsidian_writer.write_research_note(
                        ResearchNote(
                            symbol=asset.symbol,
                            asset_name=asset.name,
                            question=request.question,
                            answer=answer,
                            embedding_model=self.embedder.model_name,
                        )
                    )
                    answer.obsidian_note_path = path.as_posix()
                except (OSError, ValueError):
                    logger.warning(
                        "Obsidian note export failed: asset_id=%s",
                        asset_id,
                        exc_info=True,
                    )
        return answer
