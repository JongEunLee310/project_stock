# Feedback Loop Policy

The default feedback loop is PR and CI based.

## Flow

Issue
→ Claude planning
→ Codex implementation
→ PR
→ CI
→ CI failure feedback
→ Codex fix
→ Claude local review
→ Human merge

## Principles

- CI detects project-specific verification failures.
- Codex fixes implementation and test failures.
- Claude Code reviews scope, reasoning, docs, and risk.
- Humans approve final merge.

## Records

Important feedback should be captured in PR comments, feedback loop records, failure records, ADRs, or knowledge base updates.

## Completion, Commit, and CI Response

See `completion-commit-policy.md` for how Claude Code classifies, commits, pushes, and opens a PR once work is judged complete, and how CI failures are diagnosed by Claude Code and fixed by Codex.
