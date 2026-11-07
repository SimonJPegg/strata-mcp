# Spec Delta

## MODIFIED Requirements

### Requirement: Caller can list available models

The system SHALL expose a tool that returns the models available from the
inference engine, so the caller can choose a model and a reasoning level before
delegating. Each model SHALL be returned as one entry carrying its identifier,
its reasoning levels with provenance (advertised by the backend, or assumed
from the provider's fallback), and the advertised default reasoning level when
the backend declares one. The system SHALL NOT surface provider metadata
beyond these fields.

#### Scenario: Listing returns available model identifiers

- **WHEN** the caller invokes the list-models tool
- **THEN** the system returns one entry per model discovered from the inference
  engine, each carrying that model's identifier

#### Scenario: Listing returns per-model reasoning information

- **WHEN** the caller invokes the list-models tool
- **THEN** each entry also carries the model's reasoning levels with their
  provenance, and the default level when one is advertised

#### Scenario: Entries stay trimmed

- **WHEN** the backend's model listing carries metadata beyond identity and
  reasoning capabilities
- **THEN** the returned entries exclude that metadata

## REMOVED Requirements

### Requirement: Caller can control reasoning effort

**Reason**: The closed `none|low|medium|high` enum with tool-boundary
validation cannot express per-model reasoning vocabularies (a backend model may
advertise only `max`, or `low|medium|xhigh`), so the accepted set is no longer
something the server can know statically.

**Migration**: Callers read the chosen model's reasoning levels from the
list-models tool and pass one as the free-string `reasoning_effort` on
`delegate_task`; the value is passed through unchanged and an engine rejection
surfaces as a structured `error` result to retry from. See the ADDED
requirement "Caller chooses reasoning effort from discovered levels". Omitted
behaviour is unchanged: no field is sent and the backend default applies.

## ADDED Requirements

### Requirement: Caller chooses reasoning effort from discovered levels

The delegation tool SHALL accept an optional reasoning-effort level as a free
string chosen by the caller from the levels reported for the model the
delegation will use. The system SHALL pass the value to the completion request
unchanged and SHALL NOT validate it at the tool boundary; the engine's own
acceptance is the check. When omitted, the system SHALL NOT send a
reasoning-effort value, leaving the backend's default in effect.

#### Scenario: Reasoning effort is passed through when set

- **WHEN** the caller delegates a task with a reasoning-effort level
- **THEN** the completion request carries that value unchanged

#### Scenario: Omitted reasoning effort leaves the backend default

- **WHEN** the caller delegates a task without a reasoning-effort level
- **THEN** the completion request does not include a reasoning-effort value

#### Scenario: Engine-rejected level is a structured error

- **WHEN** the caller supplies a reasoning-effort level the backend rejects for
  the chosen model
- **THEN** the system returns a result with an `error` status and a descriptive
  message rather than raising, so the caller can retry with a different level
