# AGENTS.md

Guidance for AI agents contributing to `strata-mcp`. For what the project is,
how to install it, configure it, and the `delegate_task` tool contract, read
`README.md` first — this file does not repeat it.

## Development environment

- Use `uv` for everything; do not invoke `pip` or manage a venv by hand.
  - `uv sync` — install dependencies
  - `uv run <cmd>` — run inside the project environment
- Python 3.14. `uv.lock` is committed; keep it in sync (`uv sync --frozen` must pass).

## Before you consider a change done

```bash
uv run ruff check .
uv run pyrefly check
uv run pytest
```

All three must pass. Fix what you touched; do not disable rules to go green.

## Code conventions

- Ruff enforces them (config in `pyproject.toml`): complexity capped via C901
  (max 10), import sorting, pyupgrade, bugbear, and `TRY003`.
- Types checked by pyrefly (config in `pyproject.toml`, strict preset; run
  `uv run pyrefly check`). OpenAI wire payloads use the shared `WireObject`
  alias from `client.py` — arbitrary JSON values validated at each use site.
- Raise explicit, named exceptions (see `errors.py`); do not pass long message
  strings to a bare `ValueError`/`Exception` at the raise site (TRY003).
- Type-hint everything. Model data with pydantic, not hand-rolled classes.
- Single-line docstring on functions and classes saying why they exist.
- Keep functions small and single-purpose.

## Module layout (`src/strata_mcp/`)

- `config.py` — `StrataConfig` model and `load_config()` (TOML via `tomllib`)
- `client.py` — httpx client for Strata's OpenAI-compatible API
- `result.py` — `WorkerResult` envelope and `WorkerStatus`
- `mapping.py` — self-report markers and output/error → status mapping
- `prompt.py` — the worker system prompt
- `delegation.py` — `run_delegation`: compose, call, time, map to a result
- `server.py` — MCP server, `delegate_task` tool, config-path resolution
- `errors.py` — explicit exception types

## Design invariants — do not break these

These encode decisions in `openspec/specs/`; changing them is a spec change, not
a tweak:

- The worker is **text-only by default**. File and command tools are opt-in per
  call: the caller grants directories (`read_dirs_allowed` / `write_dirs_allowed`)
  or an exact command menu (`allowed_commands`), and the server fences every one.
  No grant means no tool.
- Failures return as a `WorkerResult` with `status = error` — they are **never**
  raised to the caller.
- There is **no hard wall-clock timeout**. The optional `max_runtime_s` backstop
  is the only time bound; a slow-but-working call must not be killed.
- The caller validates every result. The worker's self-reported status is a
  hint, never trusted as correct.

## Testing

- Mocked unit tests run anywhere and must stay green offline.
- Live integration tests (`tests/test_integration.py`) are gated behind
  `STRATA_MCP_IT=1` and need a running Strata; they are skipped otherwise.
- Assert invariants of this code (valid status, populated fields, payload
  shape), never the model's generated text — it is not deterministic.
- Tests are isolated; no project-wide fixtures. Parametrize where it helps.

## Planning workflow

This project uses OpenSpec. Durable specs live in `openspec/specs/`; proposed
work lives in `openspec/changes/`. Follow propose → apply → archive; capture a
behaviour change in the specs, not only in code.
