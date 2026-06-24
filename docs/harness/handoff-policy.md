# Handoff Policy

Claude Code hands implementation work to Codex using `.codex/task-template.md`.

## Required Fields

- Source Issue
- Task Summary
- Goal
- Background
- Implementation Scope
- Out of Scope
- Protected Files
- Requirements
- Test Requirements
- Verification Commands
- Documentation Impact
- ADR Need
- Failure Record Need
- Risk Level
- Expected Output
- Rules

## Stop Conditions

Claude Code should stop instead of handing off when:

- The issue goal is unclear.
- Required decisions are architectural and unresolved.
- Protected file changes are needed but not approved.
- Verification expectations are missing.
- Risk is high and human approval is needed.
- The requested change conflicts with existing policy.

## Handoff Quality

A good handoff is narrow, testable, and explicit about what Codex must not change.

## Codex Execution

Claude Code may invoke `codex exec` automatically as the implementation step, **under the default sandbox only** (`read-only` / `workspace-write`), passing the handoff document as the brief (per `docs/decisions/ADR-005-allow-claude-code-to-invoke-codex-exec.md`). Automation does not remove the handoff: the written scope / out-of-scope / verification contract above is still produced and passed to Codex as the prompt. Codex CLI must be pinned to a crash-free version (see `.codex/CODEX_SETUP_NOTES.md`).

`--dangerously-bypass-approvals-and-sandbox` and `-s danger-full-access` must **never** be used in an automated Claude Code workflow. If Codex's default sandbox cannot run a task, stop and ask the human per `docs/harness/human-gate-policy.md` instead of escalating Codex's privileges — fall back to manual execution (ADR-004), never to elevated access. Mandatory human gate conditions still apply **before** the automated implementation step runs.
