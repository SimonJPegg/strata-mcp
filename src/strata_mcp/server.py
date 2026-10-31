"""MCP server exposing the delegate_task tool backed by a local Strata worker."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel

from strata_mcp.client import StrataClient
from strata_mcp.config import StrataConfig, load_config
from strata_mcp.delegation import run_delegation
from strata_mcp.result import WorkerResult

# Env var naming the config file path; keeps connection details out of the
# tool contract so they do not consume the worker's attention.
_CONFIG_ENV = "STRATA_MCP_CONFIG"


class DelegateTaskResult(BaseModel):
    """Tool response: the worker result plus the declared context budget.

    model_context_size is surfaced (advisory) so the caller can budget how
    much context to send on the next delegation.
    """

    result: WorkerResult
    model_context_size: int


def _resolve_config_path() -> Path:
    """Resolve the config file path: env var, then XDG default."""
    config_path = os.environ.get(_CONFIG_ENV)
    if config_path:
        return Path(config_path)

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return base / "strata-mcp" / "config.toml"


def delegate_task_impl(
    config: StrataConfig,
    task: str,
    context: str,
    http_client: httpx.Client | None = None,
) -> DelegateTaskResult:
    """Run one delegation and wrap it with the declared context budget.

    An httpx.Client may be injected for testing; otherwise one is created and
    closed per call.
    """
    owns_client = http_client is None
    # Disable httpx's default 5s timeout: a local model can take far longer to
    # generate, and killing a slow-but-working call is exactly what the design
    # forbids. The only time bound is the optional max_runtime_s backstop.
    client_to_use = http_client or httpx.Client(timeout=None)
    try:
        client = StrataClient(config, client_to_use)
        result = run_delegation(client, config, task, context)
    finally:
        if owns_client:
            client_to_use.close()
    return DelegateTaskResult(result=result, model_context_size=config.model_context_size)


def build_server(config: StrataConfig) -> MCPServer:
    """Build the MCP server with delegate_task bound to the given config."""
    server = MCPServer(name="strata-mcp")

    @server.tool(
        description=(
            "Delegate one scoped task to a local Strata-backed worker and return "
            "a structured result. Send only the task and the minimal context the "
            "worker needs; budget against model_context_size in the response."
        )
    )
    def delegate_task(task: str, context: str = "") -> DelegateTaskResult:
        """Delegate a scoped task to the local worker and return its result."""
        return delegate_task_impl(config, task, context)

    return server


def main() -> None:
    """Entry point: load config and run the server over stdio."""
    config = load_config(_resolve_config_path())
    server = build_server(config)
    server.run()
