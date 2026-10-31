# Spec Delta

## Purpose

Lets Kiro delegate a single, scoped task to a local Strata-backed worker and
receive a structured result it can judge, keeping planning and validation with
Kiro while the local model does the bounded work.

## ADDED Requirements

### Requirement: Delegate a scoped task to the local worker

The system SHALL expose an MCP tool that accepts a task description and a
context string, runs one self-contained completion against the local Strata
worker, and returns the worker's result. The worker SHALL NOT read or write the
filesystem or run commands in this capability; it produces text only.

#### Scenario: Task returns completed work

- **WHEN** Kiro calls the tool with a task and supporting context and the worker
  finishes the task
- **THEN** the system returns a result with an `ok` status and the worker's
  output text

#### Scenario: Worker performs no side effects

- **WHEN** the worker processes a task
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
