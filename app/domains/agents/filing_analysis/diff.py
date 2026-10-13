"""Deterministic, one-to-one paragraph comparison for public filings."""

import re
from difflib import SequenceMatcher

from app.domains.agents.filing_analysis.schema import (
    ChangedSpan,
    ModifiedParagraph,
    ParagraphChange,
    SectionDiff,
)

_HEADER = re.compile(r"Table\s+of\s+Contents|\|\s*\d{4}\s+Form\s+10-K\s*\|", re.I)
_NUMBER = re.compile(
    r"(?:[$€£¥₩]|USD|EUR|GBP|JPY|KRW)?"
    r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    r"(?:%|[$€£¥₩]|USD|EUR|GBP|JPY|KRW)?",
    re.I,
)
_DATE = re.compile(r"\d{1,4}[-/.]\d{1,2}(?:[-/.]\d{1,4})?")
_MONTHS = frozenset(
    "january february march april may june july august september october november "
    "december jan feb mar apr jun jul aug sep sept oct nov dec".split()
)
_CURRENCIES = frozenset("usd eur gbp jpy krw $ € £ ¥ ₩".split())


def split_paragraphs(text: str) -> list[str]:
    return [
        line
        for raw in text.splitlines()
        if len(line := raw.strip()) > 40 and not _HEADER.search(line)
    ]


def _numeric_token(token: str) -> bool:
    value = token.strip("(),;:[]{}.!?")
    return bool(_NUMBER.fullmatch(value) or _DATE.fullmatch(value))


def _numeric_positions(tokens: list[str]) -> set[int]:
    positions = {index for index, token in enumerate(tokens) if _numeric_token(token)}
    # A month or detached currency marker needs an adjacent numeric date/amount.
    return positions | {
        index
        for index, token in enumerate(tokens)
        if token.strip(".,").lower() in _MONTHS | _CURRENCIES
        and (index - 1 in positions or index + 1 in positions)
    }


def diff_sections(old_text: str, new_text: str) -> SectionDiff:
    old = split_paragraphs(old_text)
    new = split_paragraphs(new_text)
    old_tokens = [paragraph.split() for paragraph in old]
    new_tokens = [paragraph.split() for paragraph in new]
    candidates: list[tuple[float, int, int]] = []
    # Keep all viable pairs: a second choice may be needed after another pair wins.
    for new_index, updated in enumerate(new_tokens):
        matcher = SequenceMatcher[str](None, [], updated, autojunk=False)
        for old_index, tokens in enumerate(old_tokens):
            matcher.set_seq1(tokens)
            if matcher.real_quick_ratio() < 0.6 or matcher.quick_ratio() < 0.6:
                continue
            ratio = matcher.ratio()
            if ratio >= 0.6:
                candidates.append((ratio, new_index, old_index))

    matched_old: set[int] = set()
    matches: dict[int, tuple[int, float]] = {}
    for ratio, new_index, old_index in sorted(
        candidates, key=lambda pair: (-pair[0], pair[1], pair[2])
    ):
        if new_index not in matches and old_index not in matched_old:
            matches[new_index] = (old_index, ratio)
            matched_old.add(old_index)

    result = SectionDiff()
    for new_index, paragraph in enumerate(new):
        match = matches.get(new_index)
        if match is None:
            result.added.append(
                ParagraphChange(id=f"A{len(result.added) + 1}", text=paragraph)
            )
            result.stats.added_chars += len(paragraph)
            continue
        old_index, ratio = match
        if ratio >= 0.97:
            result.stats.unchanged += 1
            continue
        matcher = SequenceMatcher(
            None, old_tokens[old_index], new_tokens[new_index], autojunk=False
        )
        opcodes = [opcode for opcode in matcher.get_opcodes() if opcode[0] != "equal"]
        spans = [
            ChangedSpan(
                old_tokens=old_tokens[old_index][old_start:old_end],
                new_tokens=new_tokens[new_index][new_start:new_end],
            )
            for _, old_start, old_end, new_start, new_end in opcodes
        ]
        old_numeric = _numeric_positions(old_tokens[old_index])
        new_numeric = _numeric_positions(new_tokens[new_index])
        if all(
            all(index in old_numeric for index in range(old_start, old_end))
            and all(index in new_numeric for index in range(new_start, new_end))
            for _, old_start, old_end, new_start, new_end in opcodes
        ):
            result.stats.trivial += 1
            continue
        result.modified.append(
            ModifiedParagraph(
                id=f"M{len(result.modified) + 1}",
                old_text=old[old_index],
                new_text=paragraph,
                changed_spans=spans,
            )
        )
        result.stats.modified_chars += sum(
            len(" ".join(span.old_tokens)) + len(" ".join(span.new_tokens))
            for span in spans
        )

    for old_index, paragraph in enumerate(old):
        if old_index not in matched_old:
            result.removed.append(
                ParagraphChange(id=f"R{len(result.removed) + 1}", text=paragraph)
            )
            result.stats.removed_chars += len(paragraph)
    result.stats.added = len(result.added)
    result.stats.removed = len(result.removed)
    result.stats.modified = len(result.modified)
    return result
