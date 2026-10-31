# Design

## Context

See proposal.md — Why. Stage 1 discovers one model via `_first_model_id`
(`data[0].id`) and uses it for every completion. `/v1/models` on Strata returns
richer entries (`id`, `status`, `meta.n_ctx`), but the OpenAI-compatible shape
across backends only reliably carries `id`.

## Goals / Non-Goals

**Goals:**
- Discover the full list of model ids; expose it via a `list_models` tool.
- Let the caller pass an optional `model` to `delegate_task`; default to first.

**Non-Goals:**
- Deriving context size per model from the endpoint (stays config-only).
- Validating a caller-supplied model against the list before use.
- Any change to the worker's text-only behaviour or the result envelope.

## Decisions

### Discovery returns all ids; selection defaults to first
`client.discover_model()` becomes `discover_models() -> list[str]` (all ids in
endpoint order). The delegation path uses the caller's `model` if given, else
`models[0]`. Only `id` is read, keeping the contract portable across Strata and
Ollama.

### Context size stays config-only, and the README says why
The endpoint cannot be trusted for context length across backends: Strata
exposes `meta.n_ctx`, but Ollama's OpenAI endpoint does not and can silently
truncate to an internal default. A single configured `model_context_size` is the
only value that holds for both and reflects what the operator launched. The
README states this rationale and the Ollama caveat explicitly.

### No validation of a caller-supplied model
If the caller passes a model not in the list, the request is sent as-is and any
failure surfaces through the existing structured-error path. Pre-validating
would duplicate the engine's own check and add a round-trip.

### Unified reasoning control via `reasoning_effort`
Both Strata and Ollama honour `reasoning_effort` on the OpenAI-compatible
endpoint (verified live on Strata: `none` → ~3 tokens, `low`/`medium` → ~36,
`high`/unset → ~48; Ollama documents `none` as its off-switch). So a single
`reasoning_effort` parameter — not a backend-specific `chat_template_kwargs`
toggle — gives one unified knob across backends. It is validated to
`none|low|medium|high` and sent only when set; unset leaves the backend default
(thinking on). It is a best-effort hint: models vary (this Qwen collapses
`low`==`medium`), documented like the context/temperature advisories.

## Risks / Trade-offs

- **Chosen model's real window differs from config** → the surfaced
  `model_context_size` may not match the chosen model. Mitigation: documented;
  the value is advisory and the oversized-context backstop still applies.
- **First-of-list default is arbitrary on multi-model backends** → acceptable;
  the caller is expected to use `list_models` then choose deliberately.

## Open Questions

- None.
