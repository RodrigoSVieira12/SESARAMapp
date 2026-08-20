# 10. Split `routing.py` by responsibility

**Status:** Accepted · **Date:** v0.13.1

## Context

An external code-review flagged that `routing.py` was accumulating too much
at once: the clinical/logistical policy, the choice of hospital, travel and
waiting times, opening hours, the Porto Santo rule, the yellow exceptions —
and a large amount of user-facing **text** (English opening-hour strings,
"opens Monday at 08:00", arrival texts, day-context phrases). Mixing the
decision logic with the wording of that decision made the file long and
gave it more than one reason to change.

## Decision

Split by responsibility, keeping the public names stable:

- `routing.py` **decides** — policy, candidate units, the chosen unit.
- `routing_textos.py` **words it** — the phrases shown to the user, in both
  languages (opening times, arrival texts, next-opening and day context).
- `motivos.py` **explains it** — the "why this recommendation?" list
  (ADR 0009).

Every helper that moved is still importable from `routing` (it re-exports
them), so older tests and any scripts that imported them keep working. No
behaviour changed; a test pins that the re-exported names still resolve.

## Consequences

- Each module has a single reason to change; the routing file shrank to its
  actual job.
- Reviewing or translating the wording no longer means reading the decision
  logic, and vice versa.
- Cost: three files instead of one; the seam is documented here and the
  compatibility re-exports must be kept until any importers are updated.

## When to revisit

If `routing.py` grows another distinct concern, the same treatment applies:
extract it behind a stable name. This is a direction, not a one-off.
