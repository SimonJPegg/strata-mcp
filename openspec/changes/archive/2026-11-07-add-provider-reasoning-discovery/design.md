# Design

## Context

See proposal.md — Why. Current state that shapes the approach:

- Config is one flat model with no provider notion (`config.py`); connection
  settings are validated once at startup.
- Thinking is a closed enum (`result.py`) passed verbatim to the wire at a
  single choke point, `_completion_payload` in `client.py`. Nothing translates.
- Discovery reads only `id` from `/v1/models` entries; the archived
  add-caller-model-selection design established that only `id` is portable
  across backends, and that caller-supplied values are not pre-validated —
  the engine's own check plus the structured-error path is the interface.
- Live evidence from the OpenCode Go models endpoint (fetched 2026-11-07):
  reasoning vocabularies are per-model, not per-provider — `hy4` advertises
  `["none","high"]`, `kimi-k3` only `["max"]`, `qwen3.8-max`
  `["low","medium","xhigh"]` with a toggle and budget, `crouton-alpha-free`
  the full `["minimal","low","medium","high","xhigh","max"]`. Entries also
  carry `limit.context`, cost tables, modality lists, and a
  `reasoning_field` compatibility hint. Go's terms ask clients for a stable
  `x-opencode-session` header and an identifying User-Agent.
- The archived decision "unified reasoning control via `reasoning_effort`, not
  a backend-specific toggle" is superseded by this change: the unified knob was
  a closed vocabulary; the replacement keeps one knob but makes its accepted
  values discovered data.

## Goals / Non-Goals

**Goals:**
- Provider-aware connection: one config key selects defaults, headers, and
  `/models` capability parsing.
- Reasoning vocabulary arrives from discovery, per model, with provenance.
- Caller owns level choice; server passes it through untranslated.
- Existing config files and behaviour keep working via the `strata` default.

**Non-Goals:**
- Per-model context size from discovery. Go advertises `limit.context` and
  Strata `meta.n_ctx`, but adopting either reopens the archived "context size
  stays config-only" decision; it deserves its own change.
- Echoing the applied level back in the result envelope (`reasoning_applied`).
  The envelope stays frozen.
- Any config-level thinking keys: no maps, no defaults, no overrides. Thinking
  configuration does not exist in TOML after this change.
- Validating a caller-supplied level against discovered capabilities at the
  tool boundary — that would duplicate the engine and go stale, against the
  established no-validation precedent.
- Native provider routes (Go's `responses` / `messages` / `generate-content`
  endpoints). Chat-completions only; Go's console translates every text model
  onto it.
- Multiple provider profiles in one config file. One server process speaks to
  one backend.

## Decisions

### Provider profiles live in code, not config
A new `providers.py` holds one profile per provider: connection defaults,
required headers, fallback reasoning levels, and the `/models` capability
parser — pydantic model plus pure parsing functions, per house style.
Rationale: the vocabulary is per-model and changes upstream; any static table
(compiled or configured) rots into per-model special cases. Discovery is the
only durable source, and what stays in code is the slow-moving part: where to
look in a response body and what to send alongside it. Alternative considered:
a config-declared thinking map per provider — rejected; it cannot express
per-model ladders and pushes endpoint research onto every operator.

### Intent resolution moves to the caller
`list_models` becomes the menu (per-model entries: id, levels, provenance,
default); `delegate_task.reasoning_effort` becomes a free string taken from
that menu and passed through unchanged. This extends the model-selection
pattern already specified: discover, caller chooses, no boundary validation,
engine rejection surfaces as a structured error the caller retries from.
Alternative considered: a canonical intent enum translated per provider —
rejected; translation cannot be right per-model (`kimi-k3` has one level), and
a closed enum is exactly what breaks when a backend adds a tier.

### Enum deleted outright, no aliases
`ReasoningEffort` is removed rather than kept as accepted aliases. The repo is
early, the README is the only contract document, and aliases would keep two
vocabularies alive in host prompts indefinitely. Breaking changes are declared
in the proposal.

### Fallback levels with provenance for silent backends
Strata and Ollama advertise nothing usable, so their profiles declare
`none|low|medium|high` — the set verified live in the archived change. Entries
mark levels `advertised` vs `assumed` so the caller knows what it can trust;
assumed levels that a model rejects still land in the existing error path.

### Malformed capability metadata degrades, not fails
Only `id` remains load-bearing in discovery. A model entry whose
`capabilities` block is present but unparseable yields fallback levels with
`assumed` provenance; discovery still returns the model. Failing discovery on
advisory metadata would violate the repo's error-as-data grain for a field the
server treats as a hint.

### Session id per server process; User-Agent always
A stdio server instance is one host conversation, so a UUID generated once at
startup satisfies Go's "stable session ID per conversation" for routing and
prompt-cache purposes. `User-Agent: strata-mcp/<version>` goes on every
provider's requests, not only Go's — it is cheap and identifies the client
honestly. Alternative considered: config-pinned session id — rejected for MVP;
operator chore with speculative cache benefit.

### Entries stay trimmed
Go's raw model blob is roughly 2KB per model across ~30 models (costs,
multipliers, modalities, SDK hints). Surfacing it would tax the orchestrator's
context for fields it must not act on, against the project's stated attention
philosophy (dense instructions, plumbing in config). The tool returns id,
levels, provenance, default — nothing else.

### Go requires an API key at load time
`provider = "opencode-go"` with no `api_key` fails configuration loading with a
new explicit exception, rather than 401-ing on every delegation. Config is
validated once at startup; a missing mandatory credential is a config error,
and house style prefers explicit named exceptions. Strata and Ollama keep the
key optional (localhost serves without one).

### Wire field stays `reasoning_effort`
All three providers are addressed over chat-completions, where the field name
is the same; Go's console translates natively-Anthropic or responses-route
models. No per-route dialect logic in this change.

## Risks / Trade-offs

- **Silent clamping upstream** (Go may accept `max` but run `high`, per
  oh-my-pi #9349) → no error to retry from; the worker just thinks less.
  Mitigation: documented as best-effort, same class as today's level collapse;
  the deferred `reasoning_applied` echo is the future fix.
- **`list_models` response shape breaks hosts** that parse `list[str]` →
  Mitigation: declared BREAKING in the proposal, README migration note; the old
  shape cannot carry the levels this change exists to surface.
- **Effort-without-model is quietly incoherent**: the first-of-list default may
  not advertise the level sent → Mitigation: tool description steers callers to
  set `model` whenever they set a level; engine rejection remains a structured
  error. Not enforced — same latitude the `model` param already has.
- **Go's response schema drifts** (capabilities shape is theirs to change) →
  Mitigation: parsing is defensive and degrades to fallback provenance; a
  gated live integration test catches drift early.
- **Fallback levels wrong for an exotic Strata/Ollama model** → Mitigation:
  `assumed` provenance tells the caller the levels are a hint; rejection is an
  error envelope, not a crash.

## Migration Plan

Single release, no data migration. Existing config files load unchanged
(`provider` defaults to `strata`; Strata keeps an optional key). Callers update
prompts/steers from the closed enum to the discovery flow: `list_models` first,
then pick a level from the chosen model's entry. Rollback is reverting the
change; specs and code move together at archive time.

## Open Questions

- None. Session-id lifecycle, validation stance, fallback provenance, and the
  enum break were all settled with the operator during exploration.
