# ADR-005: Allow Claude Code To Invoke Codex Exec Under Default Sandbox

## Status

Accepted (supersedes ADR-004)

## Context

ADR-004 kept a human-operated step between Claude Code's handoff and Codex implementation, for two reasons: an early `codex exec` attempt crashed at the sandbox level (`FAILURE-001`), and letting one agent grant another shell access raised a structural concern about the autonomy model.

Two things changed:

- **Token economics.** Running both design and implementation through Claude Code exhausts its usage limits quickly. Moving implementation to Codex (a separate tool with its own budget) and letting Claude Code trigger it automatically keeps the design/review loop in Claude Code while implementation runs in Codex — without a manual hand-off step for every task.
- **The crash is avoidable.** The SIGTRAP regression was isolated to specific Codex CLI versions, not to the nested-invocation model itself. Pinning Codex CLI to a known-good version (0.140.0) sidesteps it.

The role boundary from `ADR-001` (Claude Code plans/reviews, Codex implements) requires an *independent* execution step, not a *manual* one. Codex still runs under its own session, model, and sandbox.

## Decision

Claude Code may invoke `codex exec` automatically as the implementation step, subject to **all** of:

1. **Default sandbox only** — `read-only` or `workspace-write`.
2. **No privilege escalation, ever.** `--dangerously-bypass-approvals-and-sandbox` and `-s danger-full-access` are permanently forbidden in any automated workflow. If the default sandbox cannot run a task, Claude Code stops and asks the human (`human-gate-policy.md`) — it never escalates.
3. **Pinned CLI.** Codex CLI is pinned to a crash-free version (0.140.0 verified on this machine; see `.codex/CODEX_SETUP_NOTES.md`).
4. **Bounded delegation.** `max_depth = 1` (`.codex/config.toml`) so a Codex subagent cannot spawn further subagents, and a subagent never broadens the parent session's sandbox/approval.
5. **Handoff brief still required.** The task packet (`.codex/task-template.md`) is still produced and passed to Codex as the prompt — automation does not remove the written scope / out-of-scope / verification contract.
6. **Human gate unchanged.** All Mandatory Gate Conditions in `human-gate-policy.md` (auth/authorization, DB schema, infra/deploy, dependency changes, CI config, protected files, ADR-worthy decisions, High/Critical risk, security-relevant changes) still require human approval **before** the automated implementation step runs.

## Consequences

- Level 2 (Semi-Autonomous) no longer needs a manual human execution step for Low/Medium risk work: Claude Code triggers Codex and resumes with local review. Humans still own PR approval and merge.
- The independence guarantee shifts from "a human runs Codex" to "Codex runs in its own sandboxed session that Claude Code cannot elevate." The bypass-flag prohibition (point 2) is what preserves it.
- If the pinned CLI is unavailable, or a task genuinely needs elevated access, the workflow falls back to manual execution (ADR-004's model) rather than escalating privileges.

## Alternatives

- **Keep ADR-004 (manual execution).** Rejected: does not address token economics; adds a human step to every Low/Medium task.
- **Allow elevated/bypass invocation when the default sandbox fails.** Rejected (unchanged from ADR-004): removes the independent approval boundary.
- **Implement via Claude Code internal subagents instead of Codex.** Rejected for the token goal: internal subagents consume the same Claude Code budget that motivated this change.

## Follow-up

- Pin Codex CLI to 0.140.0 and verify a `workspace-write` dry run before relying on automated invocation (`.codex/CODEX_SETUP_NOTES.md`).
- Re-evaluate the pinned version when a fixed Codex release ships.

## Related Documents

- `docs/decisions/ADR-001-separate-claude-code-and-codex-roles.md`
- `docs/decisions/ADR-004-use-manual-codex-execution-instead-of-nested-codex-exec.md` (superseded)
- `docs/harness/handoff-policy.md`, `docs/harness/autonomy-levels.md`, `docs/harness/human-gate-policy.md`
- `.codex/CODEX_SETUP_NOTES.md`, `.codex/config.toml`
- `docs/failures/FAILURE-001-nested-codex-exec-sandbox-conflict.md`
