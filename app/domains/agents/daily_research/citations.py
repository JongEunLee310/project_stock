from app.domains.agents.daily_research.schema import (
    BriefChange,
    BriefPoint,
    DailyBriefResult,
    ItemClassification,
)


def validate_brief_citations(
    result: DailyBriefResult, new_ids: set[str], past_ids: set[str]
) -> tuple[DailyBriefResult, int]:
    corrections = 0

    def clean(
        point: BriefPoint, allowed: set[str], required: list[set[str]]
    ) -> list[str]:
        nonlocal corrections
        citations = list(dict.fromkeys(c for c in point.citations if c in allowed))
        corrections += len(point.citations) - len(citations)
        if not citations or any(not set(citations) & group for group in required):
            corrections += 1
            return []
        return citations

    developments: list[BriefPoint] = []
    risks: list[BriefPoint] = []
    for original, target in (
        (result.new_developments, developments),
        (result.risk_checks, risks),
    ):
        for point in original:
            citations = clean(point, new_ids, [new_ids])
            if citations:
                target.append(point.model_copy(update={"citations": citations}))
    changes: list[BriefChange] = []
    for change in result.changes:
        allowed = new_ids if change.kind == "NEW" else past_ids
        required = [allowed]
        if change.kind == "CONTINUING":
            allowed = new_ids | past_ids
            required = [new_ids, past_ids]
        citations = clean(change, allowed, required)
        if citations:
            changes.append(change.model_copy(update={"citations": citations}))
    classifications: dict[str, ItemClassification] = {}
    for classification in result.item_classifications:
        if classification.item not in new_ids or classification.item in classifications:
            corrections += 1
            continue
        classifications[classification.item] = classification
    for item in sorted(new_ids, key=lambda value: int(value[1:])):
        if item not in classifications:
            classifications[item] = ItemClassification(item=item)
            corrections += 1
    return result.model_copy(
        update={
            "new_developments": developments,
            "risk_checks": risks,
            "changes": changes,
            "item_classifications": list(classifications.values()),
        }
    ), corrections
