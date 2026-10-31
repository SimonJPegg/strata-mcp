# Proposal

## Why

An MCP host loads the server's instructions and every tool description into its
context at connect time, once per session. The server currently advertises no
top-level guidance on *when* to use it, and its tool descriptions are wordier
than they need to be. For a server whose purpose is to reduce the cost of
running the orchestrator, verbose wire text is self-defeating: it spends the
caller's context. The fix is to add a dense, routing-focused server description
and trim the tool descriptions so the net wire cost does not grow.

## What Changes

- Add a one-line server-level description/instructions stating when to reach for
  the server: delegate bounded, well-specified subtasks; the caller plans and
  validates; not for judgement-heavy or ambiguous work.
- Tighten the existing `delegate_task` and `list_models` tool descriptions to be
  dense and routing-focused, removing explanatory prose that belongs in the
  README rather than on the wire.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `worker-delegation`: the server advertises concise usage guidance describing
  when to delegate.

## Impact

- `server.py`: `MCPServer` gains an `instructions` value; `delegate_task` and
  `list_models` descriptions shortened.
- No change to tool signatures, parameters, behaviour, or the result envelope.
- README unaffected (it already documents usage in full).
