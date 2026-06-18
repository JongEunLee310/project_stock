# Fix CI Failure

Claude Code has already diagnosed the root cause and recorded it in the Codex handoff task or in an inline note on the PR, per `docs/harness/completion-commit-policy.md`. Read that diagnosis first, then read the CI failure output, the related PR diff, and `.codex/instructions.md`.

Implement the fix Claude Code's diagnosis points to. If the actual cause differs from the diagnosis once you investigate the code, fix the real cause and say so explicitly when reporting back — do not silently fix something else.

Fix the root cause without weakening tests, build checks, lint, typecheck, or CI rules. Run the closest local verification command before reporting completion.
