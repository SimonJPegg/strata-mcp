# Spec Delta

## ADDED Requirements

### Requirement: Server advertises concise usage guidance

The server SHALL advertise top-level guidance describing when a caller should
delegate: bounded, well-specified subtasks that the caller plans and validates,
not judgement-heavy or ambiguous work. The guidance SHALL be concise, because a
host loads it into context at connect time.

#### Scenario: Server exposes usage guidance

- **WHEN** a host connects to the server and reads its advertised information
- **THEN** the server provides a brief description of when to use it for
  delegation
