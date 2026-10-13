import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.adapters.obsidian.writer import (
    FilingAnalysisNote,
    ObsidianWriter,
    render_filing_analysis_note,
)
from app.domains.agents.filing_analysis.schema import (
    DiffStats,
    FilingAnalysisContent,
    FilingChange,
    FilingEvidence,
    FilingReference,
    FilingSectionContent,
    Importance,
)


def note() -> FilingAnalysisNote:
    def reference(year: int) -> FilingReference:
        return FilingReference(
            accession=str(year),
            fiscal_year=year,
            filed_date=date(year + 1, 2, 1),
            source_url=f"https://example.com/{year}",
            knowledge_document_id={},
        )

    levels: tuple[Importance, ...] = ("LOW", "HIGH", "MEDIUM")
    return FilingAnalysisNote(
        symbol="AAPL",
        asset_name='애플: "기업"',
        generated_at=datetime.now(UTC),
        content=FilingAnalysisContent(
            old_filing=reference(2024),
            new_filing=reference(2025),
            headline="새 위험",
            max_importance="HIGH",
            sections={
                "BUSINESS": FilingSectionContent(failed="분석 실패"),
                "RISK_FACTORS": FilingSectionContent(
                    headline="위험 변화",
                    limitations="일부 발췌",
                    changes=[
                        FilingChange(
                            kind="OTHER",
                            title=f"{level} 변화",
                            summary="요약",
                            importance=level,
                            citations=["A1", "R1"],
                        )
                        for level in levels
                    ],
                    diff_stats=DiffStats(
                        unchanged=1, trivial=2, modified=3, added=4, removed=5
                    ),
                    truncated_count=6,
                ),
            },
            evidence={
                "RISK_FACTORS": {
                    "A1": FilingEvidence(new_text="새" * 510, old_text="미사용"),
                    "R1": FilingEvidence(old_text="옛 문단"),
                },
                "BUSINESS": {"A1": FilingEvidence(new_text="사업 문단")},
            },
        ),
    )


def test_render_metadata_sections_evidence_and_escaping() -> None:
    value = note()
    text = render_filing_analysis_note(value)
    metadata = {
        key: json.loads(raw)
        for line in text.split("---\n")[1].splitlines()[:-1]
        for key, raw in [line.split(": ", 1)]
    }
    assert metadata == dict(
        symbol="AAPL",
        asset_name=value.asset_name,
        form="10-K",
        old_fiscal_year=2024,
        new_fiscal_year=2025,
        filed_date="2026-02-01",
        max_importance="HIGH",
    )
    assert "tags: [stock-agent, filing-analysis]" in text
    assert f"# {value.asset_name}(AAPL) 10-K FY2025 비교 분석" in text
    assert "[[AAPL]]" in text
    offsets = [
        text.index(f"## {title}")
        for title in ("위험요인 변화", "사업 변화", "통계", "근거")
    ]
    assert offsets == sorted(offsets)
    assert text.index("HIGH 변화") < text.index("MEDIUM 변화") < text.index("LOW 변화")
    assert "섹션 분석 실패: 분석 실패" in text and "한계: 일부 발췌" in text
    assert "| 위험요인 변화 | 1 | 2 | 3 | 4 | 5 | 6 |" in text
    assert "[^RF-A1][^RF-R1]" in text
    assert "[^BIZ-A1]:" in text
    assert "[10-K FY2025 \\[A1\\]](https://example.com/2025)" in text
    assert "[10-K FY2024 \\[R1\\]](https://example.com/2024)" in text
    assert "새" * 500 in text and "새" * 501 not in text and "미사용" not in text
    assert "옛 문단" in text
    assert text.endswith(
        "이 노트는 stock-agent가 생성했습니다. 매수·매도 권유가 아닙니다.\n"
    )


def test_writer_path_collision_preserves_existing(tmp_path: Path) -> None:
    writer = ObsidianWriter(tmp_path, "custom")
    first = writer.write_filing_analysis_note(note())
    assert first == Path("custom/filings/AAPL/FY2025-10-K.md")
    assert (tmp_path / first).read_text() == render_filing_analysis_note(note())
    (tmp_path / first).write_bytes(b"original\x00\xff")
    second = writer.write_filing_analysis_note(note())
    assert second == Path("custom/filings/AAPL/FY2025-10-K-2.md")
    assert (tmp_path / first).read_bytes() == b"original\x00\xff"


@pytest.mark.parametrize("symbol", ["../x", "a\\b", "", "..", "a|b", "a\x00b"])
def test_writer_rejects_unsafe_symbols(tmp_path: Path, symbol: str) -> None:
    with pytest.raises(ValueError):
        ObsidianWriter(tmp_path, "stock-agent").write_filing_analysis_note(
            replace(note(), symbol=symbol)
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("export", ["../outside", "/outside", "..\\outside"])
def test_writer_rejects_export_escape(tmp_path: Path, export: str) -> None:
    with pytest.raises(ValueError):
        ObsidianWriter(tmp_path, export).write_filing_analysis_note(note())
    assert not list(tmp_path.iterdir())


def test_writer_rejects_symlink_escape(tmp_path: Path) -> None:
    vault, outside = tmp_path / "vault", tmp_path / "outside"
    vault.mkdir()
    outside.mkdir()
    (vault / "stock-agent").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        ObsidianWriter(vault, "stock-agent").write_filing_analysis_note(note())
    assert not list(outside.iterdir())
