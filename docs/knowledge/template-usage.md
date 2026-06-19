# Template Usage Guide

## Purpose

How to start a new project from this template and run the Claude Code + Codex workflow day to day.

## 1. Choose a Branch

Pick `fastapi` for a FastAPI service, `spring-boot` for a Spring Boot service, or `main` if neither framework fits and you intend to add your own framework layer. See `docs/harness/branch-strategy.md`.

## 2. Copy or Start From a Branch

Clone the template repository and check out the chosen branch, or use it as a GitHub template/branch source for a new repository. Remove this guide's references to the template repository itself once the new project has its own identity.

## 3. Customize `AGENTS.md`

Update agent responsibilities, scope boundaries, and protected files to match the new project. Keep the Claude Code / Codex role split unless the project has a documented reason to change it.

## 4. Customize `CLAUDE.md`

Update Claude Code's required-context file list and review posture for the new project's directory layout and risk areas.

## 5. Fill `docs/knowledge/domain-knowledge.md`

Add the business rules, domain vocabulary, and project-specific constraints that an agent would otherwise have to rediscover from code.

## 6. Update CI Commands

Edit `.github/workflows/ci.yml` to match the project's real verification commands (lint, typecheck, test, build). Do not weaken or remove checks inherited from the framework branch without a documented reason.

## 7. Write the First Issue

State purpose, background, requirements, out-of-scope items, verification expectations, and documentation impact, per `docs/knowledge/workflow.md`.

## 8. Claude Code Creates a Codex Handoff Task

Claude Code reads the issue and relevant docs, then writes a handoff task using `.codex/task-template.md`, including scope, protected files, requirements, verification commands, and risk level.

## 9. Codex Implements

Codex implements only the handoff scope, updates tests, and runs local verification commands before opening a PR.

## 10. CI Feedback Is Handled

GitHub Actions runs the project's verification commands. Codex treats CI failures as feedback and fixes them within the handoff scope, or escalates if the fix requires scope outside the handoff.

## 11. Claude Code Performs Local PR Review

After PR creation, Claude Code reviews the diff, related issue, handoff task, CI result, protected file changes, and documentation impact, per `docs/harness/local-review-policy.md`.

## 12. Record Review Results in GitHub

Publish the local review record with one of:

```bash
gh pr comment <PR_NUMBER> --body-file docs/reviews/pr-<PR_NUMBER>.md
gh pr review <PR_NUMBER> --comment --body-file docs/reviews/pr-<PR_NUMBER>.md
gh pr review <PR_NUMBER> --request-changes --body-file docs/reviews/pr-<PR_NUMBER>.md
```

Claude Code does not approve PRs. Humans own final approval and merge.

## 13. When to Create ADRs

Create an ADR when a decision is architectural, durable, and would be costly to silently reverse (e.g., choice of framework, agent role boundaries, data model direction). Use `docs/decisions/ADR-000-template.md`.

## 14. When to Create Failure Records

Create a failure record when an approach was tried and rejected, so future agents do not repeat it without knowing why. Use `docs/failures/FAILURE-000-template.md`.

## 15. When to Update the Knowledge Base

Update `docs/knowledge/` when a workflow step changes, a domain concept is clarified, or the same misunderstanding recurs across multiple PRs or reviews.

## 16. When to Run Garbage Collection

Run garbage collection per `docs/harness/garbage-collection-policy.md` when stale AI workflow artifacts, outdated plans, or superseded documentation accumulate enough to cause drift or confusion.
