# Dogfooding Plan

## Purpose

Three small, low-risk tasks to exercise the full Claude Code + Codex workflow end to end on each branch before the template is used for real projects. These are drafts only. None of them should be implemented without explicit human approval to open the work.

## Task 1: `main` — `docs: improve Human Gate glossary entry`

**Goal:** Update `docs/knowledge/glossary.md` to clarify what Human Gate means in this template. The glossary currently has no "Human Gate" entry; one should be added that explains when a human approval step is required, referencing `docs/harness/human-gate-policy.md`.

**Expected flow:**

1. Claude Code plans the task.
2. Claude Code creates a Codex handoff task.
3. Codex edits only `docs/knowledge/glossary.md` (and the directory README if the included-documents list needs no change, this step is a no-op).
4. CI runs the template self-check only.
5. Claude Code performs local PR review.
6. Review result is recorded on the PR with `gh pr comment` / `gh pr review`.

**Risk:** Low. Documentation-only change, no protected files, no code.

## Task 2: `fastapi` — `feat: add version endpoint`

**Goal:** Add `GET /version` returning `{"version": "0.1.0"}`.

**Expected flow:**

1. Claude Code creates a Codex handoff task.
2. Codex updates `app/main.py` and `tests/`.
3. CI runs `uv run ruff check .`, `uv run mypy .`, `uv run pytest`.
4. Claude Code performs local PR review.

**Risk:** Low. Additive endpoint, no existing behavior changed.

## Task 3: `spring-boot` — `feat: add version endpoint`

**Goal:** Add `GET /version` returning `{"version": "0.1.0"}`.

**Expected flow:**

1. Claude Code creates a Codex handoff task.
2. Codex updates the Spring Boot controller layer and `src/test/`.
3. CI runs `./gradlew build`.
4. Claude Code performs local PR review.

**Risk:** Low. Additive endpoint, no existing behavior changed.

## Status

All three tasks are drafts. See `docs/feedback/dogfooding-handoffs/` for the corresponding Codex handoff drafts. None has been implemented. Opening issues and PRs for these tasks requires human decision.
