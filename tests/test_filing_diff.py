from time import perf_counter

import pytest

from app.domains.agents.filing_analysis.diff import diff_sections, split_paragraphs


def paragraph(prefix: str, count: int = 10) -> str:
    return " ".join(f"{prefix}{i:03}" for i in range(count))


def test_split_paragraph_boundaries_and_headers() -> None:
    kept = "z" * 41
    assert split_paragraphs(
        "\n".join(
            [
                "x" * 39,
                "y" * 40,
                f"  {kept}  ",
                "Table of Contents" + " " * 50,
                "Table of Contents " + "a" * 50,
                "Apple Inc. | 2025 Form 10-K | 4" + " " * 50,
                "Very Long Corporation Name Here | 2025 Form 10-K | 4",
            ]
        )
    ) == [kept]


@pytest.mark.parametrize(
    ("equal", "total", "unchanged", "modified", "added"),
    [
        (97, 100, 1, 0, 0),
        (96, 100, 0, 1, 0),
        (98, 100, 1, 0, 0),
        (6, 10, 0, 1, 0),
        (7, 10, 0, 1, 0),
        (5, 10, 0, 0, 1),
    ],
)
def test_similarity_boundaries(
    equal: int, total: int, unchanged: int, modified: int, added: int
) -> None:
    old = paragraph("old", total)
    new = " ".join(
        [f"old{i:03}" for i in range(equal)]
        + [f"new{i:03}" for i in range(equal, total)]
    )
    result = diff_sections(old, new)
    assert result.stats.unchanged == unchanged
    assert result.stats.modified == modified
    assert result.stats.added == result.stats.removed == added


def test_global_best_match_wins_and_old_is_used_once() -> None:
    old = paragraph("token")
    changed = old.replace("token009", "replacement")
    result = diff_sections(old, changed + "\n" + old)
    assert result.stats.unchanged == 1
    assert result.stats.modified == 0
    assert [item.text for item in result.added] == [changed]


def test_second_choice_is_kept_for_global_matching() -> None:
    base = paragraph("token")
    old_second = base.replace("token008", "alternative")
    new_second = base.replace("token009", "replacement")
    result = diff_sections(base + "\n" + old_second, base + "\n" + new_second)
    assert result.stats.unchanged == 1
    assert result.stats.modified == 1
    assert result.modified[0].old_text == old_second
    assert result.stats.added == result.stats.removed == 0


def test_ties_are_deterministic() -> None:
    old = paragraph("token")
    first = old.replace("token009", "firstword")
    second = old.replace("token009", "secondword")
    result = diff_sections(old, first + "\n" + second)
    assert result.modified[0].new_text == first
    assert result.added[0].text == second
    assert diff_sections(old, first + "\n" + second) == result


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("2024", "2025"),
        ("January 12, 2024", "March 12, 2024"),
        ("$1,000.00", "$2,000.00"),
        ("10%", "20%"),
        ("2024-10-12", "2025-10-13"),
        ("1,000", "2,000"),
        ("USD 100", "USD 200"),
        ("January 12, 2024", "March 15, 2025"),
    ],
)
def test_numeric_changes_are_trivial(before: str, after: str) -> None:
    base = paragraph("context", 12)
    result = diff_sections(f"{base} {before} end", f"{base} {after} end")
    assert result.stats.trivial == 1
    assert not result.modified
    assert result.stats.modified_chars == 0


def test_word_and_numeric_changes_are_modified_with_spans() -> None:
    base = paragraph("context", 8)
    result = diff_sections(f"{base} stable 2024 end", f"{base} volatile 2025 end")
    change = result.modified[0]
    assert change.id == "M1"
    assert change.changed_spans[0].old_tokens == ["stable", "2024"]
    assert change.changed_spans[0].new_tokens == ["volatile", "2025"]
    assert result.stats.modified_chars == len("stable 2024") + len("volatile 2025")


def test_inserted_number_is_trivial_but_inserted_word_is_modified() -> None:
    base = paragraph("context")
    assert diff_sections(base, base + " 2025").stats.trivial == 1
    assert diff_sections(base, base + " important").stats.modified == 1
    assert diff_sections(base + " 2025", base).stats.trivial == 1


def test_numbering_order_and_stats() -> None:
    unchanged = paragraph("same")
    trivial = paragraph("numeric") + " 2024"
    modified1 = paragraph("first")
    modified2 = paragraph("second")
    removed1, removed2 = paragraph("gone"), paragraph("deleted")
    added1, added2 = paragraph("fresh"), paragraph("novel")
    updated1 = modified1.replace("first009", "changed")
    updated2 = modified2.replace("second009", "different")
    old = "\n".join([modified1, removed1, unchanged, trivial, removed2, modified2])
    new = "\n".join(
        [added1, updated2, unchanged, added2, updated1, trivial.replace("2024", "2025")]
    )
    result = diff_sections(old, new)
    assert [(item.id, item.text) for item in result.added] == [
        ("A1", added1),
        ("A2", added2),
    ]
    assert [(item.id, item.text) for item in result.removed] == [
        ("R1", removed1),
        ("R2", removed2),
    ]
    assert [(item.id, item.new_text) for item in result.modified] == [
        ("M1", updated2),
        ("M2", updated1),
    ]
    stats = result.stats
    assert (
        stats.unchanged,
        stats.trivial,
        stats.modified,
        stats.added,
        stats.removed,
    ) == (1, 1, 2, 2, 2)
    assert stats.added_chars == len(added1) + len(added2)
    assert stats.removed_chars == len(removed1) + len(removed2)
    assert stats.modified_chars == sum(
        len(" ".join(span.old_tokens)) + len(" ".join(span.new_tokens))
        for item in result.modified
        for span in item.changed_spans
    )
    assert stats.unchanged + stats.trivial + stats.modified + stats.added == 6
    assert stats.unchanged + stats.trivial + stats.modified + stats.removed == 6


def test_empty_inputs() -> None:
    assert diff_sections("", "").stats.model_dump() == {
        "unchanged": 0,
        "modified": 0,
        "trivial": 0,
        "added": 0,
        "removed": 0,
        "added_chars": 0,
        "removed_chars": 0,
        "modified_chars": 0,
    }
    text = paragraph("token")
    assert diff_sections("", text).added[0].text == text
    assert diff_sections(text, "").removed[0].text == text


def test_250_by_250_performance() -> None:
    old = "\n".join(paragraph(f"paragraph{i}_", 60) for i in range(250))
    new = old.replace("_059", "_updated")
    started = perf_counter()
    result = diff_sections(old, new)
    elapsed = perf_counter() - started
    assert result.stats.unchanged == 250
    assert elapsed < 10


def test_month_words_without_date_are_not_trivial() -> None:
    base = paragraph("context", 10)
    assert (
        diff_sections(base + " may happen", base + " june happen").stats.modified == 1
    )
