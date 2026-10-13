from datetime import date
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.factory import get_filing_provider
from app.adapters.filings.base import FilingFetchError, FilingSectionText
from app.adapters.filings.edgar import EdgarFilingProvider, extract_10k_sections
from app.adapters.filings.mock import MockFilingProvider
from app.core.config import settings
from app.domains.assets.model import Asset
from app.domains.jobs.model import JobRun
from app.domains.knowledge.filing_service import (
    FilingCollectionResult,
    FilingCollectionService,
)
from app.domains.knowledge.model import KnowledgeDocument
from app.domains.knowledge.types import FilingSection
from app.scheduler.registry import default_scheduler_registry
from app.worker.jobs.filings import collect_filings_job


@pytest.mark.parametrize(
    "heading",
    ["ITEM 1A.RISK FACTORS", "Item\xa01A: Risk Factors", "item1a. Risk Factors"],
)
def test_extract_longest_and_inline_reference(heading: str) -> None:
    html = (
        "<table><tr><td>Item 1. Business</td></tr><tr><td>Item 1A. Risk Factors</td></tr>"
        "<tr><td>Item 2. Properties</td></tr></table>"
        "<h1>Item 1. Business</h1><div>"
        + "Business operations. "
        * 40
        + "Refer to “Item 1A. Risk Factors” for details.</div>"
        f"<h2>{heading}</h2><p>" + "Significant risks. " * 40 + "</p>"
        "<div>Item 1B. Unresolved comments</div><p>excluded</p>"
    )
    sections = extract_10k_sections(html)
    assert [s.section for s in sections] == list(FilingSection)
    assert "Refer to" in sections[0].text
    assert "Significant risks." not in sections[0].text
    assert "excluded" not in sections[1].text
    assert all(not s.truncated for s in sections)


def test_extract_limits() -> None:
    assert extract_10k_sections("<p>Item 1. Business</p><p>short</p>") == []
    sections = extract_10k_sections(
        "<p>Item 1. Business</p><p>" + "x" * 200_001 + "</p><p>Item 2. Properties</p>"
    )
    assert len(sections[0].text) == 200_000
    assert sections[0].truncated


def test_edgar_requests_and_cache() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(
                200, json={"0": {"ticker": "AAPL", "cik_str": 320193}}
            )
        if request.url.host == "data.sec.gov":
            assert request.url.path == "/submissions/CIK0000320193.json"
            return httpx.Response(
                200,
                json={
                    "filings": {
                        "recent": {
                            "form": ["10-K", "10-Q", "10-K/A", "10-K", "10-K"],
                            "accessionNumber": ["old-1", "q", "a", "new-1", "middle-1"],
                            "filingDate": [
                                "2023-01-01",
                                "2026-01-01",
                                "2026-01-01",
                                "2025-01-01",
                                "2024-01-01",
                            ],
                            "reportDate": ["2022-12-31"] * 5,
                            "primaryDocument": ["report.htm"] * 5,
                        }
                    }
                },
            )
        assert (
            str(request.url)
            == "https://www.sec.gov/Archives/edgar/data/320193/new1/report.htm"
        )
        return httpx.Response(
            200, text="<h1>Item 1. Business</h1><p>" + "x" * 600 + "</p>"
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = EdgarFilingProvider("Test contact@example.com", client, 0)
        refs = provider.list_annual_reports("aapl", 2)
        assert [ref.accession for ref in refs] == ["new-1", "middle-1"]
        assert refs[0].company_id == "320193"
        assert len(provider.fetch_sections(refs[0])) == 1
        provider.list_annual_reports("AAPL", 1)
    assert sum(r.url.path.endswith("company_tickers.json") for r in requests) == 1
    assert all(r.headers["User-Agent"] == "Test contact@example.com" for r in requests)


@pytest.mark.parametrize(
    "mode", ["http", "network", "invalid_json", "invalid_shape", "missing", "columns"]
)
def test_edgar_errors(mode: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if mode == "network":
            raise httpx.ConnectError("offline", request=request)
        if mode == "http":
            return httpx.Response(403)
        if mode == "invalid_json":
            return httpx.Response(200, text="not JSON")
        if mode == "invalid_shape":
            return httpx.Response(200, json=[])
        if mode == "missing":
            return httpx.Response(200, json={})
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(200, json={"0": {"ticker": "AAPL", "cik_str": 1}})
        return httpx.Response(200, json={"filings": {"recent": {"form": ["10-K"]}}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(FilingFetchError):
            EdgarFilingProvider("test", client, 0).list_annual_reports("AAPL", 2)


def test_request_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep = Mock()
    monkeypatch.setattr("app.adapters.filings.edgar.time.sleep", sleep)
    monkeypatch.setattr("app.adapters.filings.edgar.time.monotonic", lambda: 10.0)
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    ) as client:
        provider = EdgarFilingProvider("test", client)
        with pytest.raises(FilingFetchError):
            provider.list_annual_reports("A", 2)
        with pytest.raises(FilingFetchError):
            provider.list_annual_reports("A", 2)
        # Empty mapping is cached; test two direct requests for spacing.
        provider._get("https://example.com/a")
        provider._get("https://example.com/b")
    assert sleep.call_args.args == (0.2,)


@pytest.mark.parametrize(
    "mode,market,ua,expected",
    [
        ("mock", "NASDAQ", None, MockFilingProvider),
        ("real", "NYSE", "name contact@example.com", EdgarFilingProvider),
        ("real", "NASDAQ", None, type(None)),
        ("real", "NASDAQ", " ", type(None)),
        ("real", "KOSPI", "test", type(None)),
    ],
)
def test_factory(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    market: str,
    ua: str | None,
    expected: type,
) -> None:
    monkeypatch.setattr(settings, "FILING_PROVIDER", mode)
    monkeypatch.setattr(settings, "SEC_USER_AGENT", ua)
    assert isinstance(get_filing_provider(market), expected)


def add_asset(db: Session, symbol: str = "AAPL", market: str = "NASDAQ") -> int:
    asset = Asset(symbol=symbol, name="Apple Inc.", market=market)
    db.add(asset)
    db.commit()
    return asset.id


def test_collection_fields_and_duplicate(db: Session) -> None:
    asset_id = add_asset(db)
    provider = Mock(spec=MockFilingProvider, wraps=MockFilingProvider())
    service = FilingCollectionService(db, lambda _: provider)
    result = service.collect([asset_id])
    assert result.saved == 4
    documents = list(db.scalars(select(KnowledgeDocument)))
    doc = documents[0]
    assert doc.title == "Apple Inc. 10-K FY2025 — Item 1. Business"
    assert doc.external_id == "edgar:mock-AAPL-2025:BUSINESS"
    assert doc.kind == "FILING_SECTION"
    assert doc.asset_id == asset_id
    assert doc.source_name == "SEC EDGAR"
    assert doc.source_url == "https://example.com/filings/AAPL/2025"
    assert doc.license_note == "U.S. government public filing"
    assert doc.effective_date == date(2026, 2, 1)
    assert len(doc.content_hash) == 64
    assert doc.metadata_ == {
        "form": "10-K",
        "cik": "0",
        "accession": "mock-AAPL-2025",
        "report_date": "2025-12-31",
        "fiscal_year": 2025,
        "section": "BUSINESS",
    }
    provider.fetch_sections.reset_mock()
    assert service.collect([asset_id]).skipped_existing == 4
    provider.fetch_sections.assert_not_called()


def test_missing_and_partial_duplicate(db: Session) -> None:
    asset_id = add_asset(db)
    provider = Mock(spec=MockFilingProvider, wraps=MockFilingProvider())
    provider.fetch_sections.return_value = [
        FilingSectionText(FilingSection.BUSINESS, "business", "x" * 200_000, True)
    ]
    service = FilingCollectionService(db, lambda _: provider)
    result = service.collect([asset_id])
    assert result.saved == 2
    assert result.missing_sections[asset_id] == [
        "mock-AAPL-2025:RISK_FACTORS",
        "mock-AAPL-2024:RISK_FACTORS",
    ]
    assert all(
        doc.metadata_["truncated"] for doc in db.scalars(select(KnowledgeDocument))
    )
    provider.fetch_sections.side_effect = None
    provider.fetch_sections.return_value = MockFilingProvider().fetch_sections(
        MockFilingProvider().list_annual_reports("AAPL", 1)[0]
    )
    second = service.collect([asset_id])
    assert second.saved == 2 and second.skipped_existing == 2
    assert second.missing_sections == {}


def test_failure_rollback_and_unsupported(db: Session) -> None:
    bad = add_asset(db, "BAD")
    good = add_asset(db, "GOOD")
    korean = add_asset(db, "005930", "KOSPI")
    provider = Mock(spec=MockFilingProvider, wraps=MockFilingProvider())
    original = MockFilingProvider()

    def fetch(ref: object) -> list[FilingSectionText]:
        from app.adapters.filings.base import FilingRef

        assert isinstance(ref, FilingRef)
        if ref.accession == "mock-BAD-2024":
            raise FilingFetchError("broken")
        return original.fetch_sections(ref)

    provider.fetch_sections.side_effect = fetch
    result = FilingCollectionService(db, lambda _: provider).collect(
        [bad, good, korean, 99999]
    )
    assert result.saved == 4
    assert result.failed[bad] == "broken"
    assert 99999 in result.failed
    assert result.unsupported == [korean]
    assert {doc.asset_id for doc in db.scalars(select(KnowledgeDocument))} == {good}
    assert FilingCollectionService(db, lambda _: None).collect([good]).unsupported == [
        good
    ]


@pytest.mark.parametrize("outcome", ["success", "partial", "exception"])
def test_job_records(
    db: Session, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    monkeypatch.setattr("app.worker.jobs.filings.SessionLocal", lambda: db)
    service = Mock()
    monkeypatch.setattr(
        "app.worker.jobs.filings.FilingCollectionService", lambda _: service
    )
    if outcome == "exception":
        service.collect.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError, match="boom"):
            collect_filings_job([1])
    else:
        service.collect.return_value = FilingCollectionResult(
            saved=2,
            failed={1: "broken"} if outcome == "partial" else {},
            missing_sections={2: ["a:BUSINESS"]} if outcome == "partial" else {},
        )
        collect_filings_job([1])
    record = db.scalar(select(JobRun))
    assert record is not None
    assert record.job_type == "filing_collection"
    assert record.status == ("failed" if outcome == "exception" else "success")
    assert record.metadata_ is not None
    assert record.metadata_["asset_ids"] == [1]
    if outcome == "partial":
        assert record.metadata_["partial_failures"]["failed"] == {"1": "broken"}
        assert record.metadata_["partial_failures"]["missing_sections"] == {
            "2": ["a:BUSINESS"]
        }
    if outcome == "exception":
        assert record.error_message == "boom"


def test_schedule() -> None:
    schedule = default_scheduler_registry.get("filing_collection")
    assert schedule is not None
    assert schedule.enabled
    assert schedule.cron == "0 1 * * 6"


def test_default_watchlist_targets(db: Session) -> None:
    from app.domains.users.model import User
    from app.domains.watchlists.model import Watchlist, WatchlistItem

    watched = add_asset(db)
    unwatched = add_asset(db, "UNWATCHED")
    user = User(email="filings@example.com", hashed_password="unused")
    db.add(user)
    db.flush()
    watchlist = Watchlist(user_id=user.id, name="Filings")
    db.add(watchlist)
    db.flush()
    db.add(WatchlistItem(watchlist_id=watchlist.id, asset_id=watched))
    db.commit()
    result = FilingCollectionService(db, lambda _: MockFilingProvider()).collect()
    assert result.saved == 4
    assert {doc.asset_id for doc in db.scalars(select(KnowledgeDocument))} == {watched}
    assert unwatched != watched
    assert FilingCollectionService(db).collect([]).saved == 0


def test_mock_job_collects(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    asset_id = add_asset(db)
    monkeypatch.setattr(settings, "FILING_PROVIDER", "mock")
    monkeypatch.setattr("app.worker.jobs.filings.SessionLocal", lambda: db)
    collect_filings_job([asset_id])
    assert len(list(db.scalars(select(KnowledgeDocument)))) == 4
    record = db.scalar(select(JobRun))
    assert record is not None and record.metadata_ is not None
    assert record.metadata_["result"]["saved"] == 4
