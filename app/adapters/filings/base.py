from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from app.domains.knowledge.types import FilingSection


class FilingFetchError(Exception):
    """공시 공급자의 요청 또는 응답 처리 실패."""


@dataclass(frozen=True)
class FilingRef:
    source: str
    company_id: str
    accession: str
    form: str
    filed_date: date
    report_date: date
    document_url: str


@dataclass(frozen=True)
class FilingSectionText:
    section: FilingSection
    heading: str
    text: str
    truncated: bool = False


class FilingProvider(ABC):
    @abstractmethod
    def list_annual_reports(self, symbol: str, limit: int) -> list[FilingRef]:
        raise NotImplementedError

    @abstractmethod
    def fetch_sections(self, ref: FilingRef) -> list[FilingSectionText]:
        raise NotImplementedError
