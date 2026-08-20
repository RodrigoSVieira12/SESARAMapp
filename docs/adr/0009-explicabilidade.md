# 9. Every recommendation explains itself (`motivos`)

**Status:** Accepted · **Date:** v0.13.1

## Context

Until v0.13.0 the app said "go to Hospital X" without showing its
reasoning. For a clinical partner evaluating the prototype, and for a
clinician who has to trust or challenge a recommendation, the *why* matters
as much as the *what*: which colour, which policy, was the unit open, how
far, what is the current wait, did the experimental swap rule act. That
reasoning already existed inside `routing.py`; it was just not surfaced.

## Decision

Every `/api/encaminhamento` response carries `motivos`: an ordered,
bilingual list of the factors behind the decision. The first is always the
estimated colour; then the policy applied and its source (configuration,
flowchart outcome, or safe fallback), whether the recommended unit is open,
the travel estimate, the current waiting time, the swap-rule note when it
acted, and the island rule on Porto Santo. A new module, `motivos.py`,
formats facts the routing already decided — it takes no decisions and holds
no logic of its own. The interface shows the list in an expandable
"Why this recommendation?" block on the recommendation card.

## Consequences

- A clinician can audit a decision without reading code.
- The reasons reuse the exact numbers already in the message (e.g. the
  swap rule's both-sides totals), so the explanation cannot contradict the
  recommendation.
- The house rules apply: bilingual `_en` variants, no em dashes, and — the
  golden rule inherited from the waiting-times work — a reason only appears
  when its underlying data actually exists; nothing is invented.
- Cost: a `motivos` block is assembled per request (cheap, in-memory).

## When to revisit

If a new routing branch or factor is added, it gets a matching reason (and
a test pins it). The mechanism is stable; only the catalogue of reasons
grows.
