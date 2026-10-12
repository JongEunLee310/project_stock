"""기존 뉴스 원문의 RAG 임베딩을 반복 적재한다."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.adapters.factory import get_embedder, get_vector_store  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.domains.rag.indexing_service import EmbeddingIndexer  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-documents", type=int, default=100)
    args = parser.parse_args()
    if args.max_documents <= 0:
        parser.error("--max-documents must be positive")
    with SessionLocal() as db:
        indexer = EmbeddingIndexer(db, get_embedder(), get_vector_store(db))
        iteration = 0
        while True:
            result = indexer.run(max_documents=args.max_documents)
            iteration += 1
            print(
                f"회차 {iteration}: 문서 {result.embedded_documents}건, "
                f"청크 {result.chunks_written}개, 스캔 {result.scanned}건"
            )
            if not result.has_more:
                break


if __name__ == "__main__":
    main()
