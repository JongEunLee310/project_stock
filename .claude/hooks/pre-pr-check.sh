#!/usr/bin/env bash
set -euo pipefail

# Only run before PR creation
input=$(cat 2>/dev/null || echo "")
# 입력이 비었거나 'gh pr create'가 아니면 즉시 종료한다.
# (이전에는 -n 검사 때문에 입력이 비면 조기 종료를 건너뛰어 모든 Bash 호출마다 전체 검증이 돌았다.)
if ! echo "$input" | grep -q 'gh pr create'; then
  exit 0
fi

echo "pre-pr-check: running lint, typecheck, and tests..."
uv run ruff check .
uv run mypy .
uv run pytest
echo "pre-pr-check: passed."
exit 0
