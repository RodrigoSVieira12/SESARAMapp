# 11. Application logging, never user data

**Status:** Accepted · **Date:** v0.13.1

## Context

The application previously handled failures silently: a scraping error, a
fall back from OSRM to the network, a configured reference hospital with no
open emergency department in the data — all recovered safely (good) but
left no trace (bad for operating or debugging a real deployment). At the
same time, ADR 0003 forbids storing user data, and logs are a classic way
that rule gets broken by accident.

## Decision

Use Python's standard `logging`. An INFO line at startup records the
version and that the flows and questions validated; WARNINGs mark a
waiting-times source failing or stale data being served, OSRM falling back
to the calibrated network, and the safe-fallback path when the reference
hospital has no open emergency in the data. The level is adjustable with
the `ONDE_IR_LOG` environment variable. The **inviolable rule**: logs
record *system* events and never user data — no coordinates, no answers, no
per-user colours. A test asserts that the hospital-fallback warning leaks
no location. The command-line scripts keep `print()` on purpose: their
output *is* their interface.

## Consequences

- A real deployment can see what the system is doing and why a fallback
  happened, without a debugger.
- The privacy boundary is explicit and test-guarded, not left to habit.
- Cost: authors must keep user-identifying values out of log messages —
  hence the rule stated here and the guarding test.

## When to revisit

If structured logs or log shipping are ever needed in production, the
formatter/handler changes; the no-user-data rule does not.
