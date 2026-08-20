# 3. Stateless and database-free

**Status:** Accepted · **Date:** v0.1 (recorded v0.13.1)

## Context

A triage tool handles health data — the most sensitive category under the
GDPR. The most robust way to protect data you never wanted to keep is to
not store it at all. The clinical decision also does not need history: a
triage replays from the current answers.

## Decision

No patient records, sessions or history on the server. The frontend
accumulates the answers and re-sends all of them with each request; the
engine replays the path from scratch (cheap — the graphs are tiny). The
only server-side state is a file cache of waiting times, which contains no
personal data. The patient's own triage history, if kept, lives on their
device (`localStorage`), never on the server.

## Consequences

- There is nothing to breach, subject-access, or retain: the privacy
  posture is structural, not a policy bolted on.
- No database to run, migrate or back up — simpler to deploy and hand over.
- There is nothing to authenticate or administer, which is why there is no
  login (see ADR 0007's "what is left out").
- Cost: answers travel on each request (tiny payloads); no server-side
  analytics on individual journeys.

## When to revisit

If a genuine need to persist appears (a clinical audit trail agreed with
SESARAM, a rule-editing area for the clinical team), a database enters at
that moment, with a defined scope and its own data-protection assessment —
not by default.
