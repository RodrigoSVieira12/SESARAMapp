# 7. Static frontend, no framework, local vendor

**Status:** Accepted · **Date:** v0.5 (recorded v0.13.1)

## Context

The interface is a linear flow: emergency signs → complaint → questions →
result → unit, plus a map and a PDF. It must work in a hospital setting,
degrade well without internet, and stay legible to whoever maintains it —
without a build step, a bundler or a node toolchain to keep alive.

## Decision

Plain HTML, CSS and vanilla JavaScript (`static/`), no framework and no
build. Third-party libraries (Mermaid, Leaflet, a QR generator) are
vendored locally under `static/vendor/` — no CDN. The UI text lives in one
bilingual file (`static/js/textos.js`); clinical text comes from the API
with `_en` variants (see ADR 0008).

## Consequences

- No build to run or break; open the files and read them.
- Works offline except for map tiles and live waiting times; the app and
  the flowcharts render with no internet.
- No supply-chain surprise from a CDN at load time.
- Cost: no framework conveniences (components, reactivity); acceptable for
  a flow this size, and it keeps the dependency surface tiny.

## What is left out (and why)

No login, JWT, OAuth, user profiles, admin panel or database. This is not
lack of time: with ADR 0003 (store nothing about anyone), there is nothing
to authenticate or administer, and adding accounts would create exactly
the personal data the design avoids.

## When to revisit

If a rule-editing area for the clinical team is ever built, that is a
separate, authenticated application — and the decision about a framework
and accounts is made there, with its own scope.
