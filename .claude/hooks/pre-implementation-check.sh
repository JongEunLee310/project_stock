#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 &>/dev/null; then
  echo "pre-implementation-check: python3 not found."
  exit 1
fi

if ! command -v uv &>/dev/null; then
  echo "pre-implementation-check: uv not found. Install from https://docs.astral.sh/uv/"
  exit 1
fi

if [ ! -f "uv.lock" ]; then
  echo "pre-implementation-check: uv.lock not found. Run 'uv sync' first."
  exit 1
fi

exit 0
