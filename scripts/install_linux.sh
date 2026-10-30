#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== DSH Voice Assistant: install (Linux) =="
command -v pnpm >/dev/null || { echo "pnpm 9.15.x is required"; exit 1; }
command -v uv >/dev/null || { echo "uv is required (https://docs.astral.sh/uv/)"; exit 1; }

cd "$ROOT"
pnpm install
cd "$ROOT/runtime"
uv sync --python 3.11
echo "Install complete. Run: pnpm -r test; cd runtime; uv run voice-runtime doctor"
