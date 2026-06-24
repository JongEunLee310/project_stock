# Human Gate Policy

Human approval is required before proceeding when any of the following conditions apply.

## Mandatory Gate Conditions

- Authentication or authorization logic changes.
- Database schema changes.
- Infrastructure or deployment configuration changes.
- Dependency additions or version changes.
- CI configuration changes (`.github/workflows/`).
- Protected file changes not listed in the handoff.
- Architectural decisions that require an ADR.
- Abandoning an approach that requires a failure record.
- Risk level assessed as High or Critical.
- Security-relevant changes.
- Running Codex (or any implementation agent) with elevated/bypassed sandbox access (e.g., `codex exec --dangerously-bypass-approvals-and-sandbox`, `-s danger-full-access`) because the default sandbox failed.

Automated `codex exec` invocation under the **default** sandbox (`read-only` / `workspace-write`) is **not** a gate condition (per `docs/decisions/ADR-005-allow-claude-code-to-invoke-codex-exec.md`); only elevated/bypassed access is. The conditions above (auth, schema, deps, CI config, etc.) still gate the work **before** the automated implementation step runs.

## Gate Points in the Workflow

**Pre-handoff**: Claude Code must not produce a Codex handoff when a gate condition applies without documenting the condition and receiving explicit human approval first.

**Pre-merge**: Humans own final PR approval regardless of CI result and Claude local review outcome.

## Human Decision

The human decides whether to:

- Approve and proceed.
- Reduce scope to avoid the gate condition.
- Defer the task.
- Reject the task.

## What AI Must Not Do

- Proceed past a gate condition without documented human approval.
- Self-approve a gated change by declaring it low-risk without justification.
- Merge or push to main without human action.

## Related

- `task-classification-policy.md` — defines risk levels that trigger this gate.
- `handoff-policy.md` — lists stop conditions that overlap with gate conditions.
