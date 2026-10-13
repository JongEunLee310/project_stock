import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.adapters.embedding.base import Embedder
from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.prompts.daily_brief import build_daily_brief_system_prompt
from app.adapters.llm.types import LLMTaskType
from app.adapters.obsidian.writer import (
    DailyBriefNote,
    DailyIndexEntry,
    DailySignalLine,
    ObsidianWriter,
)
from app.adapters.vector.base import VectorStore
from app.adapters.vector.types import ChunkFilter
from app.domains.agents.daily_research.citations import validate_brief_citations
from app.domains.agents.daily_research.schema import (
    BriefEvidence,
    BriefEvidenceProjection,
    BriefPrice,
    BriefStats,
    BriefUpcoming,
    DailyBriefContent,
    DailyBriefResult,
    DailyBriefSnapshot,
    DailyResearchResult,
)
from app.domains.alerts.service import AlertService
from app.domains.assets.repository import AssetRepository
from app.domains.earnings.repository import EarningsRepository
from app.domains.news.model import NewsItem
from app.domains.news.repository import NewsItemRepository
from app.domains.prices.repository import PriceBarRepository
from app.domains.rag.indexing import clean_body_text
from app.domains.rag.indexing_service import EmbeddingIndexer
from app.domains.rag.retrieval import CANDIDATE_K, extract_source_name, postprocess_hits
from app.domains.rag.types import ChunkSourceType
from app.domains.raw_news.repository import RawNewsEventRepository
from app.domains.reports.repository import ResearchReportRepository
from app.domains.signals.repository import SignalRepository
from app.domains.signals.rules import RuleContext, RuleEngine, default_rules
from app.domains.watchlists.repository import WatchlistItemRepository

logger = logging.getLogger(__name__)
FIRST_RUN_LOOKBACK_HOURS = 48
MAX_NEW_ITEMS = 30
PAST_CONTEXT_DAYS = 30
PAST_CONTEXT_K = 10
UPCOMING_DAYS = 14
EXCERPT_LENGTH = 300


def utc_now() -> datetime:
    return datetime.now(UTC)


def _decimal_string(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _change(current: Decimal, previous: Decimal) -> str | None:
    if previous == 0:
        return None
    return _decimal_string((current - previous) / previous * 100)


class DailyResearchAgent:
    def __init__(
        self,
        db: Session,
        embedder: Embedder,
        vector_store: VectorStore,
        gateway: LLMGateway,
        now: Callable[[], datetime] = utc_now,
        obsidian_writer: ObsidianWriter | None = None,
    ) -> None:
        self.db = db
        self.embedder = embedder
        self.vector_store = vector_store
        self.gateway = gateway
        self.now = now
        self.obsidian_writer = obsidian_writer

    def run(
        self, asset_ids: list[int] | None = None, brief_date: date | None = None
    ) -> DailyResearchResult:
        generated_at = self.now()
        brief_date = (
            brief_date or generated_at.astimezone(ZoneInfo("Asia/Seoul")).date()
        )
        targets = (
            WatchlistItemRepository(self.db).list_watched_asset_ids()
            if asset_ids is None
            else list(dict.fromkeys(asset_ids))
        )
        result = DailyResearchResult()
        entries: list[DailyIndexEntry] = []
        for asset_id in targets:
            try:
                entries.append(
                    self._run_asset(asset_id, brief_date, generated_at, result)
                )
            except Exception as exc:
                self.db.rollback()
                result.failed[asset_id] = str(exc)
                logger.warning(
                    "Daily research failed: asset_id=%s", asset_id, exc_info=True
                )
                if self.obsidian_writer is not None:
                    try:
                        asset = AssetRepository(self.db).get_by_id(asset_id)
                    except Exception:
                        self.db.rollback()
                        asset = None
                    entries.append(
                        DailyIndexEntry(
                            symbol=asset.symbol if asset else str(asset_id),
                            asset_name=asset.name if asset else str(asset_id),
                            headline="",
                            new_item_count=0,
                            note_path=None,
                            failed_reason=str(exc),
                        )
                    )
        if asset_ids is None and self.obsidian_writer is not None:
            try:
                self.obsidian_writer.write_daily_index(brief_date, entries)
                result.notes_written += 1
            except (OSError, ValueError) as exc:
                result.note_failures["index"] = str(exc)
        return result

    def _run_asset(
        self,
        asset_id: int,
        brief_date: date,
        generated_at: datetime,
        outcome: DailyResearchResult,
    ) -> DailyIndexEntry:
        asset = AssetRepository(self.db).get_by_id(asset_id)
        if asset is None:
            raise ValueError("asset not found")
        symbol, asset_name = asset.symbol, asset.name
        reports = ResearchReportRepository(self.db)
        previous = reports.get_latest_daily_brief_before(asset_id, brief_date)
        start = (
            previous.created_at
            if previous
            else generated_at - timedelta(hours=FIRST_RUN_LOOKBACK_HOURS)
        )
        news = NewsItemRepository(self.db)
        items = news.list_by_asset_created_after(asset_id, start, MAX_NEW_ITEMS)
        total = news.count_by_asset_created_after(asset_id, start)
        evidence = self._new_evidence(items)
        if items:
            # The indexer scans from the beginning; finish all pages so a backlog cannot
            # leave the current asset's new sources unindexed.
            indexer = EmbeddingIndexer(self.db, self.embedder, self.vector_store)
            while indexer.run().has_more:
                pass
            past = self._past_evidence(asset_id, items, start)
        else:
            past = []
        bars = PriceBarRepository(self.db).list_recent(
            asset.symbol, asset.market, "1d", 2
        )
        price = None
        if len(bars) == 2:
            old, latest = bars
            price = BriefPrice(
                as_of=latest.timestamp.date(),
                stale=(brief_date - latest.timestamp.date()).days > 4,
                close=_decimal_string(latest.close_price),
                change_pct=_change(latest.close_price, old.close_price),
                volume_change_pct=_change(Decimal(latest.volume), Decimal(old.volume)),
            )
        upcoming = [
            BriefUpcoming(date=event.event_date)
            for event in EarningsRepository(self.db).get_events(
                asset.symbol,
                asset.market,
                brief_date,
                brief_date + timedelta(days=UPCOMING_DAYS),
            )
        ]
        synthesis = DailyBriefResult(headline="새 소식 없음")
        corrections = 0
        synthesis_failed = False
        if items:
            snapshot = DailyBriefSnapshot(
                symbol=asset.symbol,
                asset_name=asset.name,
                market=asset.market,
                brief_date=brief_date,
                new_items=[self._project(item) for item in evidence],
                past_context=[self._project(item) for item in past],
                price=price,
                upcoming=upcoming,
            )
            outcome.llm_calls += 1
            try:
                completion = self.gateway.complete_json(
                    LLMTaskType.DAILY_BRIEF,
                    snapshot,
                    DailyBriefResult,
                    build_daily_brief_system_prompt(),
                )
                synthesis = DailyBriefResult.model_validate(completion.output)
            except Exception as exc:
                synthesis_failed = True
                outcome.failed[asset_id] = f"LLM: {exc}"
                synthesis = DailyBriefResult(headline="종합 실패")
            if not synthesis_failed:
                synthesis, corrections = validate_brief_citations(
                    synthesis,
                    {item.id for item in evidence},
                    {item.id for item in past},
                )
                logger.info("Daily brief citation corrections: %s", corrections)
                if corrections >= len(items):
                    logger.warning(
                        "Daily brief excessive citation corrections: "
                        "asset_id=%s corrections=%s new_item_count=%s",
                        asset_id,
                        corrections,
                        len(items),
                    )
                item_ids = {entry.id: entry.news_item_id for entry in evidence}
                for classification in synthesis.item_classifications:
                    item_id = item_ids[classification.item]
                    assert item_id is not None
                    news.update_classification(
                        item_id, classification.impact_level, classification.sentiment
                    )
        levels: list[str] = [
            entry.impact_level for entry in synthesis.item_classifications
        ]
        risk_level: str | None = (
            max(
                levels,
                key=lambda level: {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}[
                    level
                ],
            )
            if levels
            else None
        )
        content = DailyBriefContent(
            headline=synthesis.headline,
            new_developments=synthesis.new_developments,
            changes=synthesis.changes,
            risk_checks=synthesis.risk_checks,
            limitations=synthesis.limitations,
            evidence=[] if synthesis_failed else evidence + past,
            price=price,
            upcoming=upcoming,
            stats=BriefStats(
                new_item_count=len(items),
                truncated_count=total - len(items),
                past_context_count=len(past),
                citation_corrections=corrections,
            ),
            no_news=not items,
        )
        reports.upsert_daily_brief(
            asset_id,
            brief_date,
            synthesis.headline,
            risk_level,
            content.model_dump(mode="json"),
        )
        self.db.commit()
        outcome.processed += 1
        if not items:
            outcome.skipped_no_news += 1
        signals: list[DailySignalLine] = []
        if items and not synthesis_failed:
            try:
                engine = RuleEngine(default_rules(), SignalRepository(self.db))
                alerts = AlertService(self.db)
                owners = WatchlistItemRepository(self.db).list_owner_ids_by_asset(
                    asset_id
                )
                for item in items:
                    for signal in engine.run(RuleContext(asset_id, item)):
                        outcome.signals_created += 1
                        signals.append(
                            DailySignalLine(
                                signal.signal_type,
                                signal.score,
                                signal.reason,
                            )
                        )
                        for owner in owners:
                            if alerts.create_alert(owner, signal) is not None:
                                outcome.alerts_created += 1
            except Exception as exc:
                self.db.rollback()
                outcome.failed[asset_id] = str(exc)
                logger.warning(
                    "Daily research signals failed: asset_id=%s",
                    asset_id,
                    exc_info=True,
                )
        note_path = None
        if self.obsidian_writer is not None:
            try:
                note_path = self.obsidian_writer.write_daily_brief_note(
                    DailyBriefNote(
                        symbol=symbol,
                        asset_name=asset_name,
                        brief_date=brief_date,
                        generated_at=generated_at,
                        content=content,
                        signals=signals,
                    )
                )
                outcome.notes_written += 1
            except (OSError, ValueError) as exc:
                outcome.note_failures[asset_id] = str(exc)
        reasons = [
            reason
            for reason in (
                outcome.failed.get(asset_id),
                outcome.note_failures.get(asset_id),
            )
            if reason is not None
        ]
        return DailyIndexEntry(
            symbol=symbol,
            asset_name=asset_name,
            headline=content.headline,
            new_item_count=content.stats.new_item_count,
            note_path=note_path,
            failed_reason="; ".join(reasons) if reasons else None,
        )

    def _project(self, evidence: BriefEvidence) -> BriefEvidenceProjection:
        return BriefEvidenceProjection(
            **evidence.model_dump(
                include={"id", "title", "source_name", "published_at", "excerpt"}
            )
        )

    def _new_evidence(self, items: list[NewsItem]) -> list[BriefEvidence]:
        events = {
            event.id: event
            for event in RawNewsEventRepository(self.db).list_by_ids(
                [
                    item.raw_news_event_id
                    for item in items
                    if item.raw_news_event_id is not None
                ]
            )
        }
        evidence: list[BriefEvidence] = []
        for index, item in enumerate(items, 1):
            event = (
                events.get(item.raw_news_event_id) if item.raw_news_event_id else None
            )
            title = event.title if event else item.title
            source = event.source if event else item.source
            body = clean_body_text(event.body) if event and event.body else ""
            evidence.append(
                BriefEvidence(
                    id=f"N{index}",
                    title=title,
                    source_name=extract_source_name(title, source),
                    published_at=event.published_at if event else item.published_at,
                    excerpt=(body or title)[:EXCERPT_LENGTH],
                    raw_news_event_id=item.raw_news_event_id,
                    news_item_id=item.id,
                    source_url=event.url if event else item.url,
                )
            )
        return evidence

    def _past_evidence(
        self, asset_id: int, items: list[NewsItem], start: datetime
    ) -> list[BriefEvidence]:
        vector = self.embedder.embed(["\n".join(item.title for item in items)])[0]
        new_sources = {item.raw_news_event_id for item in items}
        hits = postprocess_hits(
            [
                hit
                for hit in self.vector_store.search(
                    vector,
                    ChunkFilter(
                        embedding_model=self.embedder.model_name,
                        asset_id=asset_id,
                        source_types=(ChunkSourceType.NEWS,),
                        published_after=start - timedelta(days=PAST_CONTEXT_DAYS),
                        published_before=start,
                    ),
                    CANDIDATE_K + len(new_sources) * 2,
                )
                if hit.source_id not in new_sources
            ],
            final_evidence_k=PAST_CONTEXT_K,
        )
        events = {
            event.id: event
            for event in RawNewsEventRepository(self.db).list_by_ids(
                [hit.source_id for hit in hits]
            )
        }
        evidence: list[BriefEvidence] = []
        for hit in hits:
            event = events.get(hit.source_id)
            if event is None:
                continue
            evidence.append(
                BriefEvidence(
                    id=f"P{len(evidence) + 1}",
                    title=event.title,
                    source_name=extract_source_name(event.title, event.source),
                    published_at=event.published_at,
                    excerpt=hit.content[:EXCERPT_LENGTH],
                    raw_news_event_id=event.id,
                    news_item_id=None,
                    source_url=event.url,
                )
            )
        return evidence
