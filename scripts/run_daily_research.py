"""관심종목의 일일 리서치 브리프를 수동 생성한다."""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.db.models  # noqa: E402, F401 — registers all models before DB use


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-id", type=int, action="append", dest="asset_ids")
    parser.add_argument("--date", type=date.fromisoformat, dest="brief_date")
    args = parser.parse_args()

    from app.adapters.factory import (
        get_embedder,
        get_llm_gateway,
        get_vector_store,
        get_obsidian_writer,
    )
    from app.db.session import SessionLocal
    from app.domains.agents.daily_research.service import DailyResearchAgent

    from app.domains.agents.daily_research.preparation import prepare_embeddings

    with SessionLocal() as db:
        embedder = get_embedder()
        vector_store = get_vector_store(db)
        prepare_embeddings(db, embedder, vector_store)
        result = DailyResearchAgent(
            db,
            embedder,
            vector_store,
            get_llm_gateway(),
            obsidian_writer=get_obsidian_writer(),
        ).run(args.asset_ids, args.brief_date)
        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
