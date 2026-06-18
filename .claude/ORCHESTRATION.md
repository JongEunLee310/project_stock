# Orchestration Policy

This document defines how the main Claude Code session dispatches work to the subagents in `.claude/agents/`. It does not restate the workflow states or role boundaries already defined in `docs/harness/orchestration-state-policy.md` and `docs/harness/agent-role-policy.md` — read those first.

## Main Session Role

The main Claude Code session is the orchestrator. It does not need a dedicated "orchestrator" subagent. It:

- Interprets the user's request.
- Classifies task difficulty (see Dispatch Table below).
- Selects and invokes the relevant subagent(s).
- Integrates subagent results.
- Reviews the final Codex task packet before it is handed to the human operator.
- Decides whether a human gate condition applies (`docs/harness/human-gate-policy.md`).
- Writes the final report to the user.

## Dispatch Table

| Task Type | Example | Subagent |
|---|---|---|
| Trivial edit | Typo fix, single-line doc change, obvious one-file fix | None — main session handles it directly |
| Scope/impact analysis needed | Unclear affected files, design decision needed before implementation | `architect-planner` |
| Implementation work | Feature, bug fix, test addition, refactor | `architect-planner` → `codex-task-writer` → (human runs Codex manually) → `implementation-guardian` → `code-reviewer` |
| Failure analysis | Test, lint, typecheck, build, or CI failure | `test-debugger` |
| High/Critical risk task | Auth, payments, infra, DB migration, deployment | Human gate first per `docs/harness/human-gate-policy.md`; no subagent proceeds without it |

## Subagent Invocation Principles

- Do not invoke a subagent for trivial work the main session can do directly.
- Pass subagents a summary and task packet, not the entire conversation history, to control token usage.
- Do not invoke more subagents in parallel than the task actually needs.
- The main session integrates subagent outputs and owns the final decision and report; subagents do not report directly to the user.

## Codex Integration

No subagent invokes Codex CLI. `codex-task-writer` only produces the handoff document. The human operator runs Codex manually in a separate session, per `docs/harness/handoff-policy.md` and `docs/decisions/ADR-002-use-manual-codex-execution-instead-of-nested-codex-exec.md`.

## Prohibited for Main Session and All Subagents

- Production deployment.
- Production database access or writes.
- Reading or printing secrets, tokens, or credentials.
- Direct commits to `main`, `fastapi`, or `spring-boot`.
- Unapproved dependency additions.
- Large-scale refactoring outside the requested scope.
- Marking a risky change complete without the verification commands in `docs/harness/task-classification-policy.md` having actually been run.

## Related

- `docs/harness/orchestration-state-policy.md` — workflow states.
- `docs/harness/agent-role-policy.md` — role boundaries between Claude Code, Codex, CI, and human.
- `docs/harness/task-classification-policy.md` — risk classification used to decide gate requirements.
- `docs/harness/human-gate-policy.md` — gate conditions.
- `.claude/MCP_PERMISSION_MATRIX.md` — tool/data access boundaries per subagent.
