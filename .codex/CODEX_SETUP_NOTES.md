# Codex Setup Notes

Open items to confirm against the Codex CLI version actually in use, before relying on them in production workflows.

## Officially documented fields, local CLI verification pending

The Codex documentation describes these fields as supported for project-scoped custom agents and global agent settings. They are not unconfirmed in the spec sense — what is still pending is verifying the *locally installed* Codex CLI version actually implements them as documented, since CLI behavior can lag or diverge from the docs.

- `sandbox_mode` in `.codex/agents/*.toml` — documented values `read-only` / `workspace-write`. Verify the local CLI honors a per-agent sandbox mode as set here.
- `model_reasoning_effort` in `.codex/agents/*.toml` — documented values `low` / `medium` / `high`. Verify the local CLI applies it per agent.
- `nickname_candidates` in `.codex/agents/*.toml` — cosmetic. Verify it does not error out on the local CLI version before depending on it.
- `[agents]` block in `.codex/config.toml` (`max_threads`, `max_depth`) — verify the local CLI reads this table and that `max_depth = 1` actually blocks recursive subagent delegation as intended.

## Why this matters

Codex subagents spend more tokens than a single session (separate model/tool calls per subagent), so `max_depth = 1` is intended to prevent a subagent from spawning further subagents unbounded. If the running Codex CLI version does not support this field, that protection does not exist — the human operator should verify it manually (e.g., by deliberately asking a subagent to spawn another and confirming it is refused) before assuming it is enforced.

## How to verify

1. Run `codex --version` and check the changelog/docs for the fields above.
2. Start a Codex session in this repo and confirm `.codex/agents/*.toml` files are picked up as custom agents (e.g., they are offered when explicitly requested).
3. Update this file with the confirmed/unconfirmed status once checked, rather than deleting it.
