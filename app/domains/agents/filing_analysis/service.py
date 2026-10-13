import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.prompts.filing_analysis import build_filing_analysis_system_prompt
from app.adapters.llm.types import LLMTaskType
from app.adapters.obsidian.writer import FilingAnalysisNote, ObsidianWriter
from app.domains.agents.filing_analysis.citations import validate_filing_citations
from app.domains.agents.filing_analysis.diff import diff_sections
from app.domains.agents.filing_analysis.projection import build_filing_diff_snapshot
from app.domains.agents.filing_analysis.schema import (
    FilingAnalysisContent,
    FilingAnalysisResult,
    FilingEvidence,
    FilingReference,
    FilingSection,
    FilingSectionAnalysis,
    FilingSectionContent,
    Importance,
)
from app.domains.alerts.service import AlertService
from app.domains.assets.repository import AssetRepository
from app.domains.knowledge.model import KnowledgeDocument
from app.domains.knowledge.repository import KnowledgeDocumentRepository
from app.domains.knowledge.types import KnowledgeKind
from app.domains.reports.repository import ResearchReportRepository
from app.domains.reports.types import ReportType
from app.domains.signals.repository import SignalRepository
from app.domains.signals.schema import SignalCreate
from app.domains.signals.types import SignalType
from app.domains.watchlists.repository import WatchlistItemRepository

logger = logging.getLogger(__name__)
IMPORTANCE_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
SECTIONS: tuple[FilingSection, ...] = ("BUSINESS", "RISK_FACTORS")


def _reference(documents: dict[str, KnowledgeDocument]) -> FilingReference:
    doc = next(iter(documents.values()))
    return FilingReference(
        accession=doc.metadata_["accession"],
        fiscal_year=doc.metadata_["fiscal_year"],
        filed_date=doc.effective_date,
        source_url=doc.source_url,
        knowledge_document_id={section: item.id for section, item in documents.items()},
    )


def _importance(section: FilingSectionContent) -> Importance:
    return max(
        (change.importance for change in section.changes),
        key=IMPORTANCE_ORDER.__getitem__,
        default="LOW",
    )


class FilingAnalysisAgent:
    def __init__(
        self,
        db: Session,
        gateway: LLMGateway,
        obsidian_writer: ObsidianWriter | None = None,
    ) -> None:
        self.db = db
        self.gateway = gateway
        self.obsidian_writer = obsidian_writer

    def run(self, asset_ids: list[int] | None = None) -> FilingAnalysisResult:
        targets = (
            WatchlistItemRepository(self.db).list_watched_asset_ids()
            if asset_ids is None
            else list(dict.fromkeys(asset_ids))
        )
        result = FilingAnalysisResult()
        for asset_id in targets:
            try:
                self._run_asset(asset_id, result)
            except Exception as exc:
                self.db.rollback()
                result.failed[asset_id] = str(exc)
                logger.warning(
                    "Filing analysis failed: asset_id=%s", asset_id, exc_info=True
                )
        return result

    def _run_asset(self, asset_id: int, result: FilingAnalysisResult) -> None:
        asset = AssetRepository(self.db).get_by_id(asset_id)
        if asset is None:
            raise ValueError("asset not found")
        symbol, asset_name = asset.symbol, asset.name
        # Read all available sections so an incomplete newest filing cannot hide
        # the previous accession behind an arbitrary document-count cutoff.
        documents = KnowledgeDocumentRepository(self.db).list_by_asset(
            asset_id,
            KnowledgeKind.FILING_SECTION,
            limit=2**31 - 1,
        )
        groups: dict[str, dict[str, KnowledgeDocument]] = {}
        for doc in documents:
            accession = doc.metadata_.get("accession")
            section = doc.metadata_.get("section")
            if isinstance(accession, str) and section in SECTIONS:
                groups.setdefault(accession, {}).setdefault(section, doc)
        if len(groups) < 2:
            result.skipped_no_pair += 1
            return
        # Repository order is effective_date descending, id descending.
        new_docs, old_docs = list(groups.values())[:2]
        source_ref = f"edgar:{next(iter(new_docs.values())).metadata_['accession']}"
        reports = ResearchReportRepository(self.db)
        if reports.get_by_source_ref(asset_id, ReportType.FILING_ANALYSIS, source_ref):
            result.skipped_existing += 1
            return
        old_ref, new_ref = _reference(old_docs), _reference(new_docs)
        sections: dict[str, FilingSectionContent] = {}
        evidence: dict[str, dict[str, FilingEvidence]] = {}
        failures: list[str] = []
        for section in SECTIONS:
            stored = FilingSectionContent()
            sections[section] = stored
            evidence[section] = {}
            try:
                if section not in old_docs or section not in new_docs:
                    raise ValueError("섹션 없음")
                old_doc, new_doc = old_docs[section], new_docs[section]
                diff = diff_sections(old_doc.content, new_doc.content)
                diff.section = section
                stored.diff_stats = diff.stats
                snapshot = build_filing_diff_snapshot(
                    diff,
                    symbol=asset.symbol,
                    asset_name=asset.name,
                    section=section,
                    old_fiscal_year=old_ref.fiscal_year,
                    new_fiscal_year=new_ref.fiscal_year,
                )
                stored.truncated_count = snapshot.truncated_count
                allowed = (
                    {item.id for item in snapshot.added}
                    | {item.id for item in snapshot.removed}
                    | {item.id for item in snapshot.modified}
                )
                result.llm_calls += 1
                completion = self.gateway.complete_json(
                    LLMTaskType.FILING_ANALYSIS,
                    snapshot,
                    FilingSectionAnalysis,
                    build_filing_analysis_system_prompt(),
                )
                analysis, corrections = validate_filing_citations(
                    FilingSectionAnalysis.model_validate(completion.output),
                    allowed,
                )
                stored.headline = analysis.headline
                stored.changes = analysis.changes
                stored.limitations = analysis.limitations
                stored.citation_corrections = corrections
                cited = {
                    citation
                    for change in stored.changes
                    for citation in change.citations
                }
                for added in diff.added:
                    if added.id in cited:
                        evidence[section][added.id] = FilingEvidence(
                            new_text=added.text,
                            new_knowledge_document_id=new_doc.id,
                        )
                for removed in diff.removed:
                    if removed.id in cited:
                        evidence[section][removed.id] = FilingEvidence(
                            old_text=removed.text,
                            old_knowledge_document_id=old_doc.id,
                        )
                for modified in diff.modified:
                    if modified.id in cited:
                        evidence[section][modified.id] = FilingEvidence(
                            old_text=modified.old_text,
                            new_text=modified.new_text,
                            old_knowledge_document_id=old_doc.id,
                            new_knowledge_document_id=new_doc.id,
                        )
            except Exception as exc:
                stored.failed = str(exc)
                failures.append(f"{section}: {exc}")
                logger.warning(
                    "Filing section failed: asset_id=%s section=%s",
                    asset_id,
                    section,
                    exc_info=True,
                )
        if failures:
            result.failed[asset_id] = "; ".join(failures)
        successful = [
            section for section in sections.values() if section.failed is None
        ]
        if not successful:
            return
        leading = max(
            successful, key=lambda section: IMPORTANCE_ORDER[_importance(section)]
        )
        content = FilingAnalysisContent(
            old_filing=old_ref,
            new_filing=new_ref,
            headline=leading.headline,
            sections=sections,
            evidence=evidence,
            max_importance=_importance(leading),
        )
        report = reports.create_filing_analysis(
            asset_id,
            source_ref,
            content.headline,
            content.max_importance,
            content.model_dump(mode="json"),
        )
        report_id = report.id
        self.db.commit()
        result.analyzed += 1
        if content.max_importance == "HIGH":
            try:
                signal = SignalRepository(self.db).create(
                    SignalCreate(
                        asset_id=asset_id,
                        signal_type=SignalType.RISK_ALERT,
                        score=60,
                        risk_level="HIGH",
                        reason=content.headline,
                        key_points=[
                            change.title
                            for section in successful
                            for change in section.changes
                            if change.importance == "HIGH"
                        ],
                        evidence={"report_id": report_id, "source_ref": source_ref},
                    )
                )
                result.signals_created += 1
                owners = WatchlistItemRepository(self.db).list_owner_ids_by_asset(
                    asset_id
                )
                alerts = AlertService(self.db)
                for owner in owners:
                    if alerts.create_alert(owner, signal) is not None:
                        result.alerts_created += 1
            except Exception as exc:
                self.db.rollback()
                result.failed[asset_id] = "; ".join([*failures, f"신호·알림: {exc}"])
                logger.warning(
                    "Filing signals failed: asset_id=%s", asset_id, exc_info=True
                )
        if self.obsidian_writer is not None:
            try:
                self.obsidian_writer.write_filing_analysis_note(
                    FilingAnalysisNote(
                        symbol=symbol,
                        asset_name=asset_name,
                        generated_at=datetime.now(UTC),
                        content=content,
                    )
                )
                result.notes_written += 1
            except (OSError, ValueError) as exc:
                result.note_failures[asset_id] = str(exc)
