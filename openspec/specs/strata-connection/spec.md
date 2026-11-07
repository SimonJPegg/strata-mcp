# strata-connection Specification

## Purpose
Defines how the server reaches the local Strata inference engine over its
OpenAI-compatible API and how connection failures are surfaced as structured
results rather than crashes.

## Requirements

### Requirement: Reach Strata over the OpenAI-compatible API

The system SHALL communicate with the local inference engine using its
OpenAI-compatible chat-completions API. The system SHALL discover the available
model identifiers from the model-listing endpoint. When the caller does not
choose a model, the system SHALL use the first discovered model.

#### Scenario: Completion request uses the discovered model

- **WHEN** the system sends a completion request and the caller has not chosen a
  model
- **THEN** the request targets the OpenAI-compatible endpoint using the first
  model discovered from the model-listing endpoint

#### Scenario: Multiple available models are all discoverable

- **WHEN** the model-listing endpoint returns more than one model
- **THEN** the system makes the full list of model identifiers available rather
  than only the first

### Requirement: Connection settings come from configuration

The system SHALL read the backend provider, the base URL, an optional
maximum-runtime backstop, and an optional API key from a configuration file
rather than from tool parameters. When no provider is configured, the system
SHALL default to `strata`. The configured provider SHALL select the connection
defaults, the request headers the backend requires, and how the model-listing
endpoint is parsed. When no runtime backstop is configured, the system SHALL
NOT impose a time limit on a delegation.

#### Scenario: Base URL is read from config

- **WHEN** the server starts
- **THEN** it reads the base URL from the configuration file and uses it for
  delegation requests

#### Scenario: No backstop means no enforced time limit

- **WHEN** no maximum-runtime backstop is configured
- **THEN** a delegation is not terminated on elapsed time alone

#### Scenario: A configured backstop bounds a hung request

- **WHEN** a maximum-runtime backstop is configured and a single request to the
  backend stops making progress
- **THEN** that request is bounded by the backstop and aborted rather than left
  running after the caller is returned an `error`, surfaced as a structured
  error result

#### Scenario: API key sent when configured

- **WHEN** an API key is configured and the server sends a request to the backend
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

### Requirement: Config file is discovered from a default location

When the `STRATA_MCP_CONFIG` environment variable is not set, the system SHALL
look for its configuration at the XDG location `config.toml` under a
`strata-mcp` directory in `XDG_CONFIG_HOME` (defaulting to `~/.config`). When
the variable is set, it SHALL take precedence over the default location.

#### Scenario: Environment variable takes precedence

- **WHEN** `STRATA_MCP_CONFIG` is set to a path
- **THEN** the system loads configuration from that path, ignoring the default
  location

#### Scenario: Falls back to the XDG default

- **WHEN** `STRATA_MCP_CONFIG` is not set
- **THEN** the system loads configuration from `strata-mcp/config.toml` under
  `XDG_CONFIG_HOME`, or under `~/.config` when `XDG_CONFIG_HOME` is not set

#### Scenario: Missing config at the resolved location is reported

- **WHEN** neither the environment variable nor the default location points to
  an existing file
- **THEN** the system fails with a descriptive error naming the path it tried
