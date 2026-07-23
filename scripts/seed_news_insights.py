"""로컬 개발 DB에 뉴스 인사이트 데모 데이터를 넣는다."""

import argparse
import sys
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.domains.news_insights.model import (  # noqa: E402
    AgentRun,
    AgentRunStage,
    EventEvidence,
    ExplanationFactor,
    ExtractedEvent,
    FundFlowOutlook,
    FundFlowScenario,
    InvestorFlow,
    KeywordRelation,
    MarketEvent,
    MarketEventTopic,
    SourceDocument,
    TopicCluster,
    TopicExplanation,
    TopicInsight,
    TopicKeyword,
    TopicSymbolSensitivity,
)
from app.domains.news_insights.seed import seed_mock_news_insights  # noqa: E402


NEWS_INSIGHT_TABLES = (
    ExplanationFactor.__table__,
    AgentRunStage.__table__,
    MarketEventTopic.__table__,
    EventEvidence.__table__,
    InvestorFlow.__table__,
    TopicSymbolSensitivity.__table__,
    FundFlowScenario.__table__,
    TopicExplanation.__table__,
    TopicInsight.__table__,
    TopicKeyword.__table__,
    KeywordRelation.__table__,
    FundFlowOutlook.__table__,
    MarketEvent.__table__,
    AgentRun.__table__,
    TopicCluster.__table__,
    ExtractedEvent.__table__,
    SourceDocument.__table__,
)


def _table_counts(db: Session) -> list[tuple[str, int]]:
    return [
        (
            table.name,
            db.scalar(select(func.count()).select_from(table)) or 0,
        )
        for table in NEWS_INSIGHT_TABLES
    ]


def _print_counts(heading: str, counts: list[tuple[str, int]]) -> None:
    print(heading)
    for table_name, count in counts:
        print(f"- {table_name}: {count}건")


def seed_news_insights(*, reset: bool) -> None:
    with SessionLocal.begin() as db:
        counts = _table_counts(db)
        existing_count = sum(count for _, count in counts)
        if existing_count and not reset:
            _print_counts(
                "뉴스 인사이트 데이터가 이미 있어 시드를 건너뜁니다.",
                counts,
            )
            return

        if reset:
            _print_counts("삭제할 뉴스 인사이트 테이블과 현재 건수:", counts)
            for table in NEWS_INSIGHT_TABLES:
                db.execute(delete(table))

        seed_mock_news_insights(db)

    print("뉴스 인사이트 데모 데이터 시드 완료")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="로컬 개발 DB에 뉴스 인사이트 데모 데이터를 넣습니다.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="기존 뉴스 인사이트 행을 삭제한 뒤 다시 넣습니다.",
    )
    args = parser.parse_args()
    seed_news_insights(reset=args.reset)


if __name__ == "__main__":
    main()
