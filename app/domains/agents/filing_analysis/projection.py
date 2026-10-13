"""Build a bounded projection containing only public filing differences."""

import json
from difflib import SequenceMatcher

from app.domains.agents.filing_analysis.schema import (
    FilingDiffSnapshot,
    FilingSection,
    ModifiedParagraph,
    ModifiedProjection,
    SectionDiff,
)

MAX_INPUT_CHARS = 80_000


def _marked_new_text(paragraph: ModifiedParagraph) -> str:
    old, new = paragraph.old_text.split(), paragraph.new_text.split()
    parts: list[str] = []
    for tag, _, _, start, end in SequenceMatcher(
        None, old, new, autojunk=False
    ).get_opcodes():
        text = " ".join(new[start:end])
        if tag != "equal":
            text = f"<changed>{text}</changed>"
        parts.append(text)
    return " ".join(parts)


def build_filing_diff_snapshot(
    diff: SectionDiff,
    *,
    symbol: str,
    asset_name: str,
    section: FilingSection,
    old_fiscal_year: int,
    new_fiscal_year: int,
) -> FilingDiffSnapshot:
    snapshot = FilingDiffSnapshot(
        symbol=symbol,
        asset_name=asset_name,
        section=section,
        old_fiscal_year=old_fiscal_year,
        new_fiscal_year=new_fiscal_year,
        added=diff.added,
        removed=diff.removed,
        stats=diff.stats,
        modified=[
            ModifiedProjection(
                id=item.id, old_text=item.old_text, new_text=_marked_new_text(item)
            )
            for item in diff.modified
        ],
    )
    # Count the entire serialized payload, including metadata and marker overhead.
    for item in sorted(
        diff.modified,
        key=lambda item: sum(
            len(" ".join(span.old_tokens)) + len(" ".join(span.new_tokens))
            for span in item.changed_spans
        ),
    ):
        if (
            len(json.dumps(snapshot.as_payload(), ensure_ascii=False))
            <= MAX_INPUT_CHARS
        ):
            break
        snapshot = snapshot.model_copy(
            update={
                "modified": [
                    entry for entry in snapshot.modified if entry.id != item.id
                ],
                "truncated_count": snapshot.truncated_count + 1,
            }
        )
    if len(json.dumps(snapshot.as_payload(), ensure_ascii=False)) > MAX_INPUT_CHARS:
        raise ValueError("공시 입력 상한 80000자 초과: modified 제외 후에도 초과")
    return snapshot
