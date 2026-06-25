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

- `main` is protected: direct push is rejected by repository rules. Push to a feature branch (e.g., `docs/<topic>`, `feat/<topic>`, `fix/<topic>`) and open a PR with `gh pr create` targeting `main`.
- **Labels are required.** Attach labels at creation with `gh pr create --label`. Inherit the labels of the issue(s) the PR resolves; if there is no source issue, label by area and change type (at minimum the commit type, e.g., `docs`).
- **Assignee, milestone, and project are required.** Assign the PR to yourself (`--assignee @me` at creation, or `gh pr edit <n> --add-assignee @me`). Set the milestone to the related one — inherit it from the source issue's milestone (`--milestone "<title>"`). Add the PR to the `project_stock` GitHub Project. The **same metadata applies to issues you create**: assignee = yourself, the relevant milestone, project = `project_stock`. Note: linking to the `project_stock` Project (Projects v2) needs the gh token `project` scope (`gh auth refresh -s project`) and `gh project item-add --owner JongEunLee310 --url <pr-or-issue-url>`; the classic `--add-project` flag is deprecated and fails.
- PR body must include a closing keyword (`Closes #N`) for every related issue so that GitHub automatically closes the issue on merge. If the PR addresses multiple issues, list each on a separate line (e.g., `Closes #8`, `Closes #9`, `Closes #12`). The `.github/pull_request_template.md` already contains a `Closes #` placeholder — always fill in the issue number before creating the PR.
- PR body Summary section: group bullets by issue, not by individual bullet. If the PR covers a single issue, list all bullets together without per-bullet issue annotations (the PR title already carries the issue number). If the PR covers multiple issues, introduce each group with a bold issue header (e.g., `**Issue #10 — 제목**`) so reviewers can tell at a glance which change addresses which issue.
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
