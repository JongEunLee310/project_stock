# Garbage Collection Policy

Garbage collection keeps documentation and AI workflow artifacts useful.

## Actions

- Keep: leave the artifact unchanged.
- Update: revise outdated but useful content.
- Merge: combine duplicated content.
- Archive: move historical content to `docs/archive/`.
- Delete: remove content that has no future value and is safe to remove.

## Targets

- Outdated ADRs.
- Old failure records.
- Duplicated policies.
- Outdated workflow docs.
- Unused prompts.
- Obsolete hooks.
- Stale knowledge base entries.

## Rules

Prefer archive over delete when historical context may still matter. Do not delete protected or decision-related documents without explicit human approval.
