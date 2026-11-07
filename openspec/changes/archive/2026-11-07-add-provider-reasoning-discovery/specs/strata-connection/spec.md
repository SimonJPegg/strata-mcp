# Spec Delta

## MODIFIED Requirements

### Requirement: Connection settings come from configuration

The system SHALL read the backend provider, the base URL, an optional maximum-runtime
backstop, and an optional API key from a configuration file rather than from
tool parameters. When no provider is configured, the system SHALL default to
`strata`. The configured provider SHALL select the connection defaults, the
request headers the backend requires, and how the model-listing endpoint is
parsed. When no runtime backstop is configured, the system SHALL NOT impose a
time limit on a delegation.

#### Scenario: Base URL is read from config

- **WHEN** the server starts
- **THEN** it reads the Strata base URL from the configuration file and uses it
  for delegation requests

#### Scenario: No backstop means no enforced time limit

- **WHEN** no maximum-runtime backstop is configured
- **THEN** a delegation is not terminated on elapsed time alone

#### Scenario: A configured backstop bounds a hung request

- **WHEN** a maximum-runtime backstop is configured and a single request to
  Strata stops making progress
- **THEN** that request is bounded by the backstop and aborted rather than left
  running after the caller is returned an `error`, surfaced as a structured
  error result

#### Scenario: API key sent when configured

- **WHEN** an API key is configured and the server sends a request to Strata
- **THEN** the request includes the configured credential; when no key is
  configured, the request is sent without one

#### Scenario: Config without a provider resolves to the default

- **WHEN** a configuration file names no provider
- **THEN** the system behaves as if `strata` were configured and existing
  configuration files keep working unchanged

#### Scenario: Unknown provider is rejected at load

- **WHEN** a configuration file names a provider the system does not know
- **THEN** configuration loading fails with a descriptive error naming the
  accepted providers

## ADDED Requirements

### Requirement: Reasoning capabilities are discovered per model

When the model-listing endpoint advertises them, the system SHALL parse each
model's reasoning levels and default level and make them available alongside
the model identifier, marked as advertised. For a model whose backend advertises
no reasoning capabilities, the system SHALL supply the provider-declared
fallback levels, marked as assumed. Unparseable capability metadata SHALL
degrade to the fallback rather than fail discovery.

#### Scenario: Advertising backend reports levels with provenance

- **WHEN** the model-listing endpoint advertises reasoning levels for a model
- **THEN** the system surfaces those levels for that model, with provenance
  marked as advertised, plus the default level when one is declared

#### Scenario: Silent backend falls back to provider levels

- **WHEN** the model-listing endpoint advertises no reasoning capabilities for
  a model
- **THEN** the system surfaces the provider-declared fallback levels for that
  model with provenance marked as assumed

#### Scenario: Malformed capability metadata degrades rather than fails

- **WHEN** a model entry carries capability metadata that cannot be parsed
- **THEN** discovery still returns that model, with fallback levels marked as
  assumed

### Requirement: Provider-required request headers

The system SHALL send a User-Agent identifying the server on every request to
the backend. When the configured provider requires a session identifier
header, the system SHALL send one whose value is stable across requests for the
lifetime of a single server process.

#### Scenario: Every request identifies the server

- **WHEN** the server sends any request to the backend
- **THEN** the request carries a User-Agent identifying the server

#### Scenario: Session header is stable within a server process

- **WHEN** the configured provider requires a session header and the server
  makes multiple requests to the backend
- **THEN** each request carries the same session value for that server process
