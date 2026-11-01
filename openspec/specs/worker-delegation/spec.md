# worker-delegation Specification

## Purpose
Lets Kiro delegate a single, scoped task to a local Strata-backed worker and
receive a structured result it can judge, keeping planning and validation with
Kiro while the local model does the bounded work.

## Requirements

### Requirement: Delegate a scoped task to the local worker

The system SHALL expose an MCP tool that accepts a task description and a
context string, runs one self-contained completion against the local Strata
worker, and returns the worker's result. The worker SHALL NOT read or write the
filesystem or run commands unless the caller grants those capabilities for the
call; absent any grant it produces text only.

#### Scenario: Task returns completed work

- **WHEN** Kiro calls the tool with a task and supporting context and the worker
  finishes the task
- **THEN** the system returns a result with an `ok` status and the worker's
  output text

#### Scenario: Worker performs no side effects

- **WHEN** the worker processes a task with no file or command grants
- **THEN** no files are created, modified, or deleted and no commands are run by
  the worker

### Requirement: Return a structured result envelope

The system SHALL return every delegation outcome as a structured envelope
carrying an outcome status, the worker's output, the elapsed wall-clock time,
token usage when Strata reports it, and an error message when the status is not
`ok`. Outcomes SHALL NOT be surfaced as unhandled exceptions.

#### Scenario: Elapsed time is always reported

- **WHEN** a delegation completes for any outcome
- **THEN** the envelope includes the elapsed wall-clock time for the call

#### Scenario: Token usage included when available

- **WHEN** Strata reports prompt and completion token counts
- **THEN** the envelope includes those counts

### Requirement: Worker self-reports when stuck or unclear

The worker SHALL be instructed to stop and return early with a specific
question or statement when the task is ambiguous, it is blocked, or it cannot
complete the task, rather than continuing indefinitely. The envelope status
SHALL distinguish a completed result from one needing input and from a rejected
task.

#### Scenario: Ambiguous task returns needing input

- **WHEN** the worker determines the task is ambiguous or it lacks information
  to proceed
- **THEN** the system returns a result with a `needs_input` status and the
  worker's question

#### Scenario: Infeasible task is rejected

- **WHEN** the worker determines it cannot perform the task
- **THEN** the system returns a result with a `rejected` status and the reason

### Requirement: Kiro validates every returned result

The system SHALL treat the worker's output as unverified. The delegation
contract SHALL NOT require the worker's self-reported status to be trusted as
correct; Kiro remains responsible for judging the output and for any filesystem
writes that follow.

#### Scenario: A completed result is still subject to validation

- **WHEN** the worker returns an `ok` status with output
- **THEN** Kiro judges the output against its own acceptance criteria before
  acting on it, and the acceptance criteria are not sent to the worker

### Requirement: Caller can list available models

The system SHALL expose a tool that returns the identifiers of the models
available from the inference engine, so the caller can choose one before
delegating.

#### Scenario: Listing returns available model identifiers

- **WHEN** the caller invokes the list-models tool
- **THEN** the system returns the identifiers of the models discovered from the
  inference engine

### Requirement: Caller can choose the model per delegation

The delegation tool SHALL accept an optional model identifier. When provided,
the system SHALL use that model for the completion. When omitted, the system
SHALL use the first available model.

#### Scenario: Caller-chosen model is used

- **WHEN** the caller delegates a task with a model identifier
- **THEN** the completion request uses that model

#### Scenario: Omitted model falls back to the first available

- **WHEN** the caller delegates a task without a model identifier
- **THEN** the completion request uses the first model discovered from the
  inference engine

### Requirement: Caller can control reasoning effort

The delegation tool SHALL accept an optional reasoning-effort level of `none`,
`low`, `medium`, or `high`, and SHALL reject any other value. When provided, the
system SHALL pass it to the completion request; when omitted, the system SHALL
NOT send a reasoning-effort value, leaving the backend's default in effect.

#### Scenario: Reasoning effort is passed through when set

- **WHEN** the caller delegates a task with a reasoning-effort level
- **THEN** the completion request carries that reasoning-effort value

#### Scenario: Omitted reasoning effort leaves the backend default

- **WHEN** the caller delegates a task without a reasoning-effort level
- **THEN** the completion request does not include a reasoning-effort value

#### Scenario: Invalid reasoning effort is rejected

- **WHEN** the caller supplies a reasoning-effort level outside the accepted set
- **THEN** the system rejects it rather than sending it to the engine

### Requirement: Server advertises concise usage guidance

The server SHALL advertise top-level guidance describing when a caller should
delegate: bounded, well-specified subtasks that the caller plans and validates,
not judgement-heavy or ambiguous work. The guidance SHALL be concise, because a
host loads it into context at connect time.

#### Scenario: Server exposes usage guidance

- **WHEN** a host connects to the server and reads its advertised information
- **THEN** the server provides a brief description of when to use it for
  delegation

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

### Requirement: Command running is opt-in and caller-fenced

The delegation tool SHALL accept an `allowed_commands` list of exact command
strings. The system SHALL offer a `run_command` tool only when the list is
non-empty. The worker SHALL be able to run a command only by matching an entry
exactly; it SHALL NOT be able to add arguments, compose commands, or run a
command not on the list. A non-empty `allowed_commands` SHALL require a non-empty
`write_dirs_allowed`, so a fenced working directory always exists.

#### Scenario: No allowed commands means no command tool

- **WHEN** a task is delegated with an empty or omitted `allowed_commands`
- **THEN** the worker is offered no `run_command` tool and runs no commands

#### Scenario: Only an exact match runs

- **WHEN** the worker asks to run a command string that is not an exact entry in
  `allowed_commands`, including an allowed command with extra arguments
- **THEN** the system refuses it and returns a failed tool call to the worker
  rather than running anything

#### Scenario: Commands require a write directory

- **WHEN** a task is delegated with a non-empty `allowed_commands` but no
  `write_dirs_allowed`
- **THEN** the system rejects the delegation rather than running commands with no
  fenced working directory

### Requirement: Commands run without a shell, inside the write fence

The system SHALL execute an approved command parsed to an argument vector and run
without a shell, so no shell interpretation, piping, redirection, or chaining is
possible. The system SHALL run each command with its working directory resolved
inside the granted write directories, using the same path fence as file writes,
and with a scrubbed environment.

#### Scenario: Approved command runs and returns its output

- **WHEN** the worker runs a command that exactly matches an allowed entry
- **THEN** the system executes it without a shell inside a granted write
  directory and returns its standard output, standard error, and exit code to
  the worker

#### Scenario: Non-zero exit is a result, not a crash

- **WHEN** an approved command exits with a non-zero status
- **THEN** the system returns the output and exit code to the worker as a tool
  result rather than raising or ending the delegation

### Requirement: Each command is bounded by a clamped timeout

The delegation tool SHALL accept a `max_command_timeout_s` ceiling. The worker
MAY supply a per-command timeout; the system SHALL clamp it to the ceiling, and
SHALL apply the ceiling when the worker supplies none. A command that overruns
its timeout SHALL be terminated and reported to the worker as a failed tool call.

#### Scenario: Worker timeout is clamped to the ceiling

- **WHEN** the worker requests a per-command timeout greater than
  `max_command_timeout_s`
- **THEN** the system runs the command with the ceiling, not the larger value

#### Scenario: Overrunning command is terminated

- **WHEN** an approved command runs longer than its effective timeout
- **THEN** the system terminates it and returns a failed tool call to the worker

### Requirement: Executed commands are reported to the caller

The system SHALL report the commands the worker actually ran, each with its exit
code, so the caller can validate what happened without trusting the worker's
account.

#### Scenario: Result lists executed commands

- **WHEN** a delegation completes after the worker ran one or more commands
- **THEN** the result includes each executed command with its exit code
