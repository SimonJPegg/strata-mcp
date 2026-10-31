# Design

## Context

See proposal.md — Why. The server currently resolves config as
`STRATA_MCP_CONFIG` or the literal `strata-mcp.toml` in the current directory.
The package is built with the `uv_build` backend and run via `uv run`.

## Goals / Non-Goals

**Goals:**
- Config discovery falls back to an XDG default when the env var is unset.
- The package installs via pipx, including from a GitHub URL.

**Non-Goals:**
- Changing the delegation tool contract, worker behaviour, or result envelope.
- Publishing to PyPI.

## Decisions

### Config resolution order
`STRATA_MCP_CONFIG` (if set) → `$XDG_CONFIG_HOME/strata-mcp/config.toml` →
`~/.config/strata-mcp/config.toml`. The first existing candidate is loaded; if
none resolves to a file, the existing `ConfigFileNotFoundError` reports the
path tried. `XDG_CONFIG_HOME` is honoured per the XDG Base Directory spec.

### Build backend for pipx
pipx builds the project in an isolated environment via its PEP 517 backend. The
current `uv_build` backend is verified to build under pip/pipx; if it does not,
switch to `hatchling`, which pip and pipx drive without extra configuration.
The decision is made by testing an actual `pipx install .`.

### Installation from GitHub
Once the project is pushed to a GitHub remote,
`pipx install "git+https://github.com/simonjpegg/strata-mcp.git"` installs the
console script. This requires the repo to be committed and pushed first; it is
documented but not performed as part of this change.

## Risks / Trade-offs

- **uv_build may not be pipx-friendly** → verify with a real `pipx install .`;
  fall back to hatchling if needed.
- **XDG path on non-Linux** → `~/.config` is the documented default; macOS users
  who prefer another location can still use `STRATA_MCP_CONFIG`.

## Open Questions

- None.
