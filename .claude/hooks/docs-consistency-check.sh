#!/usr/bin/env bash
set -euo pipefail

REQUIRED_READMES=(
  "docs/README.md"
  "docs/harness/README.md"
  "docs/decisions/README.md"
  "docs/failures/README.md"
  "docs/knowledge/README.md"
)

missing=0
for readme in "${REQUIRED_READMES[@]}"; do
  if [ ! -f "$readme" ]; then
    echo "docs-consistency-check: missing $readme"
    missing=1
  fi
done

if [ "$missing" -eq 1 ]; then
  exit 1
fi

echo "docs-consistency-check: all required README files present."
exit 0
