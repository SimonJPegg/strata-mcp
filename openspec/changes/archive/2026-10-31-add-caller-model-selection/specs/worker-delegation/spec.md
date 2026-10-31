# Spec Delta

## ADDED Requirements

### Requirement: Caller can list available models

The system SHALL expose a tool that returns the identifiers of the models
available from the inference engine, so the caller can choose one before
delegating.

#### Scenario: Listing returns available model identifiers

- **WHEN** the caller invokes the list-models tool
- **THEN** the system returns the identifiers of the models discovered from the
  inference engine

### Requirement: Caller can choose the model per delegation

The delegation tool SHALL accept an optional model identifier. When provided,
the system SHALL use that model for the completion. When omitted, the system
SHALL use the first available model.

#### Scenario: Caller-chosen model is used

- **WHEN** the caller delegates a task with a model identifier
- **THEN** the completion request uses that model

#### Scenario: Omitted model falls back to the first available

- **WHEN** the caller delegates a task without a model identifier
- **THEN** the completion request uses the first model discovered from the
  inference engine

### Requirement: Caller can control reasoning effort

The delegation tool SHALL accept an optional reasoning-effort level of `none`,
`low`, `medium`, or `high`, and SHALL reject any other value. When provided, the
system SHALL pass it to the completion request; when omitted, the system SHALL
NOT send a reasoning-effort value, leaving the backend's default in effect.

#### Scenario: Reasoning effort is passed through when set

- **WHEN** the caller delegates a task with a reasoning-effort level
- **THEN** the completion request carries that reasoning-effort value

#### Scenario: Omitted reasoning effort leaves the backend default

- **WHEN** the caller delegates a task without a reasoning-effort level
- **THEN** the completion request does not include a reasoning-effort value

#### Scenario: Invalid reasoning effort is rejected

- **WHEN** the caller supplies a reasoning-effort level outside the accepted set
- **THEN** the system rejects it rather than sending it to the engine
