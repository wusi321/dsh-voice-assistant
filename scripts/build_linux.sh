#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT"
pnpm -r build
pnpm -r lint
pnpm -r typecheck
pnpm -r test

cd "$ROOT/runtime"
uv run ruff format --check src tests ../scripts
uv run ruff check src tests ../scripts
uv run mypy src
uv run pytest -q
echo "P1 checks passed."

