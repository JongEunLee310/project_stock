# Branch Strategy

## Purpose

This template is distributed as three branches instead of three repositories. This document explains why, and what is allowed to differ between them.

## Branches

- `main` — common Harness Engineering template. Framework-agnostic. Contains no application code, no runnable starter, no framework-specific CI.
- `fastapi` — FastAPI runnable starter plus the common harness layer from `main`.
- `spring-boot` — Spring Boot runnable starter plus the common harness layer from `main`.

## What Belongs Where

### Common harness layer (all branches)

- `AGENTS.md`, `CLAUDE.md`, `.codex/`
- `.github/pull_request_template.md`
- `.claude/commands/`, `.claude/hooks/`
- `docs/harness/`, `docs/knowledge/` (workflow and policy content), `docs/decisions/`, `docs/failures/`, `docs/feedback/`, `docs/archive/`

This layer should read the same across branches except for framework-specific wording in README files.

### Framework-specific layer (`fastapi`, `spring-boot` only)

- Runnable starter application code.
- Framework-specific test suite.
- Framework-specific CI workflow (lint, typecheck, build, test commands).
- Framework-specific sections of the branch README.

## Synchronization Rule

Common policy changes (harness docs, PR template, hooks, commands, `.codex/` instructions) should be made on one branch and then ported to the other two branches so the harness layer does not drift between branches.

Framework-specific changes (starter code, framework CI, framework README sections) belong only in their own branch and should not be ported to `main` or to the other framework branch.

## Drift Rules Are Out of Scope for `main`

Code drift and structure drift rules (linting conventions, directory layout rules, architecture checks) are project- and framework-specific. They must not be added to `main`. Each framework branch — and each project created from a framework branch — defines its own drift rules.

## Choosing a Branch for a New Project

- Starting a new FastAPI service: branch from `fastapi`.
- Starting a new Spring Boot service: branch from `spring-boot`.
- Starting a project in a framework not yet represented, or building a new framework branch: branch from `main` and add the framework-specific layer.

See `docs/knowledge/template-usage.md` for the full new-project setup flow.
