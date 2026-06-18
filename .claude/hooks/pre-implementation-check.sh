#!/usr/bin/env bash
set -euo pipefail

echo "pre-implementation-check: verifying Python and uv are available..."

if ! command -v python3 &>/dev/null; then
  echo "pre-implementation-check: python3 not found."
  exit 1
fi

if ! command -v uv &>/dev/null; then
  echo "pre-implementation-check: uv not found. Install from https://docs.astral.sh/uv/"
  exit 1
fi

echo "pre-implementation-check: passed."
exit 0
