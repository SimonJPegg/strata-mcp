# Tasks

## 1. Config discovery

- [x] 1.1 Implement XDG config resolution in `_resolve_config_path` (`STRATA_MCP_CONFIG` → `$XDG_CONFIG_HOME/strata-mcp/config.toml` → `~/.config/strata-mcp/config.toml`), and verify unit tests cover env-var precedence, XDG fallback, `~/.config` default when `XDG_CONFIG_HOME` is unset, and a descriptive error when none exists (ref specs/strata-connection)

## 2. Packaging

- [x] 2.1 Verify `uv build` produces a wheel and `pipx install .` installs a working `strata-mcp` console script (run it to confirm it resolves to the entry point); if the `uv_build` backend fails under pipx, switch to `hatchling` and re-verify
- [x] 2.2 Document pipx installation (local path and `git+https://` GitHub URL) and the XDG config location in the README, and verify the documented local install command runs as written

## 3. Integration

- [x] 3.1 Confirm the installed `strata-mcp` starts and responds to an MCP `initialize` request using config discovered from the XDG default location (no `STRATA_MCP_CONFIG` set)
