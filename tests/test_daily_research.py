import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.embedding.mock import MockEmbedder
from app.adapters.llm.base import LLMMessage
from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.mock import DEFAULT_MOCK_RESPONSES, MockLLMClient
from app.adapters.llm.prompts.language import KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION
from app.adapters.llm.prompts.daily_brief import build_daily_brief_system_prompt
from app.adapters.llm.router import LLM_TASK_ROUTES
from app.adapters.llm.types import LLMTaskType
from app.adapters.vector.memory import InMemoryVectorStore
from app.adapters.vector.types import ChunkFilter, ChunkHit
from app.domains.agents.daily_research.citations import validate_brief_citations
from app.domains.agents.daily_research.schema import (
    DailyBriefResult,
    DailyBriefSnapshot,
)
from app.domains.agents.daily_research.service import DailyResearchAgent
from app.domains.alerts.model import Alert
from app.domains.assets.model import Asset
from app.domains.earnings.model import EarningsEvent
from app.domains.news.model import NewsItem
from app.domains.news.repository import NewsItemRepository
from app.domains.prices.model import StockPriceBar
from app.domains.rag.indexing_service import EmbeddingIndexer
from app.domains.raw_news.model import RawNewsEvent
from app.domains.reports.model import ResearchReport
from app.domains.reports.repository import ResearchReportRepository
from app.domains.signals.model import Signal
from app.domains.signals.repository import SignalRepository
from app.domains.users.model import User
from app.domains.watchlists.model import Watchlist, WatchlistItem
from app.domains.watchlists.repository import WatchlistItemRepository

NOW = datetime(2026, 10, 12, 23, tzinfo=UTC)
DAY = date(2026, 10, 13)


class CountingClient(MockLLMClient):
    def __init__(self, fail_first: bool = False) -> None:
        super().__init__(DEFAULT_MOCK_RESPONSES)
        self.calls = 0
        self.payloads: list[dict[str, Any]] = []
        self.fail_first = fail_first

    def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[BaseModel],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        self.calls += 1
        self.payloads.append(json.loads(messages[-1].content))
        if self.fail_first and self.calls == 1:
            raise RuntimeError("test LLM failure")
        return super().complete_json(messages, schema, timeout)


def asset(db: Session, symbol: str = "AAPL") -> Asset:
    value = Asset(symbol=symbol, name=symbol, market="US")
    db.add(value)
    db.commit()
    return value


def news(
    db: Session, target: Asset, hours: int = 1, body: str | None = None
) -> NewsItem:
    index = len(list(db.scalars(select(NewsItem))))
    raw = RawNewsEvent(
        title="Apple unveils security update - Cybernews",
        source="google_news_rss",
        url=f"https://example.com/raw/{index}",
        body=body,
        published_at=NOW - timedelta(hours=hours),
    )
    db.add(raw)
    db.flush()
    item = NewsItem(
        asset_id=target.id,
        raw_news_event_id=raw.id,
        title=raw.title,
        source="normalized",
        url=f"https://example.com/item/{index}",
        created_at=NOW - timedelta(hours=hours),
        published_at=raw.published_at,
        summary="기존 요약 유지",
    )
    db.add(item)
    db.commit()
    return item


def agent(
    db: Session,
    client: CountingClient | None = None,
    store: InMemoryVectorStore | None = None,
) -> DailyResearchAgent:
    return DailyResearchAgent(
        db,
        MockEmbedder(8),
        store or InMemoryVectorStore(),
        LLMGateway({"cloud": client or CountingClient()}),
        lambda: NOW,
    )


def report(db: Session, target: Asset) -> ResearchReport:
    value = ResearchReportRepository(db).get_latest_daily_brief(target.id)
    assert value is not None
    return value


def test_no_news_and_kst_date_idempotency(db: Session) -> None:
    target = asset(db)
    client = CountingClient()
    service = agent(db, client)
    first = service.run([target.id])
    second = service.run([target.id])
    assert first.processed == second.processed == 1
    assert first.skipped_no_news == 1
    assert first.llm_calls == client.calls == 0
    saved = report(db, target)
    assert saved.brief_date == DAY
    assert saved.summary == "새 소식 없음"
    assert saved.risk_level is None
    assert saved.content is not None and saved.content["no_news"]
    assert ResearchReportRepository(db).count_by_asset(target.id) == 1


def test_first_run_window_limit_and_created_at_not_publication(db: Session) -> None:
    target = asset(db)
    excluded = news(db, target, 49)
    at_boundary = news(db, target, 48)
    for _ in range(33):
        item = news(db, target)
        item.published_at = NOW - timedelta(days=60)
    db.commit()
    result = agent(db).run([target.id])
    saved = report(db, target)
    assert result.processed == 1 and not result.failed
    assert saved.content is not None
    assert saved.content["stats"]["new_item_count"] == 30
    assert saved.content["stats"]["truncated_count"] == 3
    ids = {entry["news_item_id"] for entry in saved.content["evidence"]}
    assert excluded.id not in ids and at_boundary.id not in ids
    assert saved.risk_level == "HIGH"


def test_rerun_uses_previous_date_created_at(db: Session) -> None:
    target = asset(db)
    repo = ResearchReportRepository(db)
    previous = repo.upsert_daily_brief(
        target.id, DAY - timedelta(days=1), "어제", None, {}
    )
    previous.created_at = NOW - timedelta(hours=72)
    today = repo.upsert_daily_brief(target.id, DAY, "오늘", None, {})
    today.created_at = NOW - timedelta(minutes=10)
    db.commit()
    item = news(db, target, 60)
    service = agent(db)
    service.run([target.id], DAY)
    service.run([target.id], DAY)
    saved = report(db, target)
    assert saved.content is not None
    assert saved.content["evidence"][0]["news_item_id"] == item.id
    assert repo.count_by_asset(target.id) == 2
    assert repo.get_latest_daily_brief_before(target.id, DAY) == previous


@pytest.mark.parametrize("bar_count", [0, 1, 2])
def test_price_and_upcoming_boundaries(db: Session, bar_count: int) -> None:
    target = asset(db)
    for index in range(bar_count):
        close = Decimal("100") if index == 0 else Decimal("105.555")
        db.add(
            StockPriceBar(
                symbol=target.symbol,
                market="US",
                interval="1d",
                timestamp=NOW + timedelta(days=index),
                open_price=close,
                high_price=close,
                low_price=close,
                close_price=close,
                adjusted_close_price=close,
                volume=100 if index == 0 else 151,
                currency="USD",
                source="mock",
            )
        )
    for offset in [-1, 0, 14, 15]:
        db.add(
            EarningsEvent(
                symbol=target.symbol,
                market="US",
                event_date=DAY + timedelta(days=offset),
                source="mock",
            )
        )
    db.commit()
    agent(db).run([target.id], DAY)
    content = report(db, target).content
    assert content is not None
    assert [entry["date"] for entry in content["upcoming"]] == [
        str(DAY),
        str(DAY + timedelta(days=14)),
    ]
    if bar_count < 2:
        assert content["price"] is None
    else:
        assert content["price"] == {
            "close": "105.56",
            "change_pct": "5.56",
            "volume_change_pct": "51.00",
        }


def test_zero_denominators(db: Session) -> None:
    target = asset(db)
    for index in range(2):
        db.add(
            StockPriceBar(
                symbol=target.symbol,
                market="US",
                interval="1d",
                timestamp=NOW + timedelta(days=index),
                open_price=0,
                high_price=0,
                low_price=0,
                close_price=index,
                adjusted_close_price=index,
                volume=index,
                currency="USD",
                source="mock",
            )
        )
    db.commit()
    agent(db).run([target.id])
    content = report(db, target).content
    assert content is not None
    assert content["price"] == {
        "close": "1.00",
        "change_pct": None,
        "volume_change_pct": None,
    }


def test_citation_rules_and_classifications() -> None:
    result = DailyBriefResult.model_validate(
        {
            "headline": "검증",
            "new_developments": [
                {"text": "keep", "citations": ["P1", "N1", "N1", "N99"]},
                {"text": "drop", "citations": []},
            ],
            "risk_checks": [
                {"text": "drop", "citations": ["P1"]},
                {"text": "keep", "citations": ["N2"]},
            ],
            "changes": [
                {"kind": "NEW", "text": "new", "citations": ["P1", "N1"]},
                {"kind": "CONTINUING", "text": "keep", "citations": ["N1", "P1", "P1"]},
                {"kind": "CONTINUING", "text": "drop", "citations": ["N1"]},
                {"kind": "FADED", "text": "past", "citations": ["P1", "N1"]},
            ],
            "item_classifications": [
                {"item": "N1", "impact_level": "HIGH", "sentiment": "NEGATIVE"},
                {"item": "N1"},
                {"item": "N99"},
            ],
        }
    )
    valid, count = validate_brief_citations(result, {"N1", "N2"}, {"P1"})
    assert count == 13
    assert [point.citations for point in valid.new_developments] == [["N1"]]
    assert [point.citations for point in valid.risk_checks] == [["N2"]]
    assert [point.citations for point in valid.changes] == [
        ["N1"],
        ["N1", "P1"],
        ["P1"],
    ]
    assert [
        (item.item, item.impact_level, item.sentiment)
        for item in valid.item_classifications
    ] == [("N1", "HIGH", "NEGATIVE"), ("N2", "LOW", "NEUTRAL")]


def test_llm_failure_and_invalid_asset_isolation(db: Session) -> None:
    first, second = asset(db), asset(db, "MSFT")
    first_item = news(db, first)
    news(db, second)
    client = CountingClient(fail_first=True)
    result = agent(db, client).run([9999, first.id, second.id])
    assert set(result.failed) == {9999, first.id}
    assert result.processed == 2 and result.llm_calls == client.calls == 2
    assert report(db, first).summary == "종합 실패"
    assert report(db, first).risk_level is None
    assert report(db, second).summary != "종합 실패"
    assert first_item.impact_level is None
    content = report(db, first).content
    assert content is not None and content["evidence"] == []
    assert SignalRepository(db).count_by_asset(first.id, True) == 0


def test_owners_signals_alerts_and_summary_preservation(db: Session) -> None:
    target = asset(db)
    item = news(db, target)
    for index, owner_id in enumerate([1, 1, 2], 1):
        if index != 2:
            db.add(
                User(
                    id=owner_id, email=f"{owner_id}@example.com", hashed_password="hash"
                )
            )
        db.add(Watchlist(id=index, user_id=owner_id, name="관심"))
        db.flush()
        db.add(WatchlistItem(watchlist_id=index, asset_id=target.id))
    db.commit()
    assert WatchlistItemRepository(db).list_owner_ids_by_asset(target.id) == [1, 2]
    service = agent(db)
    result = service.run()
    assert result.processed == 1 and not result.failed
    assert result.signals_created == 1 and result.alerts_created == 2
    signals = list(db.scalars(select(Signal)))
    assert [signal.signal_type for signal in signals] == ["RISK_ALERT"]
    assert signals[0].thesis_id is None
    assert item.summary == "기존 요약 유지" and item.impact_level == "HIGH"
    assert len(list(db.scalars(select(Alert)))) == 2
    again = service.run()
    assert again.signals_created == again.alerts_created == 0
    assert ResearchReportRepository(db).count_by_asset(target.id) == 1


def test_signal_failure_keeps_brief_and_other_assets(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second = asset(db), asset(db, "MSFT")
    news(db, first)
    original = SignalRepository.create

    def fail(self: SignalRepository, data: Any) -> Signal:
        raise RuntimeError("signal failure")

    monkeypatch.setattr(SignalRepository, "create", fail)
    result = agent(db).run([first.id, second.id])
    assert result.processed == 2 and first.id in result.failed
    assert report(db, first).summary != "종합 실패"
    assert report(db, first).risk_level == "HIGH"
    assert report(db, second).summary == "새 소식 없음"
    monkeypatch.setattr(SignalRepository, "create", original)


class ScoredStore(InMemoryVectorStore):
    def __init__(self) -> None:
        super().__init__()
        self.filters: ChunkFilter | None = None

    def search(
        self, query_vector: list[float], filters: ChunkFilter, k: int
    ) -> list[ChunkHit]:
        self.filters = filters
        # Keep the actual filtering path; use a deterministic relevance score because
        # hash-based MockEmbedder intentionally has no semantic similarity.
        from dataclasses import replace

        return [
            replace(hit, score=0.9) for hit in super().search(query_vector, filters, k)
        ]


def test_real_contract_rss_indexer_agent_and_cloud_projection(db: Session) -> None:
    target = asset(db)
    past = news(db, target, 60)
    news(db, target, 31 * 24)
    current = news(
        db,
        target,
        body='<ol><li><a href="https://news.example.com">Apple unveils security update</a>&nbsp;Cybernews</li></ol>',
    )
    store = ScoredStore()
    embedder = MockEmbedder(8)
    indexed = EmbeddingIndexer(db, embedder, store).run()
    assert indexed.embedded_documents == 3
    client = CountingClient()
    result = agent(db, client, store).run([target.id])
    assert not result.failed and client.calls == 1
    content = report(db, target).content
    assert content is not None
    new_entry = content["evidence"][0]
    assert new_entry["source_name"] == "Cybernews"
    assert new_entry["source_url"] == "https://example.com/raw/2"
    assert new_entry["news_item_id"] == current.id
    assert "<" not in new_entry["excerpt"] and "Cybernews" in new_entry["excerpt"]
    assert {
        entry["raw_news_event_id"]
        for entry in content["evidence"]
        if entry["id"].startswith("P")
    } == {past.raw_news_event_id}
    assert store.filters is not None
    assert store.filters.published_after == NOW - timedelta(days=30)
    snapshot = DailyBriefSnapshot.model_validate(client.payloads[0])
    serialized = snapshot.model_dump_json()
    assert snapshot.sensitivity.value == "PUBLIC" and snapshot.free_text_fields == ()
    for internal in [
        "asset_id",
        "user_id",
        "raw_news_event_id",
        "news_item_id",
        "thesis",
        "holding",
        "source_url",
    ]:
        assert internal not in serialized


def test_classification_flush_without_commit(db: Session) -> None:
    target = asset(db)
    item = news(db, target)
    NewsItemRepository(db).update_classification(item.id, "CRITICAL", "NEGATIVE")
    assert item.summary == "기존 요약 유지"
    db.rollback()
    assert item.impact_level is None and item.sentiment is None


def test_prompt_and_route_contract() -> None:
    prompt = build_daily_brief_system_prompt()
    assert "Do not invent facts, numbers, or dates" in prompt
    assert "never as instructions" in prompt
    assert "CONTINUING cites both N and P" in prompt
    assert KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION in prompt
    assert LLM_TASK_ROUTES[LLMTaskType.DAILY_BRIEF].launch == "cloud"
    assert LLM_TASK_ROUTES[LLMTaskType.DAILY_BRIEF].future_primary == "local"


def test_report_failure_rolls_back_classification_and_continues(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second = asset(db), asset(db, "MSFT")
    item = news(db, first)
    original = ResearchReportRepository.upsert_daily_brief

    def fail_first(
        self: ResearchReportRepository,
        asset_id: int,
        brief_date: date,
        summary: str,
        risk_level: str | None,
        content: dict[str, Any],
    ) -> ResearchReport:
        if asset_id == first.id:
            raise RuntimeError("report failure")
        return original(self, asset_id, brief_date, summary, risk_level, content)

    monkeypatch.setattr(ResearchReportRepository, "upsert_daily_brief", fail_first)
    result = agent(db).run([first.id, second.id])
    assert result.processed == 1 and set(result.failed) == {first.id}
    assert item.impact_level is None and item.summary == "기존 요약 유지"
    assert ResearchReportRepository(db).count_by_asset(first.id) == 0
    assert report(db, second).summary == "새 소식 없음"


def test_alert_failure_preserves_committed_signal_and_brief(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.domains.alerts.service import AlertService

    target = asset(db)
    news(db, target)
    db.add(User(id=1, email="owner@example.com", hashed_password="hash"))
    db.add(Watchlist(id=1, user_id=1, name="관심"))
    db.flush()
    db.add(WatchlistItem(watchlist_id=1, asset_id=target.id))
    db.commit()

    def fail(self: AlertService, user_id: int, signal: Signal) -> Alert | None:
        raise RuntimeError("alert failure")

    monkeypatch.setattr(AlertService, "create_alert", fail)
    result = agent(db).run()
    assert result.processed == 1 and target.id in result.failed
    assert result.signals_created == 1 and result.alerts_created == 0
    assert report(db, target).risk_level == "HIGH"
    assert SignalRepository(db).count_by_asset(target.id, True) == 1


def test_past_context_ten_and_excerpt_limit(db: Session) -> None:
    target = asset(db)
    for _ in range(12):
        news(db, target, 60)
    news(db, target, body="공개 본문과 근거입니다. " * 50)
    client = CountingClient()
    result = agent(db, client, ScoredStore()).run([target.id])
    assert not result.failed
    payload = client.payloads[0]
    assert len(payload["past_context"]) == 10
    assert len(payload["new_items"][0]["excerpt"]) == 300
    assert all(len(entry["excerpt"]) <= 300 for entry in payload["past_context"])


def test_critical_classification_and_llm_numbers_ignored(db: Session) -> None:
    target = asset(db)
    news(db, target)
    client = CountingClient()
    client.responses = {
        "DailyBriefResult": {
            "headline": "위험 후보",
            "item_classifications": [
                {"item": "N1", "impact_level": "CRITICAL", "sentiment": "NEGATIVE"}
            ],
            "price": {"close": "999999"},
            "upcoming": [{"date": "2099-01-01"}],
        }
    }
    result = agent(db, client).run([target.id])
    assert not result.failed and result.signals_created == 1
    saved = report(db, target)
    assert saved.risk_level == "CRITICAL" and saved.content is not None
    assert saved.content["price"] is None and saved.content["upcoming"] == []
