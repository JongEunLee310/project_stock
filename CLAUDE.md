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

## Document Language

문서(ADR `docs/decisions/`, 설계 `docs/designs/`, 리뷰 기록 `docs/reviews/`)의 본문
산문은 한국어로 작성한다. 섹션 헤더·Status 라벨 등 고정 라벨과 코드 기호(식별자·경로·
enum 값)는 영어로 유지한다. 상세는 `docs/harness/design-record-policy.md`.

## Branch Rule

Before handing off any task, verify that Codex will work on a feature branch created from the latest `main`. If the current branch is behind `main`, instruct Codex to pull and rebase before starting implementation.

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
