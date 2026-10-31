# Spec Delta

## Purpose

Defines how the server reaches the local Strata inference engine over its
OpenAI-compatible API and how connection failures are surfaced as structured
results rather than crashes.

## ADDED Requirements

### Requirement: Reach Strata over the OpenAI-compatible API

The system SHALL communicate with the local Strata inference engine using its
OpenAI-compatible chat-completions API. The system SHALL discover the loaded
model's identifier from Strata's model-listing endpoint rather than accepting a
caller-supplied model, because Strata serves one loaded model and does not
hot-swap.

#### Scenario: Completion request uses the discovered model

- **WHEN** the system sends a completion request to Strata
- **THEN** the request targets the OpenAI-compatible endpoint using the model
  identifier discovered from Strata, without the caller choosing a model

### Requirement: Connection settings come from configuration

The system SHALL read the Strata base URL, an optional maximum-runtime
backstop, and an optional API key from a configuration file rather than from
tool parameters. When no runtime backstop is configured, the system SHALL NOT
impose a time limit on a delegation.

#### Scenario: Base URL is read from config

- **WHEN** the server starts
- **THEN** it reads the Strata base URL from the configuration file and uses it
  for delegation requests

#### Scenario: No backstop means no enforced time limit

- **WHEN** no maximum-runtime backstop is configured
- **THEN** a delegation is not terminated on elapsed time alone

#### Scenario: API key sent when configured

- **WHEN** an API key is configured and the server sends a request to Strata
- **THEN** the request includes the configured credential; when no key is
  configured, the request is sent without one

### Requirement: Declare and surface the model context size

Configuration SHALL declare the context size of the model Strata has loaded, and
the system SHALL make that size discoverable to the caller so it can budget how
much `context` to send. The declared size is advisory: the system SHALL NOT
enforce it beyond the existing oversized-context error backstop.

#### Scenario: Context size is read from config

- **WHEN** the server starts
- **THEN** it reads the declared model context size from the configuration file

#### Scenario: Caller can discover the context size

- **WHEN** the caller invokes the delegation tool
- **THEN** the system reports the declared model context size to the caller

### Requirement: Generation temperature is configurable

Configuration SHALL provide an optional generation temperature applied to every
completion request, defaulting to a value that favours deterministic, literal
output for a bounded worker. The system SHALL reject a temperature outside the
accepted range.

#### Scenario: Default temperature favours determinism

- **WHEN** no temperature is configured
- **THEN** the system applies a default temperature of zero to completion
  requests

#### Scenario: Configured temperature is applied

- **WHEN** a temperature within the accepted range is configured
- **THEN** the system includes that temperature in completion requests

#### Scenario: Out-of-range temperature is rejected

- **WHEN** a configured temperature is below zero or above the accepted maximum
- **THEN** configuration loading fails with a descriptive error

### Requirement: Connection and response failures are structured

The system SHALL surface Strata being unreachable, a request exceeding the
configured runtime backstop, and an empty or malformed response as a result
envelope with an `error` status and a descriptive message, not as an unhandled
exception.

#### Scenario: Strata unreachable

- **WHEN** the server cannot connect to Strata at the configured base URL
- **THEN** the system returns an `error` status with a message indicating
  Strata could not be reached

#### Scenario: Empty or malformed response

- **WHEN** Strata returns an empty or malformed completion
- **THEN** the system returns an `error` status describing the problem
