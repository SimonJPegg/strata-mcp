# Proposal

## Why

The server speaks OpenAI-compatible chat-completions and assumes a local Strata.
Pointing it at another backend (Ollama, or the OpenCode Go gateway) breaks on
thinking control: the closed `reasoning_effort` enum (`none|low|medium|high`)
does not match what those backends' models accept. Go advertises per-model
ladders — `hy4` takes only `none|high`, `kimi-k3` only `max`, `qwen3.8-max`
`low|medium|xhigh` — so no static mapping, in code or config, can keep up with
vocabularies that vary per model and change upstream. The vocabulary must come
from discovery, and the choice must belong to the caller, which holds the task
judgement.

## What Changes

- Add a `provider` config key (`strata` | `ollama` | `opencode-go`, defaulting to
  `strata`). The provider selects connection defaults (base URL expectation, API
  key), provider-required request headers (Go's stable `x-opencode-session` and
  an identifying `User-Agent`), and how reasoning capabilities are parsed from
  the model-listing endpoint. Config stays thinking-free: no TOML key about
  reasoning levels exists.
- **BREAKING**: `list_models` returns trimmed per-model entries — id, reasoning
  levels with provenance (`advertised` by the endpoint vs `assumed` from the
  provider's fallback), and the advertised default level — instead of bare
  identifier strings. Raw provider metadata (costs, modalities) never surfaces.
- **BREAKING**: `delegate_task`'s `reasoning_effort` changes from a closed enum
  to a free string taken by the caller from the chosen model's advertised
  levels. It passes through to the completion request unvalidated at the tool
  boundary, matching the existing no-validation rule for `model`; an unsupported
  value is rejected by the engine and surfaces as a structured `error` result
  the caller can retry from. Omitted behaviour is unchanged: no field is sent
  and the backend default applies.
- Backends that do not advertise reasoning capabilities (Strata, Ollama) get
  provider-declared fallback levels (`none|low|medium|high`, verified live in
  the add-caller-model-selection change), reported with `assumed` provenance so
  callers know what they can trust.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `strata-connection`: configuration names a provider that selects connection
  defaults, required headers, and capability parsing from the model-listing
  endpoint; reasoning capabilities are discovered per model, with
  provider-declared fallback levels where a backend advertises none.
- `worker-delegation`: the list-models tool surfaces trimmed per-model entries
  with reasoning levels, provenance, and default; the reasoning-effort control
  becomes a caller-chosen pass-through string instead of a closed enum, and the
  boundary-validation scenario inverts to engine rejection surfaced as a
  structured error.

## Impact

- `config.py`: `provider` field with validation; new explicit error for an
  unknown provider.
- New `providers.py` module: one profile per provider — connection defaults,
  headers, fallback reasoning levels, and `/models` capability parsing, as pure
  functions plus a pydantic profile model.
- `client.py`: `discover_models()` returns structured entries; completion and
  discovery requests carry the provider's headers.
- `result.py`: `ReasoningEffort` enum deleted.
- `server.py`: `list_models` tool response shape; `reasoning_effort: str | None`
  on `delegate_task`; per-process session id generated at `main()`; tool
  descriptions updated to point callers at discovery.
- `delegation.py`: threads the reasoning string through without enum conversion.
- README and `agents/opencode-AGENTS.md`: provider config section, the
  discovery-driven reasoning flow, and both breaking tool-contract changes.
- Tests: reasoning and `list_models` tests rewritten; existing
  `StrataConfig(...)` call sites keep working via the provider default.
- Unchanged: the result envelope, the worker prompt, file/command fencing,
  failure-as-data, and the no-hard-timeout invariant.
