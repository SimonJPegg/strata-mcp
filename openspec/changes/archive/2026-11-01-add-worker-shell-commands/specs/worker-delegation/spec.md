# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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
