# 1. Clinical rules are data, not code

**Status:** Accepted · **Date:** v0.1 (recorded v0.13.1)

## Context

The triage flows are clinical knowledge. They will be reviewed, corrected
and eventually owned by health professionals, not by the intern who wrote
the code. Encoding "if fever and stiff neck then orange" as Python `if`
statements would lock that knowledge inside a language only programmers
read, and make every clinical correction a code change with a code review.

## Decision

Each complaint is a JSON file in `app/data/rules/` (7 flowcharts + the
emergency red-flags screen, 90 questions). The engine
(`triage_engine.py`) knows nothing about any specific symptom; it walks
question graphs. The same principle applies to every piece of local
knowledge: units and hours, the routing policy, the road network, measured
times, localities, and self-care advice — all JSON under `app/data/`.

## Consequences

- A clinician can review and fix rules without touching Python; changes
  are a readable diff.
- The rules generate the Mermaid flowcharts automatically for visual
  review (`/fluxogramas`, `docs/fluxogramas/`).
- The rules can be validated as data (see ADR 0002).
- Cost: the JSON format is a small contract to learn, documented in
  [`../DATA_GUIDE.md`](../DATA_GUIDE.md).

## When to revisit

If a flow ever needs logic a question-graph cannot express (scoring across
answers, weighting), the engine grows a new node type — the rules stay
data. Only if that proliferated would code-based rules be reconsidered.
