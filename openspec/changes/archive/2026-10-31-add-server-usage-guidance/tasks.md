# Tasks

## 1. Server guidance and dense descriptions

- [x] 1.1 Add concise `instructions` to `MCPServer` (when to delegate: bounded, well-specified subtasks; caller plans and validates; not judgement-heavy/ambiguous work), and verify a test asserts the server exposes non-empty instructions
- [x] 1.2 Tighten the `delegate_task` and `list_models` tool descriptions to dense, routing-focused one-liners, and verify a test asserts each description is present and under a reasonable length cap

## 2. Verification

- [x] 2.1 Confirm `ruff check` and `pytest` pass, and that the registered tools still expose `delegate_task` and `list_models` with their descriptions intact
