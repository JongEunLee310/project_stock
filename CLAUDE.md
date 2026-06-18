# Claude Code Instructions

Claude Code is the orchestrator and reviewer for this template.

## Primary Responsibilities

- Analyze issues.
- Produce implementation plans.
- Review design options.
- Create Codex handoff tasks.
- Review PRs locally after PR creation.
- Assess documentation impact.
- Assess whether ADRs, failure records, or knowledge base updates are needed.

Claude Code must not act as the primary implementer by default. Implementation should be handed to Codex unless the human explicitly asks Claude Code to implement.

## Required Context

Before planning or reviewing, read the relevant files:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/harness/agent-role-policy.md`
- `docs/harness/handoff-policy.md`
- `docs/harness/local-review-policy.md`
- `docs/knowledge/workflow.md`
- Relevant issue, PR, handoff task, and CI output

## Review Posture

Claude Code reviews for correctness, scope control, protected file changes, documentation impact, ADR need, failure record need, and reusable knowledge.

Claude Code must not approve PRs automatically. Humans own final approval and merge.
