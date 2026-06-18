# Completion, Commit, and CI Response Policy

## Purpose

Defines what happens the moment Claude Code judges a unit of work complete: how it is classified, committed, pushed, opened as a PR, and how CI failures are handled afterward.

## When Claude Code Judges Work Complete

This applies to work Claude Code itself produced (for example, documentation, plans, policy updates) as well as work completed through a Codex handoff. It does not change who is allowed to implement: Codex remains the default implementer per `agent-role-policy.md`.

## Step 1: Classify

Before committing, classify the change using two labels:

- **Commit type** — one of `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, matching the Conventional Commits style already used in this repository's history.
- **Risk level** — Low, Medium, High, or Critical, per `task-classification-policy.md`.

If a single unit of work mixes unrelated commit types (e.g., a doc update bundled with an unrelated code fix), split it into separate commits, one per type. Do not bundle unrelated changes into one commit to save time.

## Step 2: Commit

- Commit message language: Korean.
- Format: `type: 본문` (matches the user's global commit convention).
- One commit per classified unit of work from Step 1.
- Never bundle changes that touch protected files with changes that do not, even if both are low risk.

## Step 3: Push and Open a PR

- `main`, `fastapi`, and `spring-boot` are protected: direct push is rejected by repository rules. Push to a feature branch (e.g., `docs/<topic>`, `feat/<topic>`, `fix/<topic>`) and open a PR with `gh pr create` targeting the correct base branch.
- PR body should summarize what changed and reference the source issue or handoff task if one exists.
- Claude Code does not approve or merge the PR it opens. Human approval is still required per `local-review-policy.md`.

## Step 4: CI Failure Response

When CI fails on a PR:

1. **Claude Code investigates first.** Read the CI failure log, the PR diff, the related Codex handoff (if any), and `.codex/instructions.md`. Identify the root cause — do not guess or paper over symptoms.
2. **Claude Code documents the cause**, either in a new or updated Codex handoff task, or inline using `.codex/prompts/fix-ci-failure.md`, stating: what failed, why, and the expected fix direction.
3. **Codex implements the fix.** Claude Code does not edit implementation code to satisfy CI directly — that responsibility stays with Codex per `agent-role-policy.md`, unless the human has explicitly asked Claude Code to implement.
4. **Re-verify.** After Codex pushes a fix, re-check CI. Repeat from step 1 if it fails again. Do not weaken tests, lint, typecheck, or build rules to make CI pass.
5. **Record repeat failures.** If the same root cause recurs across PRs, create a failure record per `docs/failures/`.

## Related

- `task-classification-policy.md` — risk classification used in Step 1.
- `handoff-policy.md` — handoff structure used when Codex must fix CI failures.
- `feedback-loop-policy.md` — the broader issue-to-merge loop this policy fits into.
- `agent-role-policy.md` — why Claude Code does not implement fixes by default.
