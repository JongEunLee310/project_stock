from datetime import date

from app.adapters.filings.base import FilingProvider, FilingRef, FilingSectionText
from app.domains.knowledge.types import FilingSection


class MockFilingProvider(FilingProvider):
    def list_annual_reports(self, symbol: str, limit: int) -> list[FilingRef]:
        return [
            FilingRef(
                source="edgar",
                company_id="0",
                accession=f"mock-{symbol.upper()}-{year}",
                form="10-K",
                filed_date=date(year + 1, 2, 1),
                report_date=date(year, 12, 31),
                document_url=f"https://example.com/filings/{symbol.upper()}/{year}",
            )
            for year in (2025, 2024)
        ][: max(0, limit)]

    def fetch_sections(self, ref: FilingRef) -> list[FilingSectionText]:
        return [
            FilingSectionText(
                FilingSection.BUSINESS, "Item 1. Business", "Mock business. " * 50
            ),
            FilingSectionText(
                FilingSection.RISK_FACTORS, "Item 1A. Risk Factors", "Mock risks. " * 50
            ),
        ]
