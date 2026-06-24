# ADR-004: Use Manual Codex Execution Instead Of Nested Codex Exec

## Status

Superseded by [ADR-005](ADR-005-allow-claude-code-to-invoke-codex-exec.md)

> ADR-005 allows Claude Code to invoke `codex exec` automatically **under the default sandbox only** (never bypass/danger flags), once the Codex CLI is pinned to a crash-free version. The role boundary and the permanent prohibition on elevated/bypass invocation below remain in force; only the "manual execution step is mandatory" decision is reversed. This document is retained for history and as the fallback model when automated invocation is unavailable.

## Context

Dogfooding attempted to let Claude Code drive the full pipeline by invoking `codex exec` directly from its own Bash tool. This failed at the sandbox level (`FAILURE-001-nested-codex-exec-sandbox-conflict.md`) and, independent of the crash, raised a structural question: should Claude Code ever spawn Codex as a nested, shell-capable subprocess at all?

## Decision

Claude Code does not call Codex CLI directly as a nested implementation agent, with or without elevated sandbox flags.

Claude Code's role stays limited to writing the Codex handoff document (`.codex/task-template.md`). The human operator runs Codex manually — in a separate terminal session, IDE integration, or an explicitly approved isolated environment — using that handoff as the brief.

`--dangerously-bypass-approvals-and-sandbox` and `-s danger-full-access` must not be used in any automated Claude Code workflow. If Codex's own sandbox fails and only an elevated-access run can proceed, Claude Code stops and asks the human, per `docs/harness/human-gate-policy.md`, rather than escalating privileges itself.

## Alternatives

- Have Claude Code call `codex exec` with `danger-full-access` whenever the default sandbox fails. Rejected: this lets one agent grant another agent broad shell access without an independent approval step, which the harness's autonomy model is designed to prevent.
- Fix the sandbox crash and keep automated `codex exec` invocation under `read-only`/`workspace-write`. Possible in the future (see Follow-up), but not viable now since the crash reproduces even for trivial read-only commands.
- Run Codex inside a fully separate, pre-approved disposable container or VM that Claude Code can target without per-run human approval. Rejected for now: still a nested-agent structure, and out of scope for a template meant to run on a developer's local machine without extra infrastructure.

## Consequences

The Claude Code → Codex → CI → human pipeline keeps a human-operated step between handoff creation and implementation, so it is slightly less automated than originally planned for dogfooding. In exchange, the role boundary (`ADR-001-separate-claude-code-and-codex-roles.md`) stays intact: Claude Code plans and reviews, Codex implements under its own session and its own approval settings, and no agent silently acquires another agent's execution authority.

## Follow-up

- If a future Codex CLI or OS update resolves the sandbox crash, re-evaluate automated `codex exec` invocation under its default (non-bypassed) sandbox modes only — never under `danger-full-access` or the bypass flag.
- Document the manual Codex execution step in `docs/knowledge/template-usage.md` and `docs/feedback/dogfooding-plan.md`.

## Related Documents

- `docs/failures/FAILURE-001-nested-codex-exec-sandbox-conflict.md`
- `docs/decisions/ADR-001-separate-claude-code-and-codex-roles.md`
- `docs/harness/handoff-policy.md`
- `docs/harness/human-gate-policy.md`
- `docs/harness/autonomy-levels.md`
