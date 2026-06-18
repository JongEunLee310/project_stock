# Codex Orchestration Policy

This document defines when a Codex session should spawn the custom agents defined in `.codex/agents/`. Codex only spawns a subagent when explicitly asked to in the session prompt — these agents are not invoked automatically.

## Principles

- Default to a single Codex session for most work.
- Spawn a subagent only for complex work, parallel exploration, review separation, or test-failure analysis.
- Subagents must never exceed the parent session's sandbox and approval policy. A per-agent `sandbox_mode` may further restrict the agent (e.g. `test_debugger`'s `read-only`), but must not broaden the parent session's permissions.
- Pass subagents a summary and task packet, not the full conversation — control token usage.
- The parent Codex session (or Claude Code, on the final PR) makes the final call; subagents report findings, not decisions.
- `max_depth = 1` in `.codex/config.toml` blocks subagents from spawning further subagents. See `.codex/CODEX_SETUP_NOTES.md` for whether this is confirmed to be enforced in the current Codex CLI version.

## Work Levels

### Level 1: Trivial edit

Examples: typo fix, single-file small edit, one-line README change.

Handling: no subagent — handle directly in the session.

### Level 2: Pre-implementation exploration

Examples: feature touches unfamiliar code, affected files unclear, need to trace an execution path before changing it.

Handling: spawn `codebase_explorer`.

### Level 3: Well-defined feature implementation

Examples: a task packet exists, an API addition, a change with clear tests.

Handling:
1. `codebase_explorer` if related files are still unclear.
2. `feature_worker` to implement.
3. `pr_reviewer` to self-review the diff.

### Level 4: Bug fix

Examples: a failing test, a reproducible runtime error, a CI failure with a log.

Handling:
1. `test_debugger` to diagnose the root cause (read-only — it does not apply the fix).
2. `bugfix_worker` to apply the minimal fix, if the cause is confirmed (skip `test_debugger` and go straight to `bugfix_worker` if the cause is already known).
3. Re-run the relevant tests.
4. `pr_reviewer` to self-review the diff.

### Level 5: Refactor

Examples: deduplication, function extraction, type cleanup, module boundary cleanup.

Handling:
1. `codebase_explorer` to map the area.
2. `refactor_worker` to apply the change.
3. `pr_reviewer` to self-review the diff.

### Level 6: High-risk work

Examples: authentication/authorization changes, payment/settlement changes, database migrations, deployment or infrastructure configuration, security-relevant changes.

Handling: do not proceed without explicit human approval. Claude Code's architecture review is required first (see `docs/harness/human-gate-policy.md`). At least two independent verification steps are required. Production deployment and production database writes are never performed by any agent.

## Spawn Prompt Examples

### PR review

```text
Review this branch against main.
Spawn:
- codebase_explorer to map affected paths
- pr_reviewer to find correctness, security, test risks
Wait for all results and summarize blocking issues first.
```

### Feature implementation

```text
Implement the provided task packet.
Use codebase_explorer first if related files are unclear.
Then use feature_worker for implementation.
After implementation, use pr_reviewer to review the diff.
Do not change files outside the allowed scope.
```

### Test failure analysis

```text
Analyze the failing tests.
Use test_debugger to inspect failure logs and identify root cause (read-only).
Use bugfix_worker to apply only the minimal fix once the cause is confirmed.
Do not delete failing tests.
Report commands run and remaining risks.
```

## Prohibited for Every Subagent

- Production deployment.
- Production database access or writes.
- Reading or printing secrets, tokens, or credentials.
- Direct commits to `main`, `fastapi`, or `spring-boot`.
- Unapproved dependency additions.
- Deleting or skipping a failing test to make CI pass.
- Declaring work complete without running the available verification commands, or without stating why they could not be run.

## Related

- `.codex/agents/` — the 6 custom agent definitions.
- `.codex/CODEX_TASK_PACKET_TEMPLATE.md` — task packet format used to hand work to `feature_worker` / `bugfix_worker`.
- `.codex/instructions.md` — Codex's overall role and boundaries in this template.
- `docs/harness/handoff-policy.md`, `docs/harness/human-gate-policy.md` — the Claude Code side of this workflow.
