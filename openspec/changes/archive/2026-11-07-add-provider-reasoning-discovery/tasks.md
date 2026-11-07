# Tasks

## 1. Provider config and profiles

- [x] 1.1 Add a `provider` field to `StrataConfig` accepting `strata | ollama | opencode-go`, defaulting to `strata`, and verify tests cover: a config without the key loads as `strata` (existing files unchanged), each accepted value loads, and an unknown value fails with a new explicit `UnknownProviderError` in `errors.py`
- [x] 1.2 Make `provider = "opencode-go"` require `api_key` at load time, failing with a new explicit exception naming the provider, and verify tests cover: go without a key is rejected at load, go with a key loads, strata/ollama keep the key optional
- [x] 1.3 Create `providers.py` with one pydantic profile per provider (connection defaults, required-header flags, fallback reasoning levels `none|low|medium|high` for strata/ollama) and pure parsing functions that read reasoning levels, default level, and provenance out of a `/models` entry, and verify unit tests cover: go-shaped `capabilities.reasoning` parses to advertised levels plus default, an entry with no capabilities yields fallback levels marked assumed, and malformed capability metadata degrades to fallback rather than raising
- [x] 1.4 Update the `AGENTS.md` module-layout section with `providers.py` and verify the listed modules match the source tree

## 2. Capability discovery and provider headers

- [x] 2.1 Change `client.discover_models()` to return structured per-model entries (id, reasoning levels, provenance, default level) built with the configured provider's parser, keeping `id` the only load-bearing field, and verify mocked-transport tests cover: a go-shaped body yields advertised levels per model, a strata-shaped body yields assumed fallback levels, a body with an unusable entry still fails discovery via `ModelDiscoveryError`, and malformed capabilities degrade per 1.3
- [x] 2.2 Send provider headers on every request: `User-Agent: strata-mcp/<version>` (version from package metadata) for all providers, plus a session header whose value is one UUID generated per server process for providers that require it, and verify mocked-transport tests cover: both headers present on discovery and completion requests, the session value identical across requests within a process, and no session header for strata/ollama

## 3. Reasoning pass-through

- [x] 3.1 Delete the `ReasoningEffort` enum and change `reasoning_effort` to `str | None` through `delegate_task`, `run_delegation`, and `complete()`/`complete_with_tools()`, so the payload carries the caller's string verbatim only when set, and verify tests cover: an arbitrary string (including values outside the old enum, e.g. `xhigh`) reaches the request body unchanged, an omitted value sends no reasoning field, and no boundary validation rejects any string
- [x] 3.2 Verify an engine rejection of a reasoning level (mocked 4xx) still lands in the existing structured-error path as a `WorkerResult` with `error` status and a descriptive message, adding a test if current coverage does not already exercise a 4xx carrying a reasoning field
- [x] 3.3 Update the `list_models` tool to return the trimmed structured entries from 2.1 and the `delegate_task` description to steer callers: choose model and level from `list_models`; a level set without a model applies to first-of-list; and verify an e2e test (mocked client) that the tool response carries entries with levels and provenance and excludes raw provider metadata

## 4. Documentation

- [x] 4.1 Document in the README: the `provider` config key with the go API-key requirement, the breaking `list_models` response shape, the discovery-driven reasoning flow replacing the closed enum (with a migration note for callers prompting `low|high`), the assumed-vs-advertised provenance, silent-clamping and effort-without-model caveats, and verify every documented tool signature and config example matches the code
- [x] 4.2 Update `agents/opencode-AGENTS.md` reasoning guidance (`reasoning_effort=none` wording) to the discovery flow and verify the steer matches the new tool contract

## 5. Integration

- [x] 5.1 Against live Strata (`STRATA_MCP_IT=1`), call `list_models` and verify entries return with assumed fallback levels and provenance, then `delegate_task` with an advertised-or-fallback level and verify a valid status, non-empty output, and no raised exception
- [x] 5.2 With an OpenCode Go key available, run the same pair against the go provider and verify: entries carry advertised per-model levels (e.g. a model advertising `max`), the session and User-Agent headers are accepted (no 4xx attributable to headers), and a level from the chosen model's list completes; skip and record when no key is available
