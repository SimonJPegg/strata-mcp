# Spec Delta

## MODIFIED Requirements

### Requirement: Reach Strata over the OpenAI-compatible API

The system SHALL communicate with the local inference engine using its
OpenAI-compatible chat-completions API. The system SHALL discover the available
model identifiers from the model-listing endpoint. When the caller does not
choose a model, the system SHALL use the first discovered model.

#### Scenario: Completion request uses the discovered model

- **WHEN** the system sends a completion request and the caller has not chosen a
  model
- **THEN** the request targets the OpenAI-compatible endpoint using the first
  model discovered from the model-listing endpoint

#### Scenario: Multiple available models are all discoverable

- **WHEN** the model-listing endpoint returns more than one model
- **THEN** the system makes the full list of model identifiers available rather
  than only the first
