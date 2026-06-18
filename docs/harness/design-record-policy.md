# Design Record Policy

Claude Code must write a skeleton-level design document in `docs/designs/` before creating a Codex handoff when any of the following apply:

- A new domain or subdomain is introduced.
- A new database table is created.
- A new external dependency or adapter boundary is defined.
- An architectural decision with future impact is made.

## Document Location

`docs/designs/<issue-number>-<short-slug>.md`

## Document Level

Skeleton only. No implementation code.

- Models: table name, field names, types, constraints.
- APIs: HTTP method, path, request schema name, response schema name.
- Services: function signatures and one-line responsibility.
- Repositories: function signatures and one-line responsibility.
- Dependencies: explicit list of other domains this design depends on.

No SQL queries, no business logic code, no full class bodies.

## When to Skip

- Pure test additions.
- Style or documentation changes.
- Bug fixes that do not alter schema or domain boundaries.

## Related

- `docs/decisions/` — for ADRs when an approach is chosen over alternatives.
- `docs/knowledge/workflow.md` — step 2a of the default workflow.
