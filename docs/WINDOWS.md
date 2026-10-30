# Windows 10/11

## P1 prerequisites

- Python 3.11 (uv can manage it)
- [uv](https://docs.astral.sh/uv/)
- Node.js 24 (or ≥22)
- pnpm 9.15.x
- DSH desktop **0.2.1-rc.3** for plugin work

## Build and test

```powershell
pnpm install
pnpm -r build
pnpm -r lint
pnpm -r typecheck
pnpm -r test

cd runtime
uv sync --python 3.11
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src
uv run pytest
```

## Run the P1 Runtime

```powershell
cd runtime
uv run voice-runtime doctor
uv run voice-runtime daemon --fake-audio
```

The daemon prints one JSON line with `port`, `pid`, and `discovery`. The
discovery file is `%LOCALAPPDATA%\dsh-voice-assistant\runtime.json` and is
removed on graceful shutdown.

## Paths

| Purpose | Path |
|---|---|
| Config | `%APPDATA%\dsh-voice-assistant` |
| Data / runtime state | `%LOCALAPPDATA%\dsh-voice-assistant` |
| Discovery | `%LOCALAPPDATA%\dsh-voice-assistant\runtime.json` |
| Models (planned) | `%LOCALAPPDATA%\dsh-voice-assistant\models` |

## Audio (P2, not implemented)

No microphone or speaker stream is opened in P1. P2 must verify WASAPI shared
mode, 48 kHz/44.1 kHz/16 kHz devices, separate input/output devices, and
unplug/replug recovery. AEC will use a software reference from the playback
scheduler, not WASAPI loopback by default.

## Known development issue

If the repository path contains non-ASCII characters, Windows Python may fail to
read uv's editable `.pth` file. Tests are unaffected because `pytest` uses
`pythonpath = ["src"]`. For the CLI, run with:

```powershell
$env:PYTHONPATH = "src"
uv run --no-sync voice-runtime doctor
```

CI uses an ASCII path and does not need this workaround.

## CI

`ubuntu-latest` and `windows-latest` run Python 3.11 lint/typecheck/tests and
Node 24 build/lint/typecheck/tests. Real audio and models are not exercised in
P1 CI.
