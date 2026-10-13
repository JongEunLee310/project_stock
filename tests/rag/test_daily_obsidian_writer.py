import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.adapters.obsidian.writer import (
    DailyBriefNote,
    DailyIndexEntry,
    DailySignalLine,
    ObsidianWriter,
    render_daily_brief_note,
    render_daily_index,
)
from app.domains.agents.daily_research.schema import (
    BriefChange,
    BriefEvidence,
    BriefPoint,
    BriefPrice,
    BriefStats,
    BriefUpcoming,
    DailyBriefContent,
)

DAY = date(2026, 10, 10)


def note() -> DailyBriefNote:
    return DailyBriefNote(
        symbol="NVDA",
        asset_name='엔비디아: "기업"',
        brief_date=DAY,
        generated_at=datetime(2026, 10, 12, 23, tzinfo=UTC),
        signals=[DailySignalLine("RISK_ALERT", 80, "위험 후보")],
        content=DailyBriefContent(
            headline="제품 출시",
            new_developments=[BriefPoint(text="출시", citations=["N1"])],
            changes=[
                BriefChange(kind="NEW", text="새 이슈", citations=["N1"]),
                BriefChange(kind="CONTINUING", text="계속", citations=["N1", "P1"]),
                BriefChange(kind="FADED", text="잠잠", citations=["P1"]),
            ],
            price=BriefPrice(
                as_of=date(2026, 10, 1),
                stale=True,
                close="123.45",
                change_pct=None,
                volume_change_pct="10.00",
            ),
            upcoming=[BriefUpcoming(date=DAY)],
            risk_checks=[BriefPoint(text="확인", citations=["N1"])],
            limitations="제목만 확인",
            stats=BriefStats(new_item_count=1),
            evidence=[
                BriefEvidence(
                    id=value,
                    title="[출시] 소식",
                    source_name="매체",
                    published_at=None,
                    excerpt="소식",
                    raw_news_event_id=1,
                    news_item_id=None,
                    source_url="https://example.com/news",
                )
                for value in ["N1", "P1"]
            ],
        ),
    )


def test_render_daily_sections_metadata_and_citations() -> None:
    value = note()
    text = render_daily_brief_note(value)
    metadata = {
        key: json.loads(raw)
        for line in text.split("---\n")[1].splitlines()[:-1]
        for key, raw in [line.split(": ", 1)]
    }
    assert metadata == {
        "symbol": "NVDA",
        "asset_name": value.asset_name,
        "brief_date": str(DAY),
        "generated_at": value.generated_at.isoformat(),
        "new_item_count": 1,
        "no_news": False,
        "price_stale": True,
    }
    assert 'asset_name: "엔비디아: \\"기업\\""' in text
    assert "tags: [stock-agent, daily-brief]" in text
    assert f"# {value.asset_name}(NVDA) 일일 브리프 {DAY}" in text
    assert "[[NVDA]]" in text
    sections = [
        "핵심 요약",
        "새 소식",
        "이전 대비 달라진 점",
        "가격·신호",
        "다가오는 일정",
        "리스크 점검 후보",
        "한계",
        "근거",
    ]
    offsets = [text.index(f"## {section}\n") for section in sections]
    assert offsets == sorted(offsets)
    for title in ["새 이슈", "계속되는 이슈", "잠잠해진 이슈"]:
        assert f"### {title}" in text
    assert "- 계속[^N1][^P1]" in text
    for value_id in ["N1", "P1"]:
        assert f"[^{value_id}]: [\\[출시\\] 소식](https://example.com/news)" in text
    assert "오래된 데이터" in text
    assert "| 2026-10-01 | 123.45 | — | 10.00% |" in text
    assert "RISK_ALERT (점수 80): 위험 후보" in text
    assert text.endswith(
        "이 노트는 stock-agent가 생성했습니다. 매수·매도 권유가 아닙니다.\n"
    )


def test_empty_sections_and_no_news() -> None:
    empty = replace(note(), content=DailyBriefContent(headline="요약"), signals=[])
    text = render_daily_brief_note(empty)
    assert [line for line in text.splitlines() if line.startswith("## ")] == [
        "## 핵심 요약"
    ]
    value = note()
    value.content.no_news = True
    text = render_daily_brief_note(value)
    assert [line for line in text.splitlines() if line.startswith("## ")] == [
        "## 핵심 요약",
        "## 가격·신호",
        "## 다가오는 일정",
    ]
    assert "새 소식 없음" in text and "RISK_ALERT" not in text
    assert "[^N1]" not in text
    assert value.content.price is not None
    value.content.price.stale = False
    assert "오래된 데이터" not in render_daily_brief_note(value)


def test_daily_index_success_failure_and_actual_path() -> None:
    entries = [
        DailyIndexEntry(
            "NVDA",
            "엔비디아",
            "출시",
            2,
            Path("stock-agent/daily/NVDA/2026-10-10-2.md"),
        ),
        DailyIndexEntry("MSFT", "마이크로소프트", "", 0, None, "쓰기 실패\n권한 없음"),
    ]
    text = render_daily_index(DAY, entries)
    assert 'brief_date: "2026-10-10"' in text
    assert "asset_count: 2\nfailed_count: 1" in text
    assert "tags: [stock-agent, daily-index]" in text
    assert "- [[stock-agent/daily/NVDA/2026-10-10-2|NVDA]] 출시 (새 소식 2건)" in text
    assert "- 마이크로소프트(MSFT) 실패: 쓰기 실패 권한 없음" in text
    assert "[[None" not in text


def test_daily_paths_collision_and_no_overwrite(tmp_path: Path) -> None:
    writer = ObsidianWriter(tmp_path, "stock-agent")
    value = note()
    first = writer.write_daily_brief_note(value)
    assert first == Path("stock-agent/daily/NVDA/2026-10-10.md")
    assert (tmp_path / first).read_text() == render_daily_brief_note(value)
    (tmp_path / first).write_bytes(b"original\x00\xff")
    second = writer.write_daily_brief_note(value)
    assert second.stem == first.stem + "-2"
    assert (tmp_path / first).read_bytes() == b"original\x00\xff"
    index = writer.write_daily_index(DAY, [])
    assert index == Path("stock-agent/daily/2026-10-10.md")
    original = (tmp_path / index).read_bytes()
    assert writer.write_daily_index(DAY, []).stem == index.stem + "-2"
    assert (tmp_path / index).read_bytes() == original


@pytest.mark.parametrize(
    "symbol", ["../x", "/x", "..", ".", "", "a\\b", "C:tmp", "a\x00b"]
)
def test_daily_rejects_unsafe_symbols(tmp_path: Path, symbol: str) -> None:
    with pytest.raises(ValueError):
        ObsidianWriter(tmp_path, "stock-agent").write_daily_brief_note(
            replace(note(), symbol=symbol)
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("export", ["../outside", "/outside", "..\\outside"])
@pytest.mark.parametrize("index", [False, True])
def test_daily_rejects_export_escape(tmp_path: Path, export: str, index: bool) -> None:
    writer = ObsidianWriter(tmp_path, export)
    with pytest.raises(ValueError):
        if index:
            writer.write_daily_index(DAY, [])
        else:
            writer.write_daily_brief_note(note())
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("index", [False, True])
def test_daily_rejects_symlink_escape(tmp_path: Path, index: bool) -> None:
    vault, outside = tmp_path / "vault", tmp_path / "outside"
    vault.mkdir()
    outside.mkdir()
    (vault / "stock-agent").symlink_to(outside, target_is_directory=True)
    writer = ObsidianWriter(vault, "stock-agent")
    with pytest.raises(ValueError):
        if index:
            writer.write_daily_index(DAY, [])
        else:
            writer.write_daily_brief_note(note())
    assert not list(outside.iterdir())


@pytest.mark.parametrize("no_news", [False, True])
def test_filing_section_position_and_no_news(no_news: bool) -> None:
    from app.domains.agents.daily_research.schema import BriefFilingAnalysis

    value = note()
    value.content.no_news = no_news
    value.content.filing_analyses = [
        BriefFilingAnalysis(
            report_id=1,
            symbol="NVDA",
            fiscal_year=2025,
            headline="사업 변화",
            max_importance="HIGH",
            note_path="custom/filings/NVDA/FY2025-10-K",
        )
    ]
    text = render_daily_brief_note(value)
    assert text.index("## 새 연간보고서 분석") < text.index("## 가격·신호")
    assert (
        "- [[custom/filings/NVDA/FY2025-10-K|10-K FY2025]] 사업 변화 (중요도 HIGH)"
        in text
    )
    value.content.filing_analyses = []
    assert "## 새 연간보고서 분석" not in render_daily_brief_note(value)


def test_legacy_brief_without_filing_field() -> None:
    payload = note().content.model_dump(mode="json")
    payload.pop("filing_analyses")
    assert DailyBriefContent.model_validate(payload).filing_analyses == []
