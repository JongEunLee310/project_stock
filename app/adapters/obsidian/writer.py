import json
import re
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

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


class ObsidianWriter:
    def __init__(self, vault_path: Path, export_dir: str) -> None:
        self.vault_path = vault_path
        self.export_dir = export_dir

    def write_research_note(self, note: ResearchNote) -> Path:
        vault = self.vault_path.resolve(strict=True)
        if not vault.is_dir():
            raise NotADirectoryError(vault)
        if (
            not note.symbol
            or note.symbol in {".", ".."}
            or UNSAFE_FILENAME.search(note.symbol)
            or "\x00" in note.symbol
        ):
            raise ValueError("symbol must be a safe path component")
        export = Path(self.export_dir)
        if export.is_absolute() or ".." in export.parts or "\\" in self.export_dir:
            raise ValueError("export_dir must be relative to the vault")
        directory = vault / export / "research" / note.symbol
        self._validate_path(directory, vault)
        slug = re.sub("-+", "-", UNSAFE_FILENAME.sub("-", note.question[:40]))
        slug = slug.strip("-") or "question"
        day = note.answer.generated_at.astimezone(ZoneInfo("Asia/Seoul")).date()
        stem = f"{day.isoformat()}-{slug}"
        content = render_research_note(note)
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
