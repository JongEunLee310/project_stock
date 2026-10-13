import json
from datetime import date
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.llm.gateway import LLMCompletionResult
from app.adapters.llm.prompts.filing_analysis import build_filing_analysis_system_prompt
from app.adapters.llm.prompts.language import KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION
from app.adapters.llm.router import LLM_TASK_ROUTES
from app.adapters.llm.types import LLMTaskType, SensitivityLevel
from app.domains.agents.filing_analysis.citations import validate_filing_citations
from app.domains.agents.filing_analysis.projection import (
    MAX_INPUT_CHARS,
    build_filing_diff_snapshot,
)
from app.domains.agents.filing_analysis.schema import (
    ChangedSpan,
    FilingAnalysisContent,
    FilingChange,
    FilingDiffSnapshot,
    FilingSectionAnalysis,
    ModifiedParagraph,
    ParagraphChange,
    SectionDiff,
)
from app.domains.agents.filing_analysis.service import FilingAnalysisAgent
from app.domains.alerts.model import Alert
from app.domains.assets.model import Asset
from app.domains.knowledge.model import KnowledgeDocument
from app.domains.reports.model import ResearchReport
from app.domains.signals.model import Signal
from app.domains.users.model import User
from app.domains.watchlists.model import Watchlist, WatchlistItem


def projection(diff: SectionDiff) -> FilingDiffSnapshot:
    return build_filing_diff_snapshot(
        diff,
        symbol="AAPL",
        asset_name="Apple",
        section="BUSINESS",
        old_fiscal_year=2024,
        new_fiscal_year=2025,
    )


def test_projection_contract_markers_and_truncation() -> None:
    small = ModifiedParagraph(
        id="M1",
        old_text="old " + "s" * 21000,
        new_text="new " + "s" * 21000,
        changed_spans=[ChangedSpan(old_tokens=["old"], new_tokens=["new"])],
    )
    large = ModifiedParagraph(
        id="M2",
        old_text="old " + "s" * 21000,
        new_text="danger " + "s" * 21000,
        changed_spans=[ChangedSpan(old_tokens=["old"], new_tokens=["danger"])],
    )
    diff = SectionDiff(modified=[large, small])
    snapshot = projection(diff)
    assert FilingDiffSnapshot.free_text_fields == ()
    assert snapshot.sensitivity == SensitivityLevel.PUBLIC
    assert len(snapshot.model_dump_json()) <= MAX_INPUT_CHARS
    assert snapshot.truncated_count == 1
    assert [item.id for item in snapshot.modified] == ["M2"]
    assert "<changed>danger</changed>" in snapshot.modified[0].new_text
    assert len(diff.modified) == 2
    assert projection(SectionDiff()).truncated_count == 0


def test_projection_rejects_irreducibly_large_input() -> None:
    with pytest.raises(ValueError, match="80000"):
        projection(SectionDiff(added=[ParagraphChange(id="A1", text="x" * 80000)]))


def test_deleted_tokens_get_empty_marker() -> None:
    snapshot = projection(
        SectionDiff(
            modified=[
                ModifiedParagraph(
                    id="M1",
                    old_text="one two three",
                    new_text="one three",
                    changed_spans=[ChangedSpan(old_tokens=["two"], new_tokens=[])],
                )
            ]
        )
    )
    assert snapshot.modified[0].new_text == "one <changed></changed> three"


def test_citations_clean_invalid_unknown_wrong_prefix_and_empty_changes() -> None:
    def change(kind: str, citations: list[str]) -> dict[str, object]:
        return dict(
            kind=kind,
            title="변화",
            summary="요약",
            importance="HIGH",
            citations=citations,
        )

    analysis = FilingSectionAnalysis.model_validate(
        dict(
            headline="변화",
            changes=[
                change("NEW_RISK", ["A1", "R1", "M1", "A99", "invalid"]),
                change("REMOVED_RISK", ["R1", "M1", "A1"]),
                change("OTHER", ["A1", "R1", "M1", "A1"]),
                change("NEW_RISK", ["R1"]),
                change("BUSINESS_CHANGE", []),
            ],
        )
    )
    cleaned, count = validate_filing_citations(analysis, {"A1", "R1", "M1"})
    assert [change.citations for change in cleaned.changes] == [
        ["A1", "M1"],
        ["R1", "M1"],
        ["A1", "R1", "M1"],
    ]
    assert count == 8  # six removed citations and two dropped changes
    assert len(analysis.changes) == 5


def test_prompt_contains_schema_and_route() -> None:
    prompt = build_filing_analysis_system_prompt()
    assert (
        json.dumps(FilingSectionAnalysis.model_json_schema(), ensure_ascii=False)
        in prompt
    )
    assert (
        FilingChange.model_json_schema()["properties"]["citations"]["items"]["pattern"]
        == r"^[ARM]\d+$"
    )
    assert KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION in prompt
    assert LLM_TASK_ROUTES[LLMTaskType.FILING_ANALYSIS].launch == "cloud"
    assert LLM_TASK_ROUTES[LLMTaskType.FILING_ANALYSIS].future_primary == "local"


def asset(db: Session, symbol: str = "AAPL") -> Asset:
    value = Asset(symbol=symbol, name=symbol, market="NASDAQ")
    db.add(value)
    db.commit()
    return value


OLD = "Our company sells devices worldwide and develops software for consumers in many established markets."
NEW = "Government sanctions could eliminate our overseas revenue and prohibit every international sale immediately."


def filing(
    db: Session,
    target: Asset,
    accession: str,
    year: int,
    sections: tuple[str, ...] = ("BUSINESS", "RISK_FACTORS"),
) -> None:
    for section in sections:
        db.add(
            KnowledgeDocument(
                kind="FILING_SECTION",
                title=section,
                content=NEW if year == 2025 else OLD,
                asset_id=target.id,
                source_name="SEC",
                source_url=f"https://example.com/{accession}",
                effective_date=date(year + 1, 2, 1),
                external_id=f"{target.id}:{accession}:{section}",
                content_hash="hash",
                metadata_=dict(
                    accession=accession,
                    fiscal_year=year,
                    section=section,
                    report_date=f"{year}-12-31",
                ),
            )
        )
    db.commit()


def gateway(level: str = "HIGH") -> Mock:
    fake = Mock()
    fake.complete_json.return_value = LLMCompletionResult(
        output=dict(
            headline="새 위험",
            changes=[
                dict(
                    kind="NEW_RISK",
                    title="제재 위험",
                    summary="매출 손실 가능성",
                    importance=level,
                    citations=["A1"],
                )
            ],
        ),
        provider="fake",
        model_name="fake",
    )
    return fake


def pair(db: Session) -> Asset:
    target = asset(db)
    filing(db, target, "old", 2024)
    filing(db, target, "new", 2025)
    return target


def owners(db: Session, target: Asset) -> None:
    for owner in (1, 2):
        db.add(User(id=owner, email=f"{owner}@example.com", hashed_password="hash"))
        db.flush()
        db.add(Watchlist(id=owner, user_id=owner, name="관심"))
        db.flush()
        db.add(WatchlistItem(watchlist_id=owner, asset_id=target.id))
    db.commit()


@pytest.mark.parametrize(
    "level,signals,alerts", [("HIGH", 1, 2), ("MEDIUM", 0, 0), ("LOW", 0, 0)]
)
def test_analysis_persists_contract_deduplicates_and_alerts_owners(
    db: Session, level: str, signals: int, alerts: int
) -> None:
    target = pair(db)
    owners(db, target)
    fake = gateway(level)
    agent = FilingAnalysisAgent(db, fake)
    result = agent.run()
    assert result.analyzed == 1 and result.llm_calls == 2
    assert result.signals_created == signals and result.alerts_created == alerts
    assert not result.failed
    report = db.scalars(select(ResearchReport)).one()
    content = FilingAnalysisContent.model_validate(report.content)
    assert report.summary == content.headline == "새 위험"
    assert report.risk_level == content.max_importance == level
    assert report.report_type == "FILING_ANALYSIS" and report.source_ref == "edgar:new"
    assert (
        content.old_filing.accession == "old" and content.new_filing.accession == "new"
    )
    assert content.old_filing.fiscal_year == 2024
    assert content.new_filing.filed_date == date(2026, 2, 1)
    assert content.new_filing.source_url == "https://example.com/new"
    for section in ("BUSINESS", "RISK_FACTORS"):
        stored = content.sections[section]
        assert stored.diff_stats.added == 1 and stored.diff_stats.removed == 1
        assert (
            stored.failed is None
            and stored.citation_corrections == stored.truncated_count == 0
        )
        evidence = content.evidence[section]["A1"]
        assert evidence.new_text == NEW and evidence.old_text is None
        assert (
            evidence.new_knowledge_document_id
            == content.new_filing.knowledge_document_id[section]
        )
    assert len(list(db.scalars(select(Signal)))) == signals
    assert len(list(db.scalars(select(Alert)))) == alerts
    if signals:
        signal = db.scalars(select(Signal)).one()
        assert signal.evidence is not None
        assert json.loads(signal.evidence)["report_id"] == report.id
        assert signal.signal_type == "RISK_ALERT" and signal.reason == content.headline
    skipped = agent.run([target.id, target.id])
    assert skipped.skipped_existing == 1 and skipped.llm_calls == 0
    assert fake.complete_json.call_count == 2


@pytest.mark.parametrize("count", [0, 1])
def test_no_pair_does_not_call_llm(db: Session, count: int) -> None:
    target = asset(db)
    if count:
        filing(db, target, "new", 2025)
    fake = gateway()
    result = FilingAnalysisAgent(db, fake).run([target.id])
    assert result.skipped_no_pair == 1
    fake.complete_json.assert_not_called()


@pytest.mark.parametrize("fail_both", [False, True])
def test_llm_section_failure_isolation_and_retry(db: Session, fail_both: bool) -> None:
    target = pair(db)
    fake = gateway("LOW")
    completion = fake.complete_json.return_value
    fake.complete_json.side_effect = [
        RuntimeError("broken"),
        RuntimeError("broken") if fail_both else completion,
    ]
    agent = FilingAnalysisAgent(db, fake)
    result = agent.run([target.id])
    assert result.llm_calls == 2 and target.id in result.failed
    assert result.analyzed == (0 if fail_both else 1)
    reports = list(db.scalars(select(ResearchReport)))
    assert len(reports) == (0 if fail_both else 1)
    if not fail_both:
        content = FilingAnalysisContent.model_validate(reports[0].content)
        assert content.sections["BUSINESS"].failed == "broken"
        assert content.sections["RISK_FACTORS"].failed is None
    else:
        fake.complete_json.side_effect = None
        assert agent.run([target.id]).analyzed == 1


def test_missing_section_is_recorded(db: Session) -> None:
    target = asset(db)
    filing(db, target, "old", 2024, ("BUSINESS",))
    filing(db, target, "new", 2025)
    result = FilingAnalysisAgent(db, gateway("LOW")).run([target.id])
    assert result.analyzed == 1 and result.llm_calls == 1
    report = db.scalars(select(ResearchReport)).one()
    assert report.content is not None
    assert report.content["sections"]["RISK_FACTORS"]["failed"] == "섹션 없음"


def test_signal_failure_preserves_committed_report(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = pair(db)
    monkeypatch.setattr(
        "app.domains.agents.filing_analysis.service.SignalRepository.create",
        Mock(side_effect=RuntimeError("signal broken")),
    )
    result = FilingAnalysisAgent(db, gateway()).run([target.id])
    assert result.analyzed == 1 and result.signals_created == 0
    assert "signal broken" in result.failed[target.id]
    db.rollback()
    assert db.scalars(select(ResearchReport)).one().source_ref == "edgar:new"


def test_asset_failure_isolation(db: Session) -> None:
    target = pair(db)
    result = FilingAnalysisAgent(db, gateway("LOW")).run([9999, target.id])
    assert result.failed == {9999: "asset not found"}
    assert result.analyzed == 1


def test_headline_uses_section_with_highest_validated_importance(db: Session) -> None:
    target = pair(db)
    low, high = gateway("LOW"), gateway("HIGH")
    low.complete_json.return_value.output["headline"] = "사업 변화"
    high.complete_json.return_value.output["headline"] = "중요 위험"
    low.complete_json.side_effect = [
        low.complete_json.return_value,
        high.complete_json.return_value,
    ]
    result = FilingAnalysisAgent(db, low).run([target.id])
    assert result.analyzed == 1
    report = db.scalars(select(ResearchReport)).one()
    assert report.summary == "중요 위험" and report.risk_level == "HIGH"


def test_invalid_citations_cannot_trigger_high_alert(db: Session) -> None:
    target = pair(db)
    fake = gateway()
    fake.complete_json.return_value.output["changes"][0]["citations"] = ["A99", "bad"]
    result = FilingAnalysisAgent(db, fake).run([target.id])
    assert result.analyzed == 1 and result.signals_created == 0
    report = db.scalars(select(ResearchReport)).one()
    content = FilingAnalysisContent.model_validate(report.content)
    assert content.max_importance == "LOW"
    assert all(not section.changes for section in content.sections.values())
    assert all(
        section.citation_corrections == 3 for section in content.sections.values()
    )
    assert all(not values for values in content.evidence.values())


def test_original_modified_and_removed_evidence(db: Session) -> None:
    target = pair(db)
    documents = list(db.scalars(select(KnowledgeDocument)))
    old_text = " ".join(f"token{i}" for i in range(20))
    new_text = old_text.replace("token0 token1", "new0 new1")
    removed_text = OLD
    for doc in documents:
        doc.content = (
            old_text + "\n" + removed_text
            if doc.metadata_["accession"] == "old"
            else new_text
        )
    db.commit()
    fake = gateway("LOW")
    fake.complete_json.return_value.output["changes"][0].update(
        kind="OTHER", citations=["M1", "R1"]
    )
    result = FilingAnalysisAgent(db, fake).run([target.id])
    assert result.analyzed == 1
    content = FilingAnalysisContent.model_validate(
        db.scalars(select(ResearchReport)).one().content
    )
    for section in content.evidence:
        modified = content.evidence[section]["M1"]
        assert modified.old_text == old_text and modified.new_text == new_text
        assert (
            modified.old_knowledge_document_id
            == content.old_filing.knowledge_document_id[section]
        )
        assert (
            modified.new_knowledge_document_id
            == content.new_filing.knowledge_document_id[section]
        )
        removed = content.evidence[section]["R1"]
        assert removed.old_text == removed_text and removed.new_text is None
    snapshot = fake.complete_json.call_args.args[1]
    assert "<changed>new0 new1</changed>" in snapshot.modified[0].new_text


def test_pair_selection_uses_effective_date_and_distinct_accessions(
    db: Session,
) -> None:
    target = asset(db)
    filing(db, target, "new", 2025)
    filing(db, target, "ancient", 2023)
    filing(db, target, "old", 2024)
    result = FilingAnalysisAgent(db, gateway("LOW")).run([target.id])
    assert result.analyzed == 1
    content = FilingAnalysisContent.model_validate(
        db.scalars(select(ResearchReport)).one().content
    )
    assert (
        content.new_filing.accession == "new" and content.old_filing.accession == "old"
    )


def test_alert_failure_preserves_report_and_signal(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = pair(db)
    owners(db, target)
    monkeypatch.setattr(
        "app.domains.agents.filing_analysis.service.AlertService.create_alert",
        Mock(side_effect=RuntimeError("alert broken")),
    )
    result = FilingAnalysisAgent(db, gateway()).run([target.id])
    assert result.analyzed == result.signals_created == 1 and result.alerts_created == 0
    assert "alert broken" in result.failed[target.id]
    db.rollback()
    assert db.scalars(select(ResearchReport)).one()
    assert db.scalars(select(Signal)).one()


def test_projection_counts_gateway_json_whitespace() -> None:
    from app.domains.agents.filing_analysis.schema import DiffStats

    snapshot = FilingDiffSnapshot(
        symbol="AAPL",
        asset_name="Apple",
        section="BUSINESS",
        old_fiscal_year=2024,
        new_fiscal_year=2025,
        added=[ParagraphChange(id="A1", text="")],
        removed=[],
        modified=[],
        stats=DiffStats(),
    )
    text = "x" * (MAX_INPUT_CHARS - len(snapshot.model_dump_json()))
    snapshot = snapshot.model_copy(
        update={"added": [ParagraphChange(id="A1", text=text)]}
    )
    assert len(snapshot.model_dump_json()) == MAX_INPUT_CHARS
    assert len(json.dumps(snapshot.as_payload(), ensure_ascii=False)) > MAX_INPUT_CHARS
    with pytest.raises(ValueError, match="80000"):
        projection(SectionDiff(added=snapshot.added))


def test_real_gateway_with_mock_provider_is_runnable(db: Session) -> None:
    from app.adapters.llm.gateway import LLMGateway
    from app.adapters.llm.mock import DEFAULT_MOCK_RESPONSES, MockLLMClient

    target = pair(db)
    real_gateway = LLMGateway({"cloud": MockLLMClient(DEFAULT_MOCK_RESPONSES)})
    result = FilingAnalysisAgent(db, real_gateway).run([target.id])
    assert result.analyzed == 1 and result.llm_calls == 2 and not result.failed
    content = FilingAnalysisContent.model_validate(
        db.scalars(select(ResearchReport)).one().content
    )
    assert content.max_importance == "LOW"
    assert all(
        section.limitations and "Mock" in section.limitations
        for section in content.sections.values()
    )
