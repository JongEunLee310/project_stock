# Codex Handoff Task

## Source Issue

Link or identifier: (placeholder — create issue `docs: improve Human Gate glossary entry` before opening this handoff)

## Task Summary

Add a "Human Gate" entry to `docs/knowledge/glossary.md` so the term is defined where other workflow terms already live.

## Goal

`docs/knowledge/glossary.md` contains a "Human Gate" entry that accurately summarizes when human approval is required, consistent with `docs/harness/human-gate-policy.md`.

## Background

The glossary defines Harness Engineering, Claude Code, Codex, Handoff, ADR, Failure Record, Knowledge Base, Feedback Loop, Garbage Collection, Protected Files, and Documentation Drift, but has no entry for "Human Gate" even though the term is used throughout `docs/harness/human-gate-policy.md` and `docs/harness/autonomy-levels.md`.

## Implementation Scope

- `docs/knowledge/glossary.md` — add one new entry, alphabetically or thematically placed consistent with the existing entries.

## Out of Scope

- Do not change `docs/harness/human-gate-policy.md` or `docs/harness/autonomy-levels.md` content.
- Do not add new glossary terms beyond "Human Gate".
- Do not change unrelated glossary entries.

## Protected Files

None required for this task. Do not modify `.claude/`, `.codex/`, `.github/`, or CI files.

## Requirements

- New "Human Gate" entry follows the existing one-paragraph definition style used by other entries.
- Definition must be consistent with `docs/harness/human-gate-policy.md` (read it before writing the entry).

## Test Requirements

None — documentation-only change. No code or tests affected.

## Verification Commands

```bash
find .claude/hooks -name "*.sh" -print -exec bash -n {} \;
test -f docs/knowledge/glossary.md
```

## Documentation Impact

This task is itself a documentation update. No further documentation impact expected.

## ADR Need

No. This is a definition clarification, not a decision.

## Failure Record Need

No.

## Risk Level

Low. Documentation-only, no protected files, no code, no CI behavior change.

## Expected Output

A PR that adds one glossary entry, with CI template self-check passing and a Claude Code local review comment.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
