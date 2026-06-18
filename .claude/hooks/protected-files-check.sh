#!/usr/bin/env bash
set -euo pipefail

PROTECTED_PATTERNS=(
  "AGENTS.md"
  "CLAUDE.md"
  ".codex/instructions.md"
  ".github/workflows/ci.yml"
  "docs/harness/"
  "docs/decisions/"
  "docs/failures/"
)

changed=$(git diff HEAD --name-only 2>/dev/null || echo "")

if [ -z "$changed" ]; then
  echo "protected-files-check: no changes detected."
  exit 0
fi

violations=()
while IFS= read -r file; do
  for pattern in "${PROTECTED_PATTERNS[@]}"; do
    if [[ "$file" == "$pattern" || "$file" == "${pattern}"* ]]; then
      violations+=("$file")
      break
    fi
  done
done <<< "$changed"

if [ ${#violations[@]} -gt 0 ]; then
  for v in "${violations[@]}"; do
    echo "protected-files-check: $v is a protected file. Explicit permission required in the handoff."
  done
  exit 1
fi

echo "protected-files-check: no protected files modified."
exit 0
