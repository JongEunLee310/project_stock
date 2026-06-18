# MCP Permission Matrix

No MCP server is configured in this template yet (no `.mcp.json`). This document defines the permission boundaries to apply when one is added, so access is scoped per subagent from the start rather than granted broadly after the fact.

## Matrix

| Agent | Filesystem | GitHub | Test Runner | CI Logs | Docs | DB | Deploy | Monitoring |
|---|---|---|---|---|---|---|---|---|
| Main session | Read/Write | Read/Write | Run | Read | Read/Write | None | None | Read |
| `architect-planner` | Read | Read | None | None | Read | None | None | None |
| `codex-task-writer` | Read | Read | None | None | Read | None | None | None |
| `implementation-guardian` | Read | Read | None | Read | Read | None | None | None |
| `code-reviewer` | Read | Read/Comment | Run (read-only verification) | Read | Read | None | None | None |
| `test-debugger` | Read | Read | Run | Read | Read | None | None | None |

## Principles

- Database write access is denied for every agent, including the main session.
- Production deployment access is denied for every agent, including the main session.
- Secret and credential read access is denied for every agent, including the main session.
- `architect-planner`, `codex-task-writer`, and `implementation-guardian` are read-only with respect to the filesystem.
- `code-reviewer` and `test-debugger` may run tests/lint/build commands but must not commit, push, or merge.
- "GitHub: Read/Write" for the main session covers issue and PR creation, comments, and reviews — it does not cover merging, branch protection changes, or repository settings changes.
- "GitHub: Read/Comment" for `code-reviewer` means it may draft review content; only the main session or a human posts it.
- Any MCP server that exposes deploy, production DB, or secret-manager tools must not be granted to any agent listed above without a documented exception and human approval, per `docs/harness/human-gate-policy.md`.

## When an MCP Server Is Added

1. Add a row only if the new server expands what an existing agent can already do conceptually (e.g., a GitHub MCP server replacing `gh` CLI calls keeps the same Read/Write boundary as today).
2. If the server exposes a capability not in this table (e.g., a new monitoring or alerting tool), add a column and assign access per the Principles above before any agent is allowed to use it.
3. Record the addition in `docs/decisions/` if it changes an agent's effective permissions, per `docs/knowledge/template-usage.md`.

## Related

- `.claude/ORCHESTRATION.md` — subagent dispatch.
- `docs/harness/human-gate-policy.md` — approval gate for risk exceptions.
