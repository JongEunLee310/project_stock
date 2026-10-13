import hashlib
from collections.abc import Callable

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.factory import get_filing_provider
from app.adapters.filings.base import FilingProvider
from app.domains.assets.repository import AssetRepository
from app.domains.knowledge.repository import KnowledgeDocumentRepository
from app.domains.knowledge.schema import KnowledgeDocumentCreate
from app.domains.knowledge.types import FilingSection, KnowledgeKind
from app.domains.watchlists.repository import WatchlistItemRepository


class FilingCollectionResult(BaseModel):
    saved: int = 0
    skipped_existing: int = 0
    missing_sections: dict[int, list[str]] = Field(default_factory=dict)
    failed: dict[int, str] = Field(default_factory=dict)
    unsupported: list[int] = Field(default_factory=list)


class FilingCollectionService:
    def __init__(
        self,
        db: Session,
        provider_factory: Callable[[str], FilingProvider | None] = get_filing_provider,
    ) -> None:
        self.db = db
        self.provider_factory = provider_factory
        self.documents = KnowledgeDocumentRepository(db)

    def collect(self, asset_ids: list[int] | None = None) -> FilingCollectionResult:
        result = FilingCollectionResult()
        targets = (
            WatchlistItemRepository(self.db).list_watched_asset_ids()
            if asset_ids is None
            else asset_ids
        )
        providers: dict[str, FilingProvider | None] = {}
        for asset_id in dict.fromkeys(targets):
            saved = skipped = 0
            missing: list[str] = []
            try:
                asset = AssetRepository(self.db).get_by_id(asset_id)
                if asset is None:
                    raise ValueError(f"Asset {asset_id} not found")
                if asset.market not in {"NASDAQ", "NYSE"}:
                    result.unsupported.append(asset_id)
                    continue
                if asset.market not in providers:
                    providers[asset.market] = self.provider_factory(asset.market)
                provider = providers[asset.market]
                if provider is None:
                    result.unsupported.append(asset_id)
                    continue
                for ref in provider.list_annual_reports(asset.symbol, limit=2):
                    external_ids = {
                        section: f"{ref.source}:{ref.accession}:{section.value}"
                        for section in FilingSection
                    }
                    existing = {
                        section
                        for section, external_id in external_ids.items()
                        if self.documents.get_by_external_id(
                            KnowledgeKind.FILING_SECTION, external_id
                        )
                        is not None
                    }
                    skipped += len(existing)
                    if len(existing) == len(FilingSection):
                        continue
                    sections = {
                        section.section: section
                        for section in provider.fetch_sections(ref)
                    }
                    for section in FilingSection:
                        if section in existing:
                            continue
                        extracted = sections.get(section)
                        if extracted is None:
                            missing.append(f"{ref.accession}:{section.value}")
                            continue
                        metadata: dict[str, str | int | bool] = {
                            "form": ref.form,
                            "cik": ref.company_id,
                            "accession": ref.accession,
                            "report_date": ref.report_date.isoformat(),
                            "fiscal_year": ref.report_date.year,
                            "section": section.value,
                        }
                        if extracted.truncated:
                            metadata["truncated"] = True
                        heading = (
                            "Item 1. Business"
                            if section == FilingSection.BUSINESS
                            else "Item 1A. Risk Factors"
                        )
                        self.documents.add(
                            KnowledgeDocumentCreate(
                                kind=KnowledgeKind.FILING_SECTION,
                                title=f"{asset.name} 10-K FY{ref.report_date.year} — {heading}",
                                content=extracted.text,
                                asset_id=asset_id,
                                source_name="SEC EDGAR",
                                source_url=ref.document_url,
                                license_note="U.S. government public filing",
                                effective_date=ref.filed_date,
                                external_id=external_ids[section],
                                content_hash=hashlib.sha256(
                                    extracted.text.encode("utf-8")
                                ).hexdigest(),
                                metadata_=metadata,
                            )
                        )
                        saved += 1
                self.db.commit()
                result.saved += saved
                result.skipped_existing += skipped
                if missing:
                    result.missing_sections[asset_id] = missing
            except Exception as exc:
                self.db.rollback()
                result.failed[asset_id] = str(exc)
        return result
