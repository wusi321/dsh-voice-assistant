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

## Audio (P2, Windows verified)

`voice-runtime probe` enumerates the machine's devices; P2 verified 44.1 kHz
default input/output, 0.5 s real capture, and a 0.2 s real playback smoke test on
Windows. Capture and playback are separate streams, so different devices work.
AEC uses a software reference from the playback scheduler; real echo/barge-in
testing is still P7. Bluetooth/exclusive-mode matrices are not yet covered.

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
