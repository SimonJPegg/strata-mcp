"""MCP server exposing the delegate_task tool backed by a local Strata worker."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel

from strata_mcp.client import StrataClient
from strata_mcp.config import StrataConfig, load_config
from strata_mcp.delegation import run_delegation
from strata_mcp.result import ReasoningEffort, WorkerResult

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


@contextmanager
def _strata_client(
    http_client: httpx.Client | None, config: StrataConfig
) -> Iterator[StrataClient]:
    """Yield a StrataClient, closing an internally created httpx client on exit.

    An injected client is left alone: the caller owns its lifecycle and may reuse
    it across delegations. The timeout of a client we create derives from the
    runtime backstop, so a hung request aborts rather than running on after the
    caller has been told error. With no backstop configured there is no request
    timeout: a slow-but-working local generation must not be killed.
    """
    owns_client = http_client is None
    client_to_use = http_client or httpx.Client(timeout=config.max_runtime_s)
    try:
        yield StrataClient(config, client_to_use)
    finally:
        if owns_client:
            client_to_use.close()


def delegate_task_impl(
    config: StrataConfig,
    task: str,
    context: str,
    model: str | None = None,
    reasoning_effort: ReasoningEffort | None = None,
    read_dirs_allowed: list[str] | None = None,
    write_dirs_allowed: list[str] | None = None,
    max_tool_rounds: int = 8,
    allowed_commands: list[str] | None = None,
    max_command_timeout_s: int = 300,
    http_client: httpx.Client | None = None,
) -> DelegateTaskResult:
    """Run one delegation and wrap it with the declared context budget.

    An httpx.Client may be injected for testing; otherwise one is created and
    closed per call. `model` selects the model; when None the first discovered
    model is used. `reasoning_effort` is the optional unified thinking control.
    File access is opt-in: naming `read_dirs_allowed` / `write_dirs_allowed`
    grants fenced read_file / write_file tools. `allowed_commands` grants a
    fenced run_command tool for those exact commands; it needs a write dir for
    the command cwd. With no grants, the worker is text-only.
    """
    with _strata_client(http_client, config) as client:
        result = run_delegation(
            client,
            config,
            task,
            context,
            model=model,
            reasoning_effort=reasoning_effort,
            read_dirs_allowed=read_dirs_allowed,
            write_dirs_allowed=write_dirs_allowed,
            max_tool_rounds=max_tool_rounds,
            allowed_commands=allowed_commands,
            max_command_timeout_s=max_command_timeout_s,
        )
    return DelegateTaskResult(result=result, model_context_size=config.model_context_size)


def list_models_impl(config: StrataConfig, http_client: httpx.Client | None = None) -> list[str]:
    """Return the available model ids from the inference engine."""
    with _strata_client(http_client, config) as client:
        return client.discover_models()


def build_server(config: StrataConfig) -> MCPServer:
    """Build the MCP server with delegate_task bound to the given config."""
    server = MCPServer(
        name="strata-mcp",
        # Loaded into the host's context at connect time, so keep it dense:
        # routing guidance only, details live in the README. Installing the
        # server is itself the preference signal, so state the bias as default.
        instructions=(
            "Delegate by default: the local worker does bounded, checkable "
            "work; you plan, spec, validate. Do it yourself only when the "
            "model would struggle — judgement, long reasoning, uncheckable, "
            "or spec as costly as the work. Not because it is faster. Opt-in: "
            "fenced files, command menu."
        ),
    )

    @server.tool(
        description=(
            "Run one scoped task on the local worker; returns a structured "
            "result. Opt-in: model, reasoning_effort, fenced files "
            "(read/write_dirs_allowed), exact commands (allowed_commands)."
        )
    )
    def delegate_task(
        task: str,
        context: str = "",
        model: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        read_dirs_allowed: list[str] | None = None,
        write_dirs_allowed: list[str] | None = None,
        max_tool_rounds: int = 8,
        allowed_commands: list[str] | None = None,
        max_command_timeout_s: int = 300,
    ) -> DelegateTaskResult:
        """Delegate a scoped task to the local worker and return its result."""
        return delegate_task_impl(
            config,
            task,
            context,
            model=model,
            reasoning_effort=reasoning_effort,
            read_dirs_allowed=read_dirs_allowed,
            write_dirs_allowed=write_dirs_allowed,
            max_tool_rounds=max_tool_rounds,
            allowed_commands=allowed_commands,
            max_command_timeout_s=max_command_timeout_s,
        )

    @server.tool(description="List available model ids to choose from for delegate_task.")
    def list_models() -> list[str]:
        """Return the available model ids."""
        return list_models_impl(config)

    return server


def main() -> None:
    """Entry point: load config and run the server over stdio."""
    config = load_config(_resolve_config_path())
    server = build_server(config)
    server.run()
