# 4. FastAPI as the web framework

**Status:** Accepted · **Date:** v0.1 (recorded v0.13.1)

## Context

The prototype needs a small HTTP API (triage, routing, supporting data)
plus a served static frontend, built in about a month by one intern, and
readable by whoever picks it up next.

## Decision

FastAPI, with Pydantic for request validation and Uvicorn as the server.
The whole app is a handful of route functions in `app/api/routes.py` over
the pure-Python core in `app/core/`.

## Consequences

- Request validation is declarative (Pydantic schemas in
  `models/schemas.py`); malformed requests are rejected before any logic.
- Interactive API docs come for free at `/docs` — useful for demos and for
  anyone integrating later.
- Async-capable if ever needed, but the code stays synchronous because the
  work is CPU-light and in-memory (see ADR 0003).
- Small, well-documented dependency surface; easy to containerise (one
  slim image, see the Dockerfile).

## When to revisit

Nothing here pushes toward a change. If the project ever needed server-side
rendering or a heavier admin surface, that would be a separate decision,
not a reason to replace the API framework.
