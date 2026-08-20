# 6. Travel time in layers, no hard external dependency

**Status:** Accepted · **Date:** v0.11 (recorded v0.13.1)

## Context

On Madeira, "nearest" in a straight line is often the wrong answer: the
unit closest on the map can be on the other side of the mountains. Real
routing needs road times. A hard dependency on an external routing service
(with its keys, quotas, latency and outages) is a heavy commitment for a
prototype, and would break offline.

## Decision

Estimate road time in layers, best-available first: (1) a local table of
598 hand-measured / precomputed origin→destination pairs
(`tempos_medidos.json`); (2) a calibrated, hand-tuned road network
(`rede_viagem.json`) for everything else; (3) an optional OSRM server, off
by default, switched on by the institution via an environment variable,
with a short timeout and a cooldown that falls back to the network on
failure. Units are then ranked by estimated time, with distance as the
tie-break.

## Consequences

- Good answers with no external dependency and full offline behaviour.
- A clear upgrade path: an internal OSRM improves accuracy by flipping a
  switch, and the local table can then be removed.
- The response is transparent about which method it used (`viagem_info`).
- Cost: the network's minutes are estimates pending the team's
  confirmation, and are honestly flagged as such in the UI.

## When to revisit

When an internal SESARAM OSRM exists, layer 3 becomes the primary source
and `tempos_medidos.py` is retired. The Google Distance Matrix API is a
possible alternative, weighed against cost and the no-external-dependency
goal.
