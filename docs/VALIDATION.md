# Validation status

What in this prototype is validated, and what is still pending. Aimed at a
SESARAM partner: it separates what an engineer can vouch for (the system
behaves as specified, checked by tests) from what only the institution can
sign off (the clinical content and the real-world data). (Versão
portuguesa: `VALIDACAO.md`.)

The single most important line in this document is the first pending item:
until the clinical flows are reviewed and approved, **this tool must not be
used with real patients.**

## Legend

- ☑ **Validated** — done and checked (by tests, or confirmed against a
  source).
- ☐ **Pending** — needs review or confirmation, by the party named.

## Clinical content — owner: SESARAM clinical team

- ☐ **Triage flowcharts** (`app/data/rules/*.json`). The 56 Manchester
  flowcharts (1187 discriminators) and the emergency red-flags screen were
  imported from the reference table and are not yet clinically validated.
  They must be
  reviewed question by question and approved. Use
  `python scripts/gerar_validacao_clinica.py` to produce
  `docs/validacao_clinica.html` (one complaint per page, with a
  signature/date block) for a paper review session; corrections then go
  back into the JSON, updating each file's `fonte` field with who
  validated and when.
- ☐ **Colour → service-type mapping** and the **per-colour routing
  policy** (`app/core/routing.py`, `app/data/encaminhamento.json`) —
  including the decision that red, orange and yellow go directly to the
  reference hospital. Editable without code; needs clinical sign-off.
- ☐ **Self-care advice texts** (`app/data/autocuidado.json`), shown for
  green and blue.
- ☐ **Patient-language rewrites of the advice card**
  (`app/data/aconselhamento_utente.json`): the lay PT/EN sentences of the
  "What you can do" card. Since v0.15.2 each item carries its own
  validation state (`validado`, `validado_por`, `validado_em`) — review is
  done item by item on the internal `/revisao` page (which also shows what
  the safety filter hides from the patient) and recorded in the file
  itself, applied with `python scripts/aplicar_aconselhamento_utente.py`.
  In production, `ONDE_IR_APENAS_VALIDADO=1` hides from the patient
  everything not yet validated. Current state: **0 of 85 items validated**.
- ☐ **Patient-language question rewrites**
  (`app/data/perguntas_utente.json`): the 186 lay PT/EN sentences that
  replace, on screen, the clinical questions of the 1187 discriminators.
  Since v0.15.3 each item carries the same per-item validation state —
  review is done in the "Questions" section of the `/revisao` page
  (official clinical question side by side with the rewrite) and recorded
  with `python scripts/marcar_validado.py perguntas "<clinical text>"
  --por "Name"` (no apply step needed). The risk here is lower than for
  the advice: in production, `ONDE_IR_APENAS_VALIDADO=1` **reverts**
  anything not validated to the official Manchester clinical question
  (nothing is hidden). Current state: **0 of 186 items validated**.
- ☐ **The experimental swap rule** (prefer a slightly farther unit when it
  saves a lot of total time) — flagged in the UI as experimental; needs a
  clinical decision on whether to keep it and with what thresholds.

## Unit data — owner: SESARAM + data survey

- ☐ **Addresses, phone numbers, services and opening hours** in
  `app/data/unidades.json`, wherever marked `(CONFIRMAR)` /
  `"dados_confirmados": false`. `scripts/validar_dados.py` lists exactly
  which units still carry unconfirmed data, as a survey checklist.
- ☐ **Unit coordinates** — currently approximate.
- ☐ **Locality coordinates** (`app/data/localidades.json`) — the intern's,
  pending the team's confirmation (see the `"pendentes"` / `"verificado"`
  fields).
- ☐ **Road network minutes and reference journeys** (`rede_viagem.json`,
  `percursos_referencia.json`) — hand-calibrated estimates, pending
  confirmation.

## Engineering — owner: development (checked here)

- ☑ **Data integrity at startup**: unique ids, complete branches, valid
  colours, colour matching the priority, discriminators ordered by
  priority; the server refuses to start
  otherwise (ADR 0002). Re-checkable with `scripts/validar_dados.py`.
- ☑ **Routing behaviour** across colours, islands, opening hours, holidays,
  the direct-to-hospital policy and its safe fallback — covered by the test
  suite (`tests/`).
- ☑ **Explainability**: every routing branch returns a `motivos` list;
  tests pin the shape and the reasons per branch (v0.13.1).
- ☑ **Translation coverage**: `scripts/auditar_traducoes.py` reports zero
  untranslated strings, and CI enforces it.
- ☑ **The one-page PDF** always fits on a single page, whatever the triage
  outcome — pinned by a test.
- ☑ **Waiting-times safety nets**: short-TTL cache, negative cache, and
  "unavailable" degradation (never invented numbers) — covered by tests.
- ☑ **Privacy in logs**: a test asserts the hospital-fallback warning
  contains no user location (ADR 0011).
- ☑ **Test suite**: 408 tests passing, 92% coverage of `app/`
  (`scripts/cobertura_testes.py`).

## Not decided here — for SESARAM

These are institutional choices, not prototype defects (see
[`INTEGRACAO.md`](INTEGRACAO.md)): whether waiting times come from an
official API instead of scraping; whether an internal OSRM replaces the
travel network; whether the "call the unit" button fits internal policy;
and whether the on-device history stays local or is integrated.
