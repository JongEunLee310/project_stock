import re
import time
from html.parser import HTMLParser
from typing import Any

import httpx

from app.adapters.filings.base import (
    FilingFetchError,
    FilingProvider,
    FilingRef,
    FilingSectionText,
)
from app.domains.knowledge.types import FilingSection

_BLOCKS = {"p", "div", "tr", "li", "br", "table", "h1", "h2", "h3", "h4", "h5", "h6"}
_HEADINGS = re.compile(r"^item\s*(1[abc]?|2)\s*[.:]", re.IGNORECASE | re.MULTILINE)


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in _BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in _BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def extract_10k_sections(html_text: str) -> list[FilingSectionText]:
    parser = _TextParser()
    parser.feed(html_text)
    lines = (
        re.sub(r"\s+", " ", line).strip() for line in "".join(parser.parts).splitlines()
    )
    text = "\n".join(line for line in lines if line)
    headings = list(_HEADINGS.finditer(text))
    result = []
    for number, section in [
        ("1", FilingSection.BUSINESS),
        ("1a", FilingSection.RISK_FACTORS),
    ]:
        candidates = []
        for i, match in enumerate(headings):
            if match.group(1).lower() != number:
                continue
            end = next(
                (
                    following.start()
                    for following in headings[i + 1 :]
                    if following.group(1).lower() != number
                ),
                len(text),
            )
            candidates.append(text[match.start() : end].strip())
        longest = max(candidates, key=len, default="")
        if len(longest) >= 500:
            result.append(
                FilingSectionText(
                    section=section,
                    heading=longest.split("\n", 1)[0],
                    text=longest[:200_000],
                    truncated=len(longest) > 200_000,
                )
            )
    return result


class EdgarFilingProvider(FilingProvider):
    def __init__(
        self,
        user_agent: str,
        client: httpx.Client | None = None,
        min_interval_seconds: float = 0.2,
    ) -> None:
        self.user_agent = user_agent
        self.client = client
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self._last_request: float | None = None
        self._tickers: dict[str, str] | None = None

    def _get(self, url: str) -> httpx.Response:
        if self._last_request is not None:
            time.sleep(
                max(
                    0.0,
                    self.min_interval_seconds - (time.monotonic() - self._last_request),
                )
            )
        try:
            headers = {"User-Agent": self.user_agent}
            if self.client is not None:
                response = self.client.get(url, headers=headers)
            else:
                with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                    response = client.get(url, headers=headers)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise FilingFetchError(f"EDGAR request failed: {url}: {exc}") from exc
        finally:
            self._last_request = time.monotonic()

    def _json(self, url: str) -> Any:
        try:
            return self._get(url).json()
        except ValueError as exc:
            raise FilingFetchError(f"Invalid EDGAR JSON: {url}") from exc

    def list_annual_reports(self, symbol: str, limit: int) -> list[FilingRef]:
        from datetime import date

        if limit <= 0:
            return []
        try:
            if self._tickers is None:
                entries = self._json("https://www.sec.gov/files/company_tickers.json")
                self._tickers = {
                    entry["ticker"].upper(): str(int(entry["cik_str"]))
                    for entry in entries.values()
                }
            cik = self._tickers.get(symbol.upper())
            if cik is None:
                raise FilingFetchError(f"No EDGAR CIK mapping for {symbol}")
            data = self._json(
                f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
            )
            recent = data["filings"]["recent"]
            keys = (
                "form",
                "accessionNumber",
                "filingDate",
                "reportDate",
                "primaryDocument",
            )
            if any(not isinstance(recent[key], list) for key in keys):
                raise ValueError("Submission columns must be lists")
            rows = zip(*(recent[key] for key in keys), strict=True)
            reports = []
            for form, accession, filed, reported, document in rows:
                if form != "10-K":
                    continue
                reports.append(
                    FilingRef(
                        source="edgar",
                        company_id=cik,
                        accession=accession,
                        form=form,
                        filed_date=date.fromisoformat(filed),
                        report_date=date.fromisoformat(reported),
                        document_url=f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{document}",
                    )
                )
            return sorted(
                reports, key=lambda ref: (ref.filed_date, ref.accession), reverse=True
            )[:limit]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise FilingFetchError(f"Invalid EDGAR response for {symbol}") from exc

    def fetch_sections(self, ref: FilingRef) -> list[FilingSectionText]:
        return extract_10k_sections(self._get(ref.document_url).text)
