# Tasks

> Notes (grounded against Strata's AI_SETUP.md): the server is managed with
> `uv` (pinned deps + committed lockfile); config is TOML parsed with the stdlib
> `tomllib`; Strata's default address is `http://127.0.0.1:8080/v1`; the loaded
> model id and (where available) its context length are discoverable via
> `GET /v1/models`; localhost needs no API key but one is supported for
> non-localhost use.

## 1. Project scaffold

- [x] 1.1 Initialise the `strata-mcp` package with `uv` (`uv init`, `pyproject.toml` targeting the latest AWS-supported Python, src layout) and add pinned deps (`uv add` for the MCP Python SDK and an OpenAI-compatible HTTP client), then verify `uv run python -c "import strata_mcp"` succeeds and `uv.lock` is committed
- [x] 1.2 Add ruff (with C901) and pytest via `uv add --dev`, and verify `uv run ruff check` and `uv run pytest` both run clean on the empty scaffold

## 2. Config loading

- [x] 2.1 Define a pydantic config model holding `base_url` (default `http://127.0.0.1:8080/v1`), optional `max_runtime_s` (absent = no limit), `model_context_size`, and optional `api_key`, and verify a unit test loads a valid TOML file into the model
- [x] 2.2 Implement TOML loading via `tomllib` with explicit errors for a missing file and for missing/invalid required fields, and verify unit tests cover each sad path (file absent, malformed TOML, missing `base_url`, non-positive `model_context_size`)
- [x] 2.3 Add an optional `temperature` config field (default 0.0, range 0–2) applied to every completion request, and verify tests cover the default, a configured value reaching the request payload, and out-of-range rejection (ref specs/strata-connection)

## 3. Strata client

- [x] 3.1 Implement an OpenAI-compatible chat-completions client that targets `base_url`, discovers the loaded model id via `GET /v1/models` and uses it in requests, and attaches the configured API key when present, and verify unit tests assert the model-discovery call and the request shape against a mocked HTTP transport (both with and without a key)
- [x] 3.2 Parse the completion response into output text plus token usage when present, and verify a unit test covers a response with usage and one without
- [x] 3.3 Map transport and response failures (unreachable host, empty/malformed completion, failed model discovery) to typed error outcomes rather than raising, and verify unit tests cover each case (ref specs/strata-connection)

## 4. Worker result envelope

- [x] 4.1 Define the `WorkerResult` pydantic model (`status` ∈ {ok, needs_input, rejected, error}, `output`, `elapsed_s`, optional `token_usage`, optional `error`) and verify a unit test rejects an invalid status and requires `error` when status is `error`
- [x] 4.2 Implement mapping from the worker's self-reported ending (completed/blocked/unclear/infeasible) to the envelope status, and verify a unit test covers each mapping including the transport-failure → `error` path (ref specs/worker-delegation)

## 5. Worker system prompt

- [x] 5.1 Author the worker system prompt covering the three jobs — frame the worker, bound it to the single task with no filesystem/shell access, and instruct it to stop and self-report when a task is ambiguous, blocked, or infeasible — and verify a test asserts the prompt text contains each of the three directives
- [x] 5.2 Document the prompt's intended behaviour and the self-report-plus-caller-validation model in the package README, and verify the documented behaviour matches the prompt constants

## 6. delegate_task tool

- [x] 6.1 Register the `delegate_task(task, context)` MCP tool that composes config + system prompt + inputs, calls the Strata client once (blocking), times the call, and returns a `WorkerResult`, and verify an end-to-end test with a mocked client returns an `ok` envelope with populated `elapsed_s`
- [x] 6.2 Surface the configured `model_context_size` to the caller in the tool response/metadata (advisory, not enforced), and verify a test asserts the declared size is reported (ref specs/strata-connection)
- [x] 6.3 Return a structured `error` result when `context` plus `task` exceed the declared size without calling Strata, and verify a test covers the oversized-context backstop
- [x] 6.4 Honour the optional `max_runtime_s` backstop (terminate and return `error`), confirm no limit is applied when it is absent, and verify tests cover both the backstop-hit and no-limit paths
- [x] 6.5 Emit heartbeat log lines (elapsed every N seconds) via loguru while a call is in flight, and verify a test observes at least one heartbeat for a call exceeding the interval

## 7. Integration

- [x] 7.1 Run the MCP server (`uv run`) against a running local Strata instance (`strata launch ... --no-tui`, verified via `GET /health` and `GET /v1/models`), delegate a small real task end to end, and verify the returned `WorkerResult` is `ok` with non-empty output and a reported context size
- [x] 7.2 Document the server setup in the README (`uv` install, config file example with the `http://127.0.0.1:8080/v1` default, how to point an MCP host at the server, the `strata launch` prerequisite) and verify the documented startup command runs as written
