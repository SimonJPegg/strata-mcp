# Spec Delta

## ADDED Requirements

### Requirement: File tools are opt-in per delegation

The delegation tool SHALL accept `read_dirs_allowed` and `write_dirs_allowed`
directory lists. The system SHALL offer `read_file` only when
`read_dirs_allowed` is non-empty, and `write_file` only when
`write_dirs_allowed` is non-empty. When both are empty or omitted, the worker
SHALL be offered no file tools and behave as a text-only worker.

#### Scenario: No allowlists means no file tools

- **WHEN** a task is delegated with neither allowlist set
- **THEN** the worker is given no file tools and produces a text-only result

#### Scenario: Write access is offered only when granted

- **WHEN** a task is delegated with a non-empty `write_dirs_allowed`
- **THEN** the worker is offered a `write_file` tool scoped to those directories

### Requirement: The server enforces the directory fence

The system SHALL validate every `read_file` and `write_file` path against the
caller's allowlists, resolving the real path first. A path that falls outside
every allowed directory, including via `..`, a symlink, or an absolute path, be
refused, and the refusal SHALL be reported to the worker as a failed tool call
rather than performing the operation.

#### Scenario: Path inside the fence is allowed

- **WHEN** the worker writes to a path that resolves inside an allowed directory
- **THEN** the write is performed and reported as successful

#### Scenario: Path escaping the fence is refused

- **WHEN** the worker reads or writes a path that resolves outside every allowed
  directory
- **THEN** the system refuses the operation and returns a failed tool call to
  the worker

### Requirement: The worker runs a bounded tool-use loop

The system SHALL let the worker issue tool calls and feed results back across
multiple rounds, up to a caller-supplied `max_tool_rounds`. When the budget is
reached, the system SHALL stop and return the work so far rather than continuing.

#### Scenario: Loop stops at the round budget

- **WHEN** the worker keeps issuing tool calls and reaches `max_tool_rounds`
- **THEN** the system stops the loop and returns a result rather than looping on

### Requirement: Written files are reported to the caller

The system SHALL report the list of files the worker wrote, so the caller can
validate the changes on disk.

#### Scenario: Result lists written files

- **WHEN** a delegation completes after the worker wrote one or more files
- **THEN** the result includes the paths of the files written

### Requirement: Worker escalates for ungranted access

When the worker needs a directory or a capability it was not granted, the system
SHALL return a `needs_input` result describing what the worker needs, rather
than failing or guessing.

#### Scenario: Worker needs a directory it was not granted

- **WHEN** the worker asks to write outside its granted directories, or needs a
  tool it was not offered
- **THEN** the system returns a `needs_input` result stating what access the
  worker needs
