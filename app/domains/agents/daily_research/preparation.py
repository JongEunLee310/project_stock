"""일일 리서치 실행 전에 전체 임베딩 backlog를 처리한다."""

import logging

from sqlalchemy.orm import Session

from app.adapters.embedding.base import Embedder
from app.adapters.embedding.exceptions import EmbeddingError
from app.adapters.vector.base import VectorStore
from app.domains.rag.indexing_service import EmbeddingIndexer

logger = logging.getLogger(__name__)


def prepare_embeddings(
    db: Session, embedder: Embedder, vector_store: VectorStore
) -> None:
    try:
        indexer = EmbeddingIndexer(db, embedder, vector_store)
        while indexer.run().has_more:
            pass
    except EmbeddingError:
        db.rollback()
        logger.warning(
            "embedding backlog preparation failed; continuing research", exc_info=True
        )
