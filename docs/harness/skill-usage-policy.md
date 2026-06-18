# Skill Usage Policy

External AI skills may be used when they match the task and have been installed intentionally.

## Strategy

This repository does not vendor external skills. Skills from `everything-claude-code` or other external sources must be installed manually by each team using this template.

The `.claude/skills/` and `.codex/skills/` directories must not exist in this repository. Skills are not committed here.

## Rules

- Install external skills manually into your local Claude Code environment.
- Review skill instructions before relying on them.
- Do not treat external skills as project policy unless documented here.
- Record durable workflow changes in `docs/harness/` or `docs/knowledge/`.

## Documenting Skill Use

If a skill meaningfully changes how this project's workflow operates, add a note to `docs/knowledge/workflow.md` describing the effect.

## Exclusions

This template does not bundle external skills or configure automatic skill installation.
