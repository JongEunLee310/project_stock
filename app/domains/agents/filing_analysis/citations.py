import re

from app.domains.agents.filing_analysis.schema import (
    FilingChange,
    FilingSectionAnalysis,
)


def validate_filing_citations(
    analysis: FilingSectionAnalysis, allowed_ids: set[str]
) -> tuple[FilingSectionAnalysis, int]:
    corrections = 0
    changes: list[FilingChange] = []
    for change in analysis.changes:
        prefixes = {"NEW_RISK": "AM", "REMOVED_RISK": "RM"}.get(change.kind, "ARM")
        citations = list(
            dict.fromkeys(
                citation
                for citation in change.citations
                if re.fullmatch(r"[ARM]\d+", citation)
                and citation in allowed_ids
                and citation[0] in prefixes
            )
        )
        corrections += len(change.citations) - len(citations)
        if not citations:
            corrections += 1
            continue
        changes.append(change.model_copy(update={"citations": citations}))
    return analysis.model_copy(update={"changes": changes}), corrections
