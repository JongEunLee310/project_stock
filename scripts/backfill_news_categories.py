"""category가 비어 있는 기존 뉴스 항목을 규칙 기반으로 분류한다."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.domains.news.backfill import backfill_news_categories  # noqa: E402


def main() -> None:
    with SessionLocal() as db:
        updated_count = backfill_news_categories(db)
    print(f"뉴스 카테고리 backfill 완료: {updated_count}건 갱신")


if __name__ == "__main__":
    main()
