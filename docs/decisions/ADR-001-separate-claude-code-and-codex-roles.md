# ADR-001: Separate Claude Code And Codex Roles

## Status

Accepted

## Context

AI-assisted development becomes harder to review when one agent plans, implements, reviews, and records decisions without clear boundaries.

## Decision

Separate responsibilities:

- Claude Code = orchestrator and reviewer.
- Codex = implementer.
- CI = feedback sensor.
- Human = final owner.

## Alternatives

- Use one agent for planning, implementation, and review.
- Run Claude Code review automatically in GitHub Actions.
- Let CI own all review feedback.

## Consequences

Role separation makes scope, review, and accountability clearer. It adds handoff overhead, but that overhead creates better review records and safer human approval.

## Follow-up

Project-specific templates should customize verification commands and protected files.

## Related Documents

- `docs/harness/agent-role-policy.md`
- `docs/harness/handoff-policy.md`
- `docs/harness/local-review-policy.md`
