"""관심종목의 최근 10-K 사업·위험요인 섹션을 수집한다."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.db.models  # noqa: E402, F401


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-id", type=int, action="append", dest="asset_ids")
    args = parser.parse_args()

    from app.db.session import SessionLocal
    from app.domains.knowledge.filing_service import FilingCollectionService

    with SessionLocal() as db:
        result = FilingCollectionService(db).collect(args.asset_ids)
        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
