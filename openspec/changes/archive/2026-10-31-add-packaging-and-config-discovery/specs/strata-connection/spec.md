# Spec Delta

## ADDED Requirements

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
