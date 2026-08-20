# 5. Waiting times by scraping, with a safety net

**Status:** Accepted (provisional) · **Date:** v0.8 (recorded v0.13.1)

## Context

Real waiting times materially improve the recommendation (an orange with
120 min at the local centre but 8 min at the hospital should hear about
it). SESARAM publishes them on public web pages, but offers no official
API. The prototype needs the data now, without being a bad citizen to the
source or ever showing invented numbers.

## Decision

Scrape the two public pages (`espera.py`), behind several safety nets: a
file cache with a short TTL so the site is hit at most once per TTL per
source, with an honest User-Agent; a **negative cache** so a failure is
not retried immediately; graceful degradation to "unavailable" (routing
then decides by hours and proximity, exactly as before); and the rule that
availability is measured by the presence of numbers, never by the courtesy
note the site always shows.

## Consequences

- The feature works today without waiting for an institutional API.
- The source is never hammered, and a scrape failure degrades cleanly.
- Users never see a fabricated waiting time.
- Cost: scraping is brittle to page changes — a real risk, accepted
  because the fallback is safe and the whole thing is provisional.

## When to revisit

This is explicitly a stopgap. The moment SESARAM exposes an official
waiting-times API, `espera.py` swaps its source and the scraping is
deleted — nothing else in the system needs to change. See
[`../INTEGRACAO.md`](../INTEGRACAO.md).
