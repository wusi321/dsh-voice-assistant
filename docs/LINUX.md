# Ubuntu 22.04

## P1 prerequisites

- Python 3.11 (uv can manage it)
- `uv`
- Node.js 24 (or ≥22)
- pnpm 9.15.x
- DSH web/desktop 0.2.1-rc.3 for plugin work

P2 will additionally require PortAudio (`libportaudio2`), PipeWire or
PulseAudio, and the usual build tools for native wheels.

## Build and test

```bash
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

```bash
cd runtime
uv run voice-runtime doctor
uv run voice-runtime daemon --fake-audio
```

## Paths

| Purpose | Path |
|---|---|
| Config | `$XDG_CONFIG_HOME/dsh-voice-assistant` or `~/.config/dsh-voice-assistant` |
| Data / runtime state | `$XDG_DATA_HOME/dsh-voice-assistant` or `~/.local/share/dsh-voice-assistant` |
| Discovery | `<data>/runtime.json` |
| Models (planned) | `<data>/models` |

## Audio (P2, Linux pending)

P2 implements device enumeration, separate input/output streams, resampling,
device switching, and restart-on-error. The Mock backend tests run on
`ubuntu-latest` CI. **Real PipeWire/PulseAudio hardware verification is still
pending**: default source/sink, 44.1/48/16 kHz, hot-plug, and AEC need an Ubuntu
machine with audio. The Runtime does not assume 16 kHz hardware input.

## Service (P9)

A `systemd --user` unit is planned; P1 only runs in the foreground. Do not add a
unit that assumes a display server: the Runtime is headless and independent of
DSH.

## CI

`ubuntu-latest` runs the Python and Node jobs. Real audio and models are not
exercised in P1 CI.
