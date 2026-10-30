# Contributing

## Ground rules

- Read `AGENTS.md` in the workspace root, `docs/ARCHITECTURE.md`, and `docs/PROTOCOL.md` before changing code.
- Do not modify `GDDXX-Jarvis` or `dsh-pet`; they are read-only upstream references.
- Keep the Python Runtime independent from DSH. DSH is the only Agent execution core.
- Every new module needs tests. Do not remove failing tests to make CI pass.
- Do not add a dependency without recording its license in `NOTICE.md`.

## Development setup

```bash
pnpm install
uv sync --project runtime
```

Run the checks:

```bash
pnpm lint
pnpm typecheck
pnpm test
uv run --project runtime ruff check runtime/src runtime/tests
uv run --project runtime mypy runtime/src
uv run --project runtime pytest runtime/tests
```

## Commit and review

- Work in small, reviewable changes.
- Separate commits for protocol, runtime, plugin, and CI changes.
- Report untested platform-specific behavior explicitly.
- Do not claim a feature is complete when it is only a stub.

## License

By contributing, you agree that your contribution is licensed under the
Apache License, Version 2.0.
