import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.domains.agents.daily_research.schema import DailyBriefContent
from app.domains.rag.schema import ResearchAnswer

UNSAFE_FILENAME = re.compile(r'[/\\:*?"<>|#^\[\]\s]')
MAX_CREATION_ATTEMPTS = 100


@dataclass(frozen=True)
class ResearchNote:
    symbol: str
    asset_name: str
    question: str
    answer: ResearchAnswer
    embedding_model: str


def render_research_note(note: ResearchNote) -> str:
    answer = note.answer
    metadata = {
        "symbol": note.symbol,
        "asset_name": note.asset_name,
        "question": note.question,
        "generated_at": answer.generated_at.isoformat(),
        "embedding_model": note.embedding_model,
        "source_count": len(answer.evidence),
        "insufficient_evidence": answer.insufficient_evidence,
        "masked_categories": [category.value for category in answer.masked_categories],
    }
    # JSON scalars are also YAML scalars and escape quotes and control characters.
    lines = ["---"]
    lines.extend(
        f"{key}: {json.dumps(value, ensure_ascii=False)}"
        for key, value in metadata.items()
    )
    lines.extend(
        [
            "tags: [stock-agent, research-qa]",
            "---",
            "",
            f"# {note.asset_name}({note.symbol}) 리서치 Q&A",
            "",
            f"[[{note.symbol}]]",
            "",
            "## 질문",
            "",
            note.question,
            "",
            "## 답변",
            "",
        ]
    )
    if answer.insufficient_evidence:
        lines.extend(["근거가 부족합니다.", ""])
    for point in answer.answer_points:
        citations = "".join(f"[^{citation}]" for citation in point.citations)
        lines.append(f"- {point.text}{citations}")
    if answer.limitations:
        lines.extend(["", "## 한계", "", answer.limitations])
    lines.extend(["", "## 근거", ""])
    for item in answer.evidence:
        published = item.published_at.date().isoformat() if item.published_at else ""
        title = item.title.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        lines.append(
            f"[^{item.id}]: [{title}]({item.source_url}) — "
            f"{item.source_name}, {published}"
        )
        lines.append("")
    lines.extend(["이 노트는 stock-agent가 생성했습니다. 매수·매도 권유가 아닙니다.", ""])
    return "\n".join(lines)


@dataclass(frozen=True)
class DailySignalLine:
    signal_type: str
    score: int
    reason: str


@dataclass(frozen=True)
class DailyBriefNote:
    symbol: str
    asset_name: str
    brief_date: date
    generated_at: datetime
    content: DailyBriefContent
    signals: list[DailySignalLine]


@dataclass(frozen=True)
class DailyIndexEntry:
    symbol: str
    asset_name: str
    headline: str
    new_item_count: int
    note_path: Path | None
    failed_reason: str | None = None


def render_daily_brief_note(note: DailyBriefNote) -> str:
    content = note.content
    metadata = {
        "symbol": note.symbol,
        "asset_name": note.asset_name,
        "brief_date": note.brief_date.isoformat(),
        "generated_at": note.generated_at.isoformat(),
        "new_item_count": content.stats.new_item_count,
        "no_news": content.no_news,
        "price_stale": content.price.stale if content.price else False,
    }
    lines = ["---"]
    lines.extend(
        f"{key}: {json.dumps(value, ensure_ascii=False)}"
        for key, value in metadata.items()
    )
    lines.extend(
        [
            "tags: [stock-agent, daily-brief]",
            "---",
            "",
            f"# {note.asset_name}({note.symbol}) 일일 브리프 {note.brief_date}",
            "",
            f"[[{note.symbol}]]",
        ]
    )

    def section(title: str, body: list[str]) -> None:
        if body:
            lines.extend(["", f"## {title}", "", *body])

    def point(text: str, citations: list[str]) -> str:
        return f"- {text}" + "".join(f"[^{value}]" for value in citations)

    section(
        "핵심 요약",
        ["새 소식 없음"]
        if content.no_news
        else ([content.headline] if content.headline else []),
    )
    if not content.no_news:
        section(
            "새 소식", [point(p.text, p.citations) for p in content.new_developments]
        )
        changes = []
        for kind, title in [
            ("NEW", "새 이슈"),
            ("CONTINUING", "계속되는 이슈"),
            ("FADED", "잠잠해진 이슈"),
        ]:
            group = [
                point(p.text, p.citations) for p in content.changes if p.kind == kind
            ]
            if group:
                changes.extend([f"### {title}", "", *group, ""])
        section("이전 대비 달라진 점", changes)
    price_lines = []
    if content.price:
        price = content.price
        price_lines.extend(
            [
                "| 기준일 | 종가 | 등락률 | 거래량 변화 |",
                "|---|---|---|---|",
                f"| {price.as_of} | {price.close} | "
                f"{price.change_pct + '%' if price.change_pct is not None else '—'} | "
                f"{price.volume_change_pct + '%' if price.volume_change_pct is not None else '—'} |",
            ]
        )
        if price.stale:
            price_lines.extend(["", "오래된 데이터"])
    if not content.no_news and note.signals:
        price_lines.extend(
            [
                "",
                *[
                    f"- {signal.signal_type} (점수 {signal.score}): {signal.reason}"
                    for signal in note.signals
                ],
            ]
        )
    section("가격·신호", price_lines)
    section(
        "다가오는 일정", [f"- {event.date}: {event.kind}" for event in content.upcoming]
    )
    if not content.no_news:
        section(
            "리스크 점검 후보",
            [point(p.text, p.citations) for p in content.risk_checks],
        )
        section("한계", [content.limitations] if content.limitations else [])
        evidence_lines = []
        for item in content.evidence:
            title = (
                item.title.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
            )
            published = (
                item.published_at.date().isoformat() if item.published_at else ""
            )
            evidence_lines.extend(
                [
                    f"[^{item.id}]: [{title}]({item.source_url}) — {item.source_name}, {published}",
                    "",
                ]
            )
        section("근거", evidence_lines)
    lines.extend(
        ["", "이 노트는 stock-agent가 생성했습니다. 매수·매도 권유가 아닙니다.", ""]
    )
    return "\n".join(lines)


def render_daily_index(brief_date: date, entries: list[DailyIndexEntry]) -> str:
    lines = [
        "---",
        f'brief_date: "{brief_date.isoformat()}"',
        f"asset_count: {len(entries)}",
        f"failed_count: {sum(entry.failed_reason is not None for entry in entries)}",
        "tags: [stock-agent, daily-index]",
        "---",
        "",
        f"# 일일 브리프 {brief_date}",
        "",
    ]
    for entry in entries:
        if entry.note_path is not None:
            path = entry.note_path.with_suffix("").as_posix()
            lines.append(
                f"- [[{path}|{entry.symbol}]] {entry.headline} "
                f"(새 소식 {entry.new_item_count}건)"
            )
        if entry.failed_reason is not None:
            reason = " ".join(entry.failed_reason.splitlines())
            lines.append(f"- {entry.asset_name}({entry.symbol}) 실패: {reason}")
    return "\n".join([*lines, ""])


class ObsidianWriter:
    def __init__(self, vault_path: Path, export_dir: str) -> None:
        self.vault_path = vault_path
        self.export_dir = export_dir

    def write_research_note(self, note: ResearchNote) -> Path:
        self._validate_symbol(note.symbol)
        slug = re.sub("-+", "-", UNSAFE_FILENAME.sub("-", note.question[:40]))
        slug = slug.strip("-") or "question"
        day = note.answer.generated_at.astimezone(ZoneInfo("Asia/Seoul")).date()
        stem = f"{day.isoformat()}-{slug}"
        content = render_research_note(note)
        return self._write_new(Path("research") / note.symbol, stem, content)

    def write_daily_brief_note(self, note: DailyBriefNote) -> Path:
        self._validate_symbol(note.symbol)
        return self._write_new(
            Path("daily") / note.symbol,
            note.brief_date.isoformat(),
            render_daily_brief_note(note),
        )

    def write_daily_index(
        self, brief_date: date, entries: list[DailyIndexEntry]
    ) -> Path:
        return self._write_new(
            Path("daily"),
            brief_date.isoformat(),
            render_daily_index(brief_date, entries),
        )

    @staticmethod
    def _validate_symbol(symbol: str) -> None:
        if (
            not symbol
            or symbol in {".", ".."}
            or UNSAFE_FILENAME.search(symbol)
            or "\x00" in symbol
        ):
            raise ValueError("symbol must be a safe path component")

    def _write_new(self, relative_dir: Path, stem: str, content: str) -> Path:
        vault = self.vault_path.resolve(strict=True)
        if not vault.is_dir():
            raise NotADirectoryError(vault)
        export = Path(self.export_dir)
        if export.is_absolute() or ".." in export.parts or "\\" in self.export_dir:
            raise ValueError("export_dir must be relative to the vault")
        directory = vault / export / relative_dir
        self._validate_path(directory, vault)
        directory.mkdir(parents=True, exist_ok=True)
        for attempt in range(1, MAX_CREATION_ATTEMPTS + 1):
            suffix = "" if attempt == 1 else f"-{attempt}"
            path = directory / f"{stem}{suffix}.md"
            self._validate_path(path, vault)
            try:
                with path.open("x", encoding="utf-8") as output:
                    output.write(content)
            except FileExistsError:
                continue
            return path.relative_to(vault)
        raise FileExistsError("Obsidian note creation exhausted 100 filenames")

    @staticmethod
    def _validate_path(path: Path, vault: Path) -> None:
        if not path.resolve().is_relative_to(vault):
            raise ValueError("note path must remain inside the vault")
