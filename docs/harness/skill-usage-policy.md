# Skill Usage Policy

External AI skills may be used when they match the task and have been installed intentionally.

## Strategy

The `must not exist` / `not committed` rule below applies to the **template repository** during template authoring — the template ships without vendored skills so each team installs what it needs.

A **project derived from the template** may install and commit skills it intentionally uses. This project (`project_stock`) does so: `.claude/skills/` and `.codex/skills/` are committed, and the backend skills `fastapi-patterns`, `python-testing`, `api-design` are activated for implementation and review. Activation and per-skill status are recorded in `docs/agent/skill-policy.md`; the effect on the workflow is noted in `docs/knowledge/workflow.md`.

### Template repository rule

In the template repository, the `.claude/skills/` and `.codex/skills/` directories must not exist and skills are not committed. Skills from `everything-claude-code` or other external sources are installed manually by each team using the template.

## Rules

- Install external skills manually into your local Claude Code environment.
- Review skill instructions before relying on them.
- Do not treat external skills as project policy unless documented here.
- Record durable workflow changes in `docs/harness/` or `docs/knowledge/`.

## Documenting Skill Use

If a skill meaningfully changes how this project's workflow operates, add a note to `docs/knowledge/workflow.md` describing the effect.

## Exclusions

This template does not bundle external skills or configure automatic skill installation.
