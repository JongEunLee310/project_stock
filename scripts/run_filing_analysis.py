"""관심종목의 최신 연간보고서를 직전 보고서와 비교해 분석한다."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.db.models  # noqa: E402, F401 — registers all models before DB use


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-id", type=int, action="append", dest="asset_ids")
    args = parser.parse_args()

    from app.adapters.factory import get_llm_gateway
    from app.db.session import SessionLocal
    from app.domains.agents.filing_analysis.service import FilingAnalysisAgent

    with SessionLocal() as db:
        result = FilingAnalysisAgent(db, get_llm_gateway()).run(args.asset_ids)
        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
