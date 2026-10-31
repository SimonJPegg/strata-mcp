# Proposal

## Why

The server currently discovers a single model from `/v1/models` and uses it for
every delegation. When the backend serves more than one model (e.g. Ollama, or a
future multi-model Strata), the caller — which holds the judgement about the
task — has no way to see what is available or to pick the model best suited to
the work. Letting the caller choose per task puts the decision where the
judgement lives.

## What Changes

- Add a `list_models` MCP tool that returns the available model identifiers
  discovered from `/v1/models`, so the caller can see the roster before choosing.
- Add an optional `model` parameter to `delegate_task`; when supplied, the
  worker uses that model. When omitted, the server defaults to the first model
  discovered from `/v1/models` (current behaviour).
- Add an optional `reasoning_effort` parameter to `delegate_task`
  (`none | low | medium | high`), passed through to the completion request only
  when set. This is a unified thinking control: both Strata and Ollama honour
  `reasoning_effort` on the OpenAI-compatible endpoint, with `none` turning the
  model's reasoning phase off. When omitted, the backend's own default applies
  (thinking on), preserving current behaviour.
- Keep `model_context_size` as a single configured, advisory value — the server
  does NOT derive context size per model from the endpoint. Document explicitly
  in the README why: the OpenAI-compatible `/v1/models` does not reliably expose
  context length across backends (Strata reports it, Ollama does not and may
  silently truncate), so the operator declares it once to match what the server
  was launched with.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `strata-connection`: model discovery surfaces the full list of available
  models rather than only the first.
- `worker-delegation`: the delegation tool accepts an optional caller-chosen
  model, and a new tool lists the available models.

## Impact

- `client.py`: discovery returns all model ids, not just the first.
- `server.py`: new `list_models` tool; `delegate_task` gains an optional `model`
  argument threaded through to the completion request.
- `delegation.py` / `client.py`: the chosen (or default-first) model id is passed
  to the completion call.
- README: documents `list_models`, the optional `model` argument, and the
  config-only context-size rationale with the Ollama caveat.
- No change to the result envelope, the worker prompt, or the text-only
  (Stage 1) nature of the worker.
