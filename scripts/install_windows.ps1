# P1 development bootstrap for Windows.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "== DSH Voice Assistant: install (Windows) =="
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
  throw "pnpm is required (pnpm 9.15.x)."
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  throw "uv is required (https://docs.astral.sh/uv/)."
}

Push-Location $Root
try {
  pnpm install
  Push-Location "$Root\runtime"
  try {
    uv sync --python 3.11
  } finally {
    Pop-Location
  }
  Write-Host "Install complete. Run: pnpm -r test; cd runtime; uv run voice-runtime doctor"
} finally {
  Pop-Location
}
