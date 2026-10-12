import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.adapters.factory import get_obsidian_writer
from app.adapters.obsidian.writer import (
    ObsidianWriter,
    ResearchNote,
    render_research_note,
)
from app.core.config import settings
from app.domains.rag.schema import AnswerPoint, EvidenceItem, ResearchAnswer
from app.domains.rag.types import ChunkContentQuality, ChunkSourceType


def note() -> ResearchNote:
    return ResearchNote(
        symbol="NVDA",
        asset_name='NVIDIA: "기업"',
        question='성장: "근거"\n다음 질문?',
        embedding_model="bge-m3",
        answer=ResearchAnswer(
            generated_at=datetime(2026, 10, 11, 23, 59, tzinfo=UTC),
            insufficient_evidence=False,
            limitations=None,
            answer_points=[AnswerPoint(text="제품 출시", citations=[1, 3])],
            evidence=[
                EvidenceItem(
                    id=1,
                    source_type=ChunkSourceType.NEWS,
                    source_id=42,
                    title="출시 소식",
                    source_name="매체",
                    source_url="https://example.com/news",
                    published_at=datetime(2026, 10, 11, tzinfo=UTC),
                    excerpt="제품 출시",
                    score=0.8,
                    content_quality=ChunkContentQuality.FULL,
                )
            ],
        ),
    )


def test_render_frontmatter_and_body() -> None:
    research = note()
    rendered = render_research_note(research)
    metadata = rendered.split("---\n")[1].splitlines()
    fields = {
        key: json.loads(value)
        for line in metadata[:-1]
        for key, value in [line.split(": ", 1)]
    }
    assert fields == {
        "symbol": research.symbol,
        "asset_name": research.asset_name,
        "question": research.question,
        "generated_at": research.answer.generated_at.isoformat(),
        "embedding_model": "bge-m3",
        "source_count": 1,
        "insufficient_evidence": False,
    }
    assert metadata[-1] == "tags: [stock-agent, research-qa]"
    assert f"# {research.asset_name}(NVDA) 리서치 Q&A" in rendered
    assert "[[NVDA]]" in rendered
    assert f"## 질문\n\n{research.question}" in rendered
    assert "- 제품 출시 [1][3]" in rendered
    assert "[1] [출시 소식](https://example.com/news) — 매체, 2026-10-11" in rendered
    assert "## 한계" not in rendered
    assert rendered.endswith(
        "이 노트는 stock-agent가 생성했습니다. 매수·매도 권유가 아닙니다.\n"
    )


def test_render_insufficient_evidence_retains_points_and_limitations() -> None:
    research = note()
    research.answer.insufficient_evidence = True
    research.answer.limitations = "추가 근거 필요"
    rendered = render_research_note(research)
    assert "## 답변\n\n근거가 부족합니다\n\n- 제품 출시 [1][3]" in rendered
    assert "## 한계\n\n추가 근거 필요" in rendered
    research.answer.evidence[0].published_at = None
    assert "— 매체, \n" in render_research_note(research)


@pytest.mark.parametrize(
    "question,slug",
    [
        ('한글 / \\ : * ? " < > | # ^ [ ] 질문', "한글-질문"),
        ("가" * 40 + "나", "가" * 40),
        (" / ? # ", "question"),
        ("../x", "..-x"),
    ],
)
def test_writer_path_and_slug(tmp_path: Path, question: str, slug: str) -> None:
    research = replace(note(), question=question)
    path = ObsidianWriter(tmp_path, "stock-agent").write_research_note(research)
    assert path == Path(f"stock-agent/research/NVDA/2026-10-12-{slug}.md")
    assert (tmp_path / path).read_text() == render_research_note(research)


def test_writer_collisions_preserve_existing_bytes(tmp_path: Path) -> None:
    writer = ObsidianWriter(tmp_path, "stock-agent")
    research = replace(note(), question="질문")
    first = writer.write_research_note(research)
    original = b"existing\x00\xff\r\n"
    (tmp_path / first).write_bytes(original)
    second = writer.write_research_note(research)
    second_bytes = (tmp_path / second).read_bytes()
    third = writer.write_research_note(research)
    assert second.stem == first.stem + "-2"
    assert third.stem == first.stem + "-3"
    assert (tmp_path / first).read_bytes() == original
    assert (tmp_path / second).read_bytes() == second_bytes


def test_writer_missing_vault(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        ObsidianWriter(missing, "stock-agent").write_research_note(note())
    assert not missing.exists()


@pytest.mark.parametrize("symbol", ["../x", "/x", "..", ".", "", "a\\b", "C:tmp"])
def test_writer_rejects_unsafe_symbol(tmp_path: Path, symbol: str) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    with pytest.raises(ValueError):
        ObsidianWriter(vault, "stock-agent").write_research_note(
            replace(note(), symbol=symbol)
        )
    assert list(tmp_path.iterdir()) == [vault]
    assert list(vault.iterdir()) == []


@pytest.mark.parametrize("export_dir", ["../outside", "/outside", "..\\outside"])
def test_writer_rejects_unsafe_export_dir(tmp_path: Path, export_dir: str) -> None:
    with pytest.raises(ValueError):
        ObsidianWriter(tmp_path, export_dir).write_research_note(note())
    assert list(tmp_path.iterdir()) == []


def test_writer_rejects_symlink_escape(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    outside = tmp_path / "outside"
    vault.mkdir()
    outside.mkdir()
    (vault / "stock-agent").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        ObsidianWriter(vault, "stock-agent").write_research_note(note())
    assert list(outside.iterdir()) == []


def test_writer_collision_limit(tmp_path: Path) -> None:
    writer = ObsidianWriter(tmp_path, "stock-agent")
    research = replace(note(), question="질문")
    for _ in range(100):
        writer.write_research_note(research)
    with pytest.raises(FileExistsError, match="100"):
        writer.write_research_note(research)
    assert len(list(tmp_path.rglob("*.md"))) == 100


def test_writer_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_PATH", None)
    assert get_obsidian_writer() is None
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "OBSIDIAN_EXPORT_DIR", "exports")
    writer = get_obsidian_writer()
    assert writer is not None
    assert writer.vault_path == tmp_path and writer.export_dir == "exports"
