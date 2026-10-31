# Proposal

## Why

Running the server from a working-directory checkout with `uv run` is fine for
development but awkward for actual use: it depends on the current directory and
requires `STRATA_MCP_CONFIG` to be set by hand. Making `strata-mcp` a
pipx-installable tool with a conventional config location lets a user install it
once and run it from anywhere.

## What Changes

- Discover config from the XDG location `~/.config/strata-mcp/config.toml`
  (honouring `XDG_CONFIG_HOME`) when `STRATA_MCP_CONFIG` is not set, so a
  hand-run `strata-mcp` finds its config without an environment variable.
- Make the package pipx-installable, including from a GitHub URL, with a build
  backend that pip/pipx can drive.
- Document pipx installation (local path and GitHub) and the XDG config location
  in the README.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `strata-connection`: config discovery gains an XDG default location in
  addition to the `STRATA_MCP_CONFIG` environment variable.

## Impact

- **config resolution**: `STRATA_MCP_CONFIG` takes precedence; otherwise the XDG
  path is used; otherwise a descriptive error.
- **packaging**: `pyproject.toml` build backend confirmed or switched for
  pip/pipx compatibility; no change to runtime behaviour.
- **docs**: README install section updated.
- **No change** to the delegation tool contract or the worker behaviour.
