# Default Workflow

## 1. Issue Creation

Create an issue with purpose, background, requirements, out-of-scope items, verification expectations, and documentation impact.

## 2. Claude Plan

Claude Code reads the issue and relevant docs, then creates a plan.

## 3. Codex Handoff

Claude Code creates a Codex handoff task using `.codex/task-template.md`.

## 4. Codex Implementation

Codex implements only the handoff scope, updates tests, and runs local verification.

## 5. PR Creation

Create a PR using `.github/pull_request_template.md`.

## 6. CI Feedback

GitHub Actions runs project-specific verification. CI failures are feedback for Codex.

## 7. Claude Local Review

Claude Code reviews the PR locally after PR creation.

## 8. Review Record

Record local review in `tmp/claude-pr-review.md` and publish to the PR conversation when useful.

## 9. Document Promotion

Promote reusable review findings into docs, ADRs, failure records, or knowledge base entries.

## 10. Human Merge

Humans approve and merge after risk, CI, and review status are acceptable.
