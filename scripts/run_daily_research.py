"""관심종목의 일일 리서치 브리프를 수동 생성한다."""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-id", type=int, action="append", dest="asset_ids")
    parser.add_argument("--date", type=date.fromisoformat, dest="brief_date")
    args = parser.parse_args()

    from app.adapters.factory import get_embedder, get_llm_gateway, get_vector_store
    from app.db.session import SessionLocal
    from app.domains.agents.daily_research.service import DailyResearchAgent

    with SessionLocal() as db:
        result = DailyResearchAgent(
            db, get_embedder(), get_vector_store(db), get_llm_gateway()
        ).run(args.asset_ids, args.brief_date)
        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
