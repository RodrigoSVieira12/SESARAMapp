# 2. Validate the data at startup (fail fast)

**Status:** Accepted · **Date:** v0.1 (recorded v0.13.1)

## Context

Hand-edited data is data that will eventually be wrong: a duplicate id, a
branch that goes nowhere, a colour that does not exist, a question that
references a sibling that was renamed. Discovering such an error halfway
through a real triage — a dead end in front of a patient — is not
acceptable in a clinical context.

## Decision

The server **refuses to start** if any flowchart has duplicate ids,
missing branches, invalid colours, references to nonexistent questions,
cycles or unreachable questions, and says exactly what and where.
`scripts/validar_dados.py` runs the same checks (plus units, coordinates
and opening-hour formats) without starting the server, for the people who
edit the JSON and do not program.

## Consequences

- A data error becomes a problem for whoever edited it, at the moment
  they edited it — not a runtime surprise later.
- The error message is in plain language, aimed at a non-programmer.
- Cost: startup does a little validation work; negligible for this size.

## When to revisit

The checks are additive: a new failure mode means a new check, not a
change of approach. This decision is unlikely to be reversed.
