import logging

from app.adapters.embedding.exceptions import EmbeddingError
from app.adapters.factory import get_embedder, get_vector_store
from app.db.session import SessionLocal
from app.domains.jobs.service import JobRunService
from app.domains.rag.indexing_service import EmbeddingIndexer, IndexingResult

logger = logging.getLogger(__name__)


def embed_documents_job(max_documents: int = 100) -> IndexingResult | None:
    db = SessionLocal()
    job_run_service = JobRunService(db)
    job_run_id: int | None = None
    try:
        job_run = job_run_service.start(
            "embed_documents", {"max_documents": max_documents}
        )
        job_run_id = job_run.id
        result = EmbeddingIndexer(db, get_embedder(), get_vector_store(db)).run(
            max_documents=max_documents
        )
        job_run_service.succeed(job_run_id)
        logger.info("embed_documents completed: %s", result)
        return result
    except Exception as exc:
        db.rollback()
        if job_run_id is not None:
            job_run_service.fail(job_run_id, str(exc))
        if isinstance(exc, EmbeddingError):
            return None
        raise
    finally:
        db.close()
