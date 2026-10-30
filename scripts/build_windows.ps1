# P1 verification/build for Windows (no installer yet).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Push-Location $Root
try {
  pnpm -r build
  pnpm -r lint
  pnpm -r typecheck
  pnpm -r test
  Push-Location "$Root\runtime"
  try {
    uv run ruff format --check src tests
    uv run ruff check src tests
    uv run mypy src
    uv run pytest -q
  } finally {
    Pop-Location
  }
  Write-Host "P1 checks passed."
} finally {
  Pop-Location
}
