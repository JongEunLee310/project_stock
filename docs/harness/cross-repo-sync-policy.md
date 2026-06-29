# Cross-Repository Sync Policy

## Purpose

The backend (`project_stock`) and frontend (`project_stock_FE`) repositories share the same AI-assisted engineering harness. Shared governance must read the same in both repositories so an agent behaves identically regardless of which repo it is working in.

## Shared Layer (must stay in sync)

When an instruction is **not** specific to one repository's stack or domain, the same change must be applied to **both** repositories. This shared layer includes:

- `AGENTS.md`, `CLAUDE.md` (non-stack-specific rules).
- `docs/harness/` policies.
- `.codex/` instructions, templates, and agent definitions.
- `.github/pull_request_template.md`.
- Shared `docs/knowledge/` workflow and policy content.

## Repo-Specific Layer (may differ — do NOT force-sync)

Some content is legitimately different per repository and must not be forced into alignment:

- **Verification commands / tooling** — backend uses `uv run ruff/mypy/pytest`; frontend uses `pnpm lint/typecheck/test/build`.
- **Framework conventions** — e.g. frontend component/UI conventions.
- **ADR numbers** — each repo numbers its own ADRs independently, so the same decision can carry a different number (e.g. manual-codex-execution is `ADR-004` in backend, `ADR-002` in frontend). Reference each repo's own number; do not copy the other repo's number.
- **Domain content** — design records, reviews, and failures specific to that repo's code.

## Rule

- When you change a shared-layer instruction in one repo, make the equivalent change in the other repo in the same change set.
- Open parallel PRs (one per repo) and cross-reference them so reviewers can see both halves land together.
- Do not let the shared layer drift. If you find existing drift, align it toward the agreed canonical version and note it.

## Related

- `branch-strategy.md` — single-`main` branch model within each repo.
- `handoff-policy.md`, `local-review-policy.md` — shared-layer policies that must match across repos.
