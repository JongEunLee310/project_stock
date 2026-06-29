# Agent Instructions

These instructions apply to all AI coding agents working in this repository.

## Working Rules

- Read the relevant documentation before starting work.
- Before starting work, pull the latest `main` and create a dedicated feature branch (`feat/<topic>`, or `fix/`/`docs/`/`chore/` by change type). Never commit work directly on `main`.
- Stay within the issue scope and the explicit handoff scope.
- Distinguish facts, assumptions, and open questions.
- Do not weaken tests, CI, lint, typecheck, build checks, or verification rules.
- Do not remove tests to make CI pass.
- Do not modify protected files unless the issue or handoff explicitly allows it.
- Update documentation when project knowledge changes.
- Record important decisions in ADRs when they affect future work.
- Record important failures when an attempted approach should not be repeated.

## Protected Files

Protected files are files that require explicit permission before modification. Project-specific templates may expand this list.

- `AGENTS.md`
- `CLAUDE.md`
- `.codex/instructions.md`
- `.codex/agents/`
- `.codex/config.toml`
- `.codex/CODEX_ORCHESTRATION.md`
- `.github/workflows/ci.yml`
- `docs/harness/`
- `docs/decisions/`
- `docs/failures/`

`.codex/agents/` and `.codex/config.toml` define what a Codex subagent is allowed to do and how deep delegation can go — a `feature_worker` or `bugfix_worker` changing its own permissions is a privilege-escalation risk, not a normal code change.

`.codex/CODEX_SETUP_NOTES.md` and `.codex/CODEX_TASK_PACKET_TEMPLATE.md` are not protected files, but any change to them should be called out explicitly in the handoff, since they affect what behavior is expected from Codex subagents.

## Verification

Use the verification commands listed in the issue, handoff task, or project README.

Default commands for this template:

- `uv run ruff check .` — lint
- `uv run mypy .` — type check
- `uv run pytest` — tests

If verification cannot be run, explain why and state the residual risk.

## Codex Subagents

Codex may spawn the custom agents defined in `.codex/agents/` (`codebase_explorer`, `feature_worker`, `bugfix_worker`, `test_debugger`, `refactor_worker`, `pr_reviewer`) only when explicitly asked to in the session prompt. See `.codex/CODEX_ORCHESTRATION.md` for when each one applies and `.codex/CODEX_TASK_PACKET_TEMPLATE.md` for the task packet format.

## Done Definition

A Codex task is done only when all of the following are reported, not just implied:

- The requirement is met.
- The list of changed files is stated.
- The relevant test/verification commands were run, with results.
- Any verification that could not be run is named, with the reason and residual risk.
- Remaining risks are stated.
- Whether documentation, an ADR, or a failure record needs updating is stated.
