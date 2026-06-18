#!/usr/bin/env bash
set -euo pipefail

echo "pre-pr-check: running lint and tests..."
uv run ruff check .
uv run pytest
echo "pre-pr-check: passed."
exit 0
