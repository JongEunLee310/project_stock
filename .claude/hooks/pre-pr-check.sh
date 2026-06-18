#!/usr/bin/env bash
set -euo pipefail

# Only run before PR creation
input=$(cat 2>/dev/null || echo "")
if [ -n "$input" ] && ! echo "$input" | grep -q 'gh pr create'; then
  exit 0
fi

echo "pre-pr-check: running lint, typecheck, and tests..."
uv run ruff check .
uv run mypy .
uv run pytest
echo "pre-pr-check: passed."
exit 0
