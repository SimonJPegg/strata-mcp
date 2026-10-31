# Tasks

## 1. Discovery returns all models

- [x] 1.1 Replace `discover_model()` with `discover_models() -> list[str]` returning all ids from `/v1/models` in order (empty list → `ModelDiscoveryError`), and update unit tests to cover multiple models, a single model, and the empty-list error
- [x] 1.2 Update the completion path so `complete()` receives an explicit model id chosen by the caller, and verify the request payload carries the chosen model (mocked transport)

## 2. Model selection in delegation and tools

- [x] 2.1 Thread an optional `model` through `run_delegation` (caller value → else first discovered), and verify tests cover the chosen-model and default-first paths
- [x] 2.2 Add an optional `model` parameter to the `delegate_task` tool, and verify an e2e test (mocked client) that a supplied model is used and an omitted one defaults to first
- [x] 2.3 Add a `list_models` MCP tool returning the discovered model ids, and verify a test asserts the returned ids against a mocked `/v1/models`
- [x] 2.4 Add an optional `reasoning_effort` (`none|low|medium|high`) validated at the param boundary, threaded through `run_delegation` and `complete()` so the payload carries it only when set, and verify tests cover: value sent when set, absent when omitted, and an invalid value rejected
- [x] 2.5 Expose `reasoning_effort` on the `delegate_task` tool, and verify an e2e test (mocked client) that a set value reaches the request and an omitted one does not

## 3. Documentation

- [x] 3.1 Document `list_models`, the optional `model` and `reasoning_effort` arguments (unified `none|low|medium|high` thinking control honoured by Strata and Ollama; best-effort, model-dependent), and — explicitly — that `model_context_size` is a single configured advisory value (with the rationale that `/v1/models` does not reliably expose context length across backends; Strata reports it, Ollama does not and may silently truncate), and verify the README reflects the current tool signatures

## 4. Integration

- [x] 4.1 Against live Strata, call `list_models` and a `delegate_task` with an explicit model id, and verify both succeed deterministically (valid status, non-empty output, model id echoed in the list)
