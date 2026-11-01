# Tasks

## 1. Path fence

- [x] 1.1 Implement a path-fence helper that resolves a requested path to its real absolute form and accepts it only if it falls within one of a set of allowed directories, and verify unit tests cover: path inside, `..` escape, symlink escape, absolute-path-outside, and empty-allowlist (nothing allowed)

## 2. File tools

- [x] 2.1 Implement `read_file` and `write_file` operations that run through the fence helper, returning a failed tool result (not an exception) on a refused path, and verify tests cover a successful read, a successful write, a refused read, and a refused write
- [x] 2.2 Have `write_file` create missing parent directories only inside the fence, and track each written path, and verify tests cover a nested write within the fence and that the written path is recorded

## 3. Tool-use loop

- [x] 3.1 Add a bounded tool-call loop to the client: offer the granted tools, execute returned `tool_calls`, append results as `tool` messages, and repeat until the model stops or `max_tool_rounds` is reached, and verify tests (mocked transport scripting a multi-round tool exchange) cover a completed loop and a loop stopped at the round cap
- [x] 3.2 Map the loop outcome to a `WorkerResult`, reusing `needs_input` when the worker requests ungranted access, and verify tests cover the ok path and the ungranted-access → `needs_input` path

## 4. Contract and delegation

- [x] 4.1 Add `read_dirs_allowed`, `write_dirs_allowed`, and `max_tool_rounds` to `run_delegation` and `delegate_task`, offering file tools only when the matching allowlist is non-empty (no allowlists → Stage 1 behaviour), and verify tests cover tools-offered-when-granted and no-tools-when-omitted
- [x] 4.2 Add `files_written` to the result envelope and populate it from the loop, and verify a test asserts the written files are reported

## 5. Documentation

- [x] 5.1 Document the file tools in the README with an explicit safety section (opt-in fencing, server enforcement, path-escape refusal, reads vs writes), add the fence contract to each new parameter's description, and append a short "file access is opt-in" clause to the server instructions; verify the README and tool/param descriptions match the implemented contract

## 6. Integration

- [x] 6.1 Against live Strata, delegate a task that reads a seeded file and writes a new one inside a granted temp dir, and verify the file appears on disk, `files_written` lists it, and a write attempt outside the fence is refused

## 7. Release hygiene

- [x] 7.1 Remove the stale `strata_mcp-0.1.0-*` assets left on the `0.1.1` GitHub release, and verify only the `0.1.1` artifacts remain attached

## 8. Recommended agent configs

- [x] 8.1 Ship example agent configs under `agents/` (Kiro agent JSON with a delegation-steering prompt; OpenCode `mcp` block; OpenCode AGENTS.md steer snippet) that register strata-mcp and bias the host toward delegating bounded work, and mention them in the README
