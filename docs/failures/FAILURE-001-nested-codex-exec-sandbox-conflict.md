# FAILURE-001: Nested Codex Exec Sandbox Conflict

## Status

Accepted

## Background

During dogfooding, Claude Code attempted to invoke Codex CLI directly via `codex exec` from inside its own Bash tool, intending to automate the full Issue → handoff → implementation → PR pipeline without a human running Codex separately.

## Failed Approach

Claude Code ran `codex exec --cd <worktree> -s read-only|workspace-write ...` to have Codex implement a handoff task non-interactively, inside a session already running under the harness's own tool execution layer.

## Failure Cause

`codex exec` crashed with exit code 133 on the first shell tool call under both `read-only` and `workspace-write` sandbox modes. The only available workarounds were `--dangerously-bypass-approvals-and-sandbox` or `-s danger-full-access`, both of which the harness's auto-mode classifier blocked as unapproved autonomous agent spawning. Beyond the immediate sandbox crash, granting those flags would have created a nested autonomous agent (Claude Code spawning a full-access Codex shell) with no independent approval gate — a structural problem, not just an environment bug.

## Impact

The dogfooding run could not exercise an automated Claude Code → Codex handoff in a single session. No application code or protected files were affected; only the orchestration mechanism was blocked.

## Replacement Decision

Originally (ADR-004): Claude Code created the handoff document only, and the human operator ran Codex manually in a separate session. **This has since been superseded by ADR-005**, which allows Claude Code to invoke `codex exec` automatically under the default sandbox once the Codex CLI is pinned to a crash-free version — the retry conditions below were met. Manual execution remains the fallback when automated invocation is unavailable. See `docs/decisions/ADR-005-allow-claude-code-to-invoke-codex-exec.md` and `docs/decisions/ADR-004-use-manual-codex-execution-instead-of-nested-codex-exec.md` (superseded).

## Retry Conditions

These conditions were the bar for resuming direct `codex exec` invocation; ADR-005 accepts automated invocation now that they hold:

- The sandbox crash is root-caused and avoidable (the SIGTRAP regression was isolated to specific Codex CLI versions; pinning to a crash-free version, 0.140.0, sidesteps it), confirmed with `read-only` sandbox succeeding on a trivial command.
- Automated invocation stays within the **default** sandbox (`read-only` / `workspace-write`) only. Elevated/full-access runs remain forbidden in automated workflows and a Human Gate condition (`docs/harness/human-gate-policy.md`); the default-sandbox automation in ADR-005 is not such a run.

## Related Documents

- `docs/decisions/ADR-005-allow-claude-code-to-invoke-codex-exec.md`
- `docs/decisions/ADR-004-use-manual-codex-execution-instead-of-nested-codex-exec.md` (superseded)
- `docs/harness/handoff-policy.md`
- `docs/harness/human-gate-policy.md`
- `docs/harness/autonomy-levels.md`
- `docs/feedback/dogfooding-plan.md`
