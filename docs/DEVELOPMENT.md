# Development

## Layout

```text
packages/protocol   TypeScript event schemas + binary PCM codec
packages/plugin     DSH Host + Client plugin
runtime/            Python Voice Runtime (uv)
models/             manifest + schema; weights are not committed
config/             default runtime config + generated schema
scripts/            model downloader and helper scripts
docs/               architecture, protocol, security, platform, roadmap
```

## Commands

```bash
pnpm install
pnpm -r build
pnpm -r lint
pnpm -r typecheck
pnpm -r test

cd runtime
uv sync --python 3.11
uv run ruff format src tests
uv run ruff check src tests
uv run mypy src
uv run pytest
```

The protocol package must be built before the plugin is typechecked/built
because the plugin imports its emitted types. Root `pnpm typecheck` and
`pnpm test` do this automatically.

## Cross-language protocol changes

1. Change `packages/protocol/src/events.ts` and/or `binary.ts`.
2. Update `runtime/src/voice_runtime/transport/protocol.py` to match.
3. Update the golden frame test in `runtime/tests/test_protocol.py`.
4. Run both test suites.
5. Update `docs/PROTOCOL.md` and bump `PROTOCOL_VERSION` for breaking changes.

## Testing conventions

- Python tests live in `runtime/tests` and use pytest + pytest-asyncio.
- TypeScript tests live next to each package in `test/` and use Vitest.
- No test may require a real microphone, speaker, model file, or DSH install.
- Fake engines (`runtime/src/voice_runtime/engines/fake.py`) are for tests and
  `--fake-audio`; they are not a product fallback.
- Do not remove or skip a failing test to make CI green.

## Logging

Use `voice_runtime.utils.logging` and its redaction filter. Never log tokens,
raw audio, or recognized text by default.

## Branching

`main` is the integration branch; work in small feature branches. Do not merge
the history of `GDDXX-Jarvis` or `dsh-pet`; they are read-only references.
