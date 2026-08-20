# Changelog

The full version history of the prototype, newest first. The README
keeps only a pointer here, on purpose: this file can grow, the README
cannot. (Versão portuguesa: `CHANGELOG.pt.md`.)

Versions before v0.5 predate this log — the initial triage engine,
startup validation and the holiday calendar (v0.4) — and their details
live in the git history.

## v0.16.2 — robustness: readable errors, anti-abuse limits, local fonts, API contract

Second round of the external "demanding senior engineer" style review
(the first produced v0.16.1): five robustness improvements, all pinned
by new tests, with no change to the clinical logic.

- **Readable data errors end to end (this round's real bug).** A SYNTAX
  error in a rules JSON — the most likely mistake when hand-editing —
  was the only one escaping the friendly messages: it blew up with a raw
  traceback at startup (without naming the file in the message) and with
  a `500 Internal Server Error` on `/api/fluxogramas`, despite the
  docstring promising the message in the `"erro"` field (reproduced in
  the review with one extra `{` in a real file). The engine's
  `_carregar` now converts `json.JSONDecodeError`/`OSError` into a
  `RuntimeError` carrying the file NAME — the same format as the
  existing validations — and the endpoint keeps its promise again. Two
  more mistakes of the same family also gained clear messages: a
  non-object JSON root and a flow without a top-level `"id"` (previously
  raw `AttributeError`/`KeyError`).
- **Sanity limits on requests (anti-abuse).** A single crafted
  `POST /api/exportar_pdf` cost **~33 seconds of CPU** (measured in the
  review): on a public, unauthenticated endpoint, a handful of such
  requests would take the server down. Three layers land, cheapest
  first: (1) a cap on request body size — ASGI middleware in
  `app/main.py`, early `413`, 1 MB by default, configurable via
  `ONDE_IR_CORPO_MAXIMO`; (2) maximums on every text and list field of
  the schemas (`app/models/schemas.py`), generous against real data (the
  largest flow has ~40 discriminators, the longest message ~700
  characters) so no legitimate request changes; (3) the PDF generator
  itself trims what it draws (`_aparar`, ceilings in `pdf_clinico.py`),
  so the property holds even for direct callers. The same attack now
  costs ~0.03 s.
- **Public Sans self-hosted (offline + GDPR).** The typeface came from
  Google Fonts at runtime — the one remaining CDN call, contradicting
  both "works offline" (Leaflet, Mermaid and the QR generator already
  lived in `static/vendor` for exactly that reason) and the privacy
  posture: loading fonts from Google sends every user's IP to a third
  party. The four weights the interface uses (400/600/700/800, woff2)
  now live in `static/vendor/public-sans/`, licence (SIL OFL 1.1)
  alongside, taken from the official v2.001 release of the U.S. Web
  Design System. This also clears the way for a strict
  Content-Security-Policy.
- **Response formats documented in `/docs` (a complete contract).** The
  endpoints returned `dict`, so the interactive docs showed requests but
  not responses — half a contract, right where the integration argument
  lives. `/api/triagem`, `/api/encaminhamento` and
  `/api/integracao/triagem` now declare `response_model`
  (`app/models/respostas.py`, new), with two deliberate choices so that
  documenting breaks nothing: `extra="allow"` (a new key from the
  routing is never silently dropped from the response) and
  `response_model_exclude_unset` (keys the routing did not set stay
  ABSENT on the wire, not `null`). Tests pin the format in both
  directions: `politica` still does not appear on green and still does
  on yellow.
- **3.11+3.12 CI matrix and a licence.** The README promises
  "Python 3.11+" but CI only tested 3.12; the matrix now tests both
  (`fail-fast` off, to see both when one breaks). And the repository had
  no licence: `LICENSE` (MIT) lands at the root — with the rights holder
  flagged as pending confirmation between the author and SESARAM — plus
  a "License" section in both READMEs delimiting what the code licence
  does NOT cover: the clinical content from the Manchester table
  (licensed by the Grupo Português de Triagem) and the vendored
  libraries, each with its own licence alongside.

The fourteen new tests live in `tests/test_v16_2.py`.

## v0.16.1 — PDF hardening, lint in CI, pinned dependencies

A fix-up release, driven by an external "demanding senior engineer"
style code review. No new features: three finishing fronts, in order of
importance.

- **PDF markup injection fixed (the real bug).** reportlab's
  `Paragraph` interprets a mini-HTML, and `pdf_clinico.py` was handing
  it request text unescaped: a message with a stray `<b>` crashed the
  generation (500), an `<img>` tag made the server try to open a file,
  and an invalid entity (`&#xZZ;`) was another 500. Every piece of
  external text now goes through `_esc()` (escaping `<`, `>`, `&` and
  quotes) before reaching reportlab; only markup written by the module
  itself is interpreted. Ten new tests (`tests/test_pdf_escape.py`) pin
  the behaviour: hostile payloads must return a valid PDF AND show the
  text literally (escaping is not deleting).
- **Documentation numbers and links tell the truth again.** Badges and
  README text had drifted (370/341 tests "as of v0.15.3", "latest
  version v0.13.1"); they now reflect the real suite and this version.
  References to `docs/adr/0012-logging.md` and
  `docs/adr/0011-divisao-routing.md` (old numbering) now point to the
  files that exist: `0011-logging.md` and `0010-divisao-routing.md`.
- **Lint and format in CI; dependencies pinned.** `ruff` and
  `black --check` join `ci.yml` (configuration in the new
  `pyproject.toml`; versions in `requirements-dev.txt`) — an F811 would
  have flagged `_primeira_aberta` being defined twice in `routing.py`,
  now deleted, and mid-file imports moved to the top. The whole
  codebase was formatted with black (a mechanical change; the test
  suite confirms nothing moved). `requirements.txt` now pins the exact
  tested versions, for reproducible builds.

## v0.16.0 — the "health app" frontend

An interface-only release. The starting point was an external UX/UI
review (generated by an AI assistant) with twenty suggestions; this
version is a CRITICAL reading of that review, not a blind application of
it. **No clinical text changes**: questions, advice and rules stay
untouched in the data files (they have their own validation pipeline,
and rewriting 1,187 questions is exactly where meaning would drift).
What changes is the presentation.

What the review got right (and went in):

- **Giant Yes/No.** The answer buttons become 88px blocks with tick and
  cross icons and weight 800 — the answer IS the screen. They stay
  deliberately NEUTRAL: in triage, "yes" usually means worse, and
  painting "yes" green would send the wrong signal. On tap, the chosen
  button confirms itself for an instant before the next question slides
  in (and both disable against double taps); with reduced motion set at
  system level, it advances immediately.
- **A progress bar — but an honest one.** The suggestion was
  "8 / 12 questions"; that exact total cannot be promised, because the
  assessment can end earlier depending on the answers. What is shown is
  "Question N · at most M" (the flow's real maximum, which the API
  already sent) with a bar that fills toward that maximum — it answers
  "are 2 left, or 30?" without lying and without explaining the
  early-exit mechanic (explaining it would bias answers).
- **An app-like home page.** Cover-sized title, ONE huge button ("Start
  assessment") and everything else in the background: the three steps
  collapse into "How does it work?", and two contact shortcuts appear
  (112 and SNS 24, the same as the footer) because someone arriving in a
  panic should not have to scroll. The original suggestion asked for
  MORE options on the home page ("browse units", etc.), contradicting
  its own one-goal-per-screen principle — that part did not go in.
- **The result as a card.** The priority guide is now the signature
  element: background tinted in the triage colour, a colour spine, the
  accessible shape + colour name in the label, a prominent
  classification in a compact card and the target time in a pill with a
  clock. It opens
  with "Based on your answers:" instead of reading like a database
  field. The tints and per-level text colours were computed to meet
  WCAG (the auditor checks every `--cor-texto` value).
- **A unit card with statistics.** The three numbers that decide the
  trip — driving time, wait and open/closed — are promoted from chips to
  stat blocks (big number, small label, "est./recorded" note). Chips
  remain as a second line of context (road km, people waiting). The
  address gains an icon; opening hours collapse into an accordion that
  opens by itself when the unit is closed (which is when they matter).
- **The map in an accordion, open by default.** The suggestion was to
  hide it behind "Show on map"; what went in is the accordion, but OPEN
  from the start (seeing where the unit is helps more than hiding the
  map), with "Hide the map" for anyone who prefers the short screen.
  The preference survives the language switch and Leaflet starts only
  inside the accordion, never in the screen's render body.
- **Hierarchy, spacing and micro-interactions.** A type scale with
  weight 800 for titles and the question, more air between cards, 16px
  corners, subtle shadows ON TOP of the visible borders (the borders
  stay: they are the accessibility of users with reduced contrast
  sensitivity), short transitions — all switched off under
  `prefers-reduced-motion`.
- **Icons, not emojis.** The single-stroke SVG set grows (tick, cross,
  phone, map, shield) for answers, shortcuts, contacts and the map
  accordion. Emojis stay out: they vary by system and feel off in a
  clinical context.

What the review did not know (and therefore did not change):

- The questions are ALREADY in lay language since v0.14.1
  (`texto_utente`), "Why this recommendation?" has ALREADY existed since
  v0.13.1, times ALREADY read "~18 min", and the interface is ALREADY
  neutral outside the result (the v0.14.1 decision stands: no Manchester
  colour during the questions).
- A separate "summary screen" would duplicate the destination card; the
  useful core of that idea went in as a context pill: the priority
  (shape + colour + classification) follows the person to the routing
  screen.

Also in this release:

- **A grouped complaint list.** "Adults and general situations" and
  "Babies and children", using the `pediatrico` flag the API already
  sent — stressed parents no longer scan 56 mixed cards. Search stays on
  top of everything.
- **Listen to the question.** The read-aloud button (v0.15.1) reaches
  the question screen, with the same local Web Speech API.
- **Contacts with icons** and the brand mark in the header.
- New tests in `tests/test_v16.py` pin the honest bar, the neutral
  buttons, the tinted guide, the map open by default in its accordion
  (no Leaflet start at render time) and the bilingual keys; the `test_v15_3` cache pin no
  longer fixes the exact number (the same step `test_v15_2` had already
  taken). "112" and "SNS 24" are written in the markup, like in the
  footer: numbers and brands are not copy to translate, and the
  translation auditor keeps having no exceptions.

## v0.15.3 — questions as data

The mirror of v0.15.2, now for the other half of the lay content: the
triage questions rewritten in patient language. No patient-facing text
changes and the triage logic is untouched — what changes is who can edit
what, what gets recorded, and what breaks CI when someone slips. With
this, no clinical content lives inside Python code anymore.

- **The questions leave the code.** The 186 lay rewrites (PT and EN,
  side by side) covering the 1187 discriminators lived in a dictionary
  in `scripts/_perguntas_utente.py`; they move to
  `app/data/perguntas_utente.json`, editable like any other data file,
  and the `.py` is reduced to a loader (the historical name
  `PERGUNTAS_UTENTE` keeps working for the table importer). Editing and
  applying **no longer needs the Excel file**: the new
  `scripts/aplicar_perguntas_utente.py` rebuilds only
  `texto_utente`/`texto_utente_en` across the `rules/` files (the
  clinical text is untouched), is byte-for-byte idempotent and only
  rewrites the files that changed.
- **Per-item validation state — living only in the editable file.**
  Each rewrite gains `validado`, `validado_por` and `validado_em`, as in
  the advice, but with a different design decision: the state is **not
  copied** into the rules. The rules are also edited by hand, and a copy
  of the state there was a guarantee of drift; the engine reads
  `perguntas_utente.json` at startup when it needs it.
- **The production gate reverts — it does not hide.** With
  `ONDE_IR_APENAS_VALIDADO=1`, not-yet-validated rewrites are removed
  from the questions and the patient sees the **official clinical**
  Manchester question (the engine's natural fallback, which is the
  validated source). Hiding a question would change the triage, so the
  gate semantics differ here: for advice it hides, for questions it
  swaps the proposed wording for the official one. Missing file with the
  gate on = everything reverted with a warning; corrupted file = startup
  error.
- **The review view gains a questions section.** The internal `/revisao`
  page now has two sections (Advice | Questions); the new one shows, per
  flow, the official clinical question side by side with the PT/EN
  rewrite, the colour/priority and each item's validation state, with
  the same filters (pending only, search) and data re-read from disk on
  each refresh (`GET /api/perguntas/revisao`, with the editable file's
  SHA-256 in the response).
- **Its own verifier in CI.** The new `scripts/verificar_perguntas.py`
  requires **full coverage** — a discriminator without a rewrite entry
  is an error, because the patient would see the clinical text without
  anyone having decided that — and catches rewrites edited without
  applying (or rules edited by hand, compared item by item), orphan
  keys, incomplete PT/EN pairs and validations without who/when. It
  lists as WARNINGS the clinical texts repeated within the same flow (12
  cases inherited from the official table, which by construction share
  the same rewrite) and distinct keys colliding into the same lay
  sentence (currently zero).
- **`marcar_validado.py`: validating without hand-editing JSON.** A
  single CLI for both rewrite files (`aconselhamento` | `perguntas`):
  lists what is pending (`--listar --contem ...`), marks and unmarks by
  the exact clinical key (extra whitespace is tolerated; a wrong key
  writes nothing and suggests close matches), fills the three fields at
  once and rewrites the file in the canonical format — `git diff` shows
  only the touched fields. For advice it runs the apply step
  automatically (so the SHA-256 in `fonte.reescritas` stays in sync);
  for questions it is not needed, because the state lives only in the
  editable file.
- **The frontend's bilingual choice gains tests.** The rule "use the
  `*_en` field when the language is English and it exists; otherwise
  Portuguese" lived in `app.js`'s `campo()`, untested. It moves to the
  core (`Nucleo.textoNaLingua`, pure functions) with six new Node tests
  — including engine question objects and the guarantee that `undefined`
  never reaches the screen — and `campo()` merely injects the active
  language. That makes 14 Node tests in total.
- **Old tests stop pinning the exact version.** The `index.html` test
  (v0.15.2) required literal `?v=20` and `v0.15.2`, and the version test
  required equality — every release forced edits to older versions'
  tests. They now pin what matters (the core's load order, a version
  minimum); the exact cache-busting number lives in the current
  version's tests. The suite adds 29 new tests (`tests/test_v15_3.py`),
  for a total of 370.

Deliberately left for later: the real modularisation of `app.js` (~1450
lines; the core remains the brick, not the building) and a fuller JS test
runner; visual regression and real screen-reader testing — the reworked
`/revisao` page was checked by tests and by hand against the API, but
not in a real browser; the clinical reconciliation of self-care × advice
(visible and listed since v0.15.2, still to be decided); the backlog of
lay advice rewrites (~148 candidates); and the clinical validation
itself — 0 of 85 advice items and 0 of 186 questions validated, now with
the tool to record each approval.

## v0.15.2 — advice governance and safety nets

A deliberate housekeeping release: no patient-facing text changes (except
the hairlines, see below) and the triage logic is untouched. What changes
is who can edit what, what gets recorded, and what breaks CI when someone
slips — the architecture and governance weaknesses identified in the
v0.15.1 review.

- **The patient sentences leave the code.** The thing the clinical team
  will most want to fix — the lay sentences of the "What you can do"
  card — lived in a `.py`, against the "rules as data" philosophy. The 85
  rewrites (PT and EN, side by side) move to
  `app/data/aconselhamento_utente.json`, editable like any other data
  file; `scripts/_aconselhamento_utente.py` became a loader, and the
  historical names keep working. Editing and applying **no longer needs
  the Excel**: the new `scripts/aplicar_aconselhamento_utente.py`
  rebuilds only the patient layer of `aconselhamento.json` (the clinical
  text is untouched), is byte-for-byte idempotent, and the table importer
  uses exactly the same merge function — one logic, no drifting copies.
- **Per-item clinical validation state.** Each rewrite gained `validado`,
  `validado_por` and `validado_em` (YYYY-MM-DD): drafts and approved
  content are no longer indistinguishable to the system. The verifier
  demands a complete record when `validado=true`, and the new production
  gate `ONDE_IR_APENAS_VALIDADO=1` makes the engine hide from the patient
  everything not yet validated (the clinical text still reaches
  integrators). Off by default: in development everything shows, marked
  as subject to validation. The current state (0 of 85 validated) is
  recorded in `docs/VALIDATION.md`.
- **A clinician review view (`/revisao`).** Whoever reviewed the patient
  screen could not see what the safety filter hides — and so could not
  confirm the filter is right. The new internal page shows, per flow and
  colour, the clinical advice side by side with the lay PT/EN sentence,
  each item's validation state and, in grey, the items hidden from the
  patient; with filters (hidden only, pending only, search) and data
  re-read from disk on each refresh (`GET /api/aconselhamento/revisao`),
  like the flowcharts. It is the tool for the item-by-item validation
  session.
- **Data provenance.** `aconselhamento.json` gained a `fonte` block:
  `fonte.tabela` records exactly which Excel the advice came from (name,
  SHA-256, date, row count — filled on the next import; until then the
  verifier warns that provenance is unrecorded) and `fonte.reescritas`
  stores the SHA-256 of the editable file. That hash is what turns "I
  edited the rewrites and forgot to apply" into a CI error with the exact
  command to run — and "someone hand-edited the generated file" is caught
  too, item by item.
- **Importers without duplicated logic.** `slug()`, key normalisation and
  the priority→colour map were defined twice (`importar_manchester.py`
  and `importar_aconselhamento.py`) and had to be kept in sync by hand —
  if `slug()` changed in one and not the other, the flow↔advice mapping
  broke silently. They now live once in `scripts/_manchester_comum.py`,
  with their own tests; the rules' `limpar()` stays local on purpose (it
  preserves the discriminators' internal spacing, and the comment
  explains the difference).
- **The frontend safety property got tests.** The guarantee "the patient
  only sees items with `texto_utente`; never the clinical text" lived
  inside `app.js` with no test at all — if someone "improved" the filter
  to fall back to the clinical text, nothing would catch it. Filtering,
  language choice and deduplication moved to `static/js/nucleo.js` (pure
  functions, no DOM), pinned by eight tests that run in Node
  (`tests/js/teste_nucleo.js`), in CI and wrapped in pytest; `app.js`
  merely paints what the core returns. It is the first — deliberately
  small — step of the frontend modularisation.
- **An accessibility audit in CI — and the hairlines fixed.** The new
  `scripts/auditar_acessibilidade.py` checks what is checkable without a
  browser: WCAG contrast ratios of the colour pairs actually in use
  (text ≥ 4.5:1; components ≥ 3:1), the page language, a viewport that
  does not block zoom, accessible names on static buttons, `aria-live`,
  `:focus-visible`, touch targets ≥ 48 px and no positive `tabindex`.
  The first run confirmed the v0.15.1 analysis: the only real problem was
  the hairlines (1.4:1, invisible to anyone with reduced contrast
  sensitivity). With the high-contrast button removed, the base theme now
  has to comply on its own: `--linha` rose to 3.6:1 and `--linha-forte`
  to 5.7:1 — **the only visible change in this release** (darker
  hairlines), revertible in two lines of CSS, but the audit blocks the
  regression in CI.
- **A more complete verifier.** Beyond orphan keys and PT/EN pairs,
  `verificar_aconselhamento.py` now catches: rewrites edited without
  applying (SHA), hand edits of the generated file, incomplete validation
  state and the pre-v0.15.2 structure without state. And it lists, as a
  WARNING, the **self-care × advice overlaps** within the same colour
  (very similar sentences that can appear on the same screen) — the
  relationship between the two blocks is now defined in the data guide,
  but the reconciliation is a clinical decision and stays out of CI on
  purpose.

Deliberately left for later: the real modularisation of `app.js` (~1300
lines; the core is the first brick, not the building) and a fuller JS
test runner; visual regression and real screen-reader testing (the static
audit replaces neither); the clinical self-care × advice reconciliation
(now visible and listed, but undecided); the same "from `.py` to data"
migration for the patient questions (`scripts/_perguntas_utente.py`, the
same pattern as the advice); and the backlog of lay rewrites the verifier
sizes (~148 candidates).

## v0.15.1 — safer, bilingual, reordered advice

A follow-up to v0.15.0, now looking at the "What you can do" card from
the point of view of the people who need it most: the seriously ill
patient, the patient with low literacy or poor eyesight, and the visitor
who does not speak Portuguese. Interface and safeguard changes; the
triage logic is unchanged.

- **The ordering no longer works against the sickest patient.** For red,
  the first-aid card now comes **right after the 112 button** (no longer
  after the restart button). For the other colours, the advice appears
  before the navigation. The first piece of advice in each colour is
  highlighted as the **main action**, so it stands out under stress.
- **The advice in English.** Every lay advice item gained the
  `texto_utente_en` variant (map `ACONSELHAMENTO_UTENTE_EN`, with exactly
  the same keys as the Portuguese one; identical PT sentences share the
  same translation, so on-screen deduplication works the same in both
  languages). With the interface in EN, the "What you can do" card is
  entirely in English; if a translation is ever missing, the usual safe
  fallback applies (the Portuguese is shown). Like the Portuguese text,
  the translations are a proposal awaiting clinical validation.
- **Read aloud, in both languages.** A "Listen" button on the card, using
  the browser's Web Speech API (local, no network). It reads what is on
  screen, in the interface language: pt-PT in Portuguese, en-GB in
  English. The button only appears if the browser supports speech
  synthesis; reading stops when the screen changes.
- **The advice no longer disappears at routing — and it moves.** Tapping
  "see where to go" keeps the "What you can do" card, but now at the
  **end of the screen**, after the units and the contact buttons: at that
  point the patient has already seen the advice on the result screen, and
  what they look for first is where to go and whom to call. The PDF,
  print and new-assessment buttons close the page.
- **The bracelet colour is no longer on its own.** Each level gains a
  **distinct shape** before the colour label (circle, triangle, diamond,
  square, star), legible by people with red-green colour blindness (about
  8% of men).
- **No repeated advice for the patient.** The card now deduplicates at
  the level of the displayed text (in the active language): two distinct
  clinical items that collapse into the same lay sentence (for example
  "paracetamol" and "paracetamol or ibuprofen") no longer produce two
  near-identical bullets.
- **A safeguard against the mapping's silent failure.** The lay advice is
  linked to the clinical text by the exact string; a single stray space in
  the table was enough for a piece of advice to vanish from the screen
  with no error at all. The new `scripts/verificar_aconselhamento.py`
  catches that drift (orphan keys = CI failure) and prints a report:
  coverage, text collisions, typos inherited from the source
  (`paracematol`, `cetrizina`, `analgesicos`) and the size of the hidden
  backlog (a rough estimate of how much is genuinely professional-only and
  how much is safe lay advice still to be rewritten). With English on
  board, it also checks that the PT and EN maps have the same keys, that
  no EN key is orphaned, and that `aconselhamento.json` is up to date
  (every `texto_utente` with its `texto_utente_en`). Wired into
  `validar_dados.py` and CI. Also removed a dead key (a truncated "Sinais
  de choque...") that matched no advice and never reached the patient.

Deliberately left for later (needs clinical validation and/or is a larger
expansion): pictograms for the key gestures (recovery position, stroke
test, choking); grouping the conditional advice ("if conscious" / "if
unresponsive") into mini-flows; and rewriting the safe lay advice that is
still hidden (the backlog the verifier now sizes).

## v0.15.0 — patient advice ("What you can do")

The result screen now shows a card with practical advice for the flow and
colour reached. Purely additive change: the triage logic is unchanged
(priorities and colours stay exactly the same).

- **New data source `app/data/aconselhamento.json`.** The advice column of
  the Manchester table is imported by
  `scripts/importar_aconselhamento.py` and organised by flow and colour
  (56 flows, 935 items in total). Each entry is a list deduplicated per
  (flow, colour), in first-appearance order. The file is now documented in
  the data guide.
- **Dual storage `texto` / `texto_utente`, like the questions.** Each item
  keeps the clinical `texto` from the table (fidelity, and what
  integrators receive at `/integracao/triagem`) and, where a safe lay
  version exists, a plain-language `texto_utente` (see
  `scripts/_aconselhamento_utente.py`). At present 572 of the 935 items
  (61%) already have a patient version.
- **Safety policy: the patient only sees vetted lay advice.** The table's
  advice is written for the triage professional and includes actions that
  must not be given as instructions to a layperson (assessing the
  Cincinnati scale, contact isolation, dispatching resources, drugs by
  name, calling the poison centre, sending the police...). So, unlike the
  questions, the frontend does **not** fall back to the clinical text: it
  only shows items with a `texto_utente`. The rest stay in the backend but
  never reach the patient. Where the layperson's action differs from the
  clinical one, the safe at-home action is used (for example, for a
  deformed limb, "do not try to straighten the limb, keep it still"
  instead of "align the limb").
- **The card appears on the result screen, not only at routing.** That is
  where first-aid advice matters most: in a red situation the patient
  calls 112 and may never reach the routing screen. The routing screen's
  "Why this recommendation?" block is unchanged.
- **Advice text is Portuguese only, with a safe fallback to English.** The
  table is Portuguese only; in English, the per-item advice shows the
  Portuguese text (as happens elsewhere already). The "What you can do" /
  "O que pode fazer" heading and the footnote are bilingual.
- **Still pending clinical validation.** Like the self-care and patient
  questions, these rewrites are a proposal and are marked as subject to
  clinical validation before real use.

## v0.14.3 — full translation of saved evaluations and a larger synonym dictionary

Two focused fixes, no change to the clinical triage logic (priorities and
colours are untouched).

- **Saved evaluations now follow the language toggle.** On the "previous
  evaluations" screen, the complaint name (e.g. *Dispneia no adulto* /
  *Shortness of breath in adults*), the colour label and the answered
  questions stayed in the language they were saved in and did not switch
  when toggling PT/EN. The history now stores both languages for each
  entry (instead of a single already-resolved string) and resolves the
  visible text against the active language at render time, matching how
  the rest of the app already worked. Entries saved before this version
  keep the language they were recorded in.
- **Free-text search dictionary expanded.** `app/data/sinonimos.json` now
  merges the previous terms with the extended clinical word list: every
  one of the 56 triage flows now has synonyms (previously 39), with the
  union of all distinct terms on both sides preserved. This removes the
  "flow without synonyms" validator warnings and widens what patients can
  type (including PT/EN/ES/FR/DE/IT variants). Still pending review by the
  clinical team, as the file header notes.

## v0.14.2 — municipal holidays, robustness and frontend polish

A batch of small improvements, all pending validation with SESARAM. The
clinical triage logic (priorities and colours) is unchanged; what changes
is routing in a few cases and several patient-facing texts.

- **Municipal holidays, per municipality.** Each of the 11 municipalities
  now has its municipal holiday, applied **only to units in that
  municipality** (Funchal 21 Aug, Santa Cruz 15 Jan, Machico 8 May,
  Santana 25 May, Calheta 24 Jun, Ponta do Sol 8 Sep, Ribeira Brava 29
  Jun, Câmara de Lobos 4 Oct, São Vicente 22 Jan, Porto Moniz 22 Jul,
  Porto Santo 24 Jun). On those days the municipality's walk-in
  consultations close, but — as with national/regional holidays —
  emergency and urgent care (24h) stay open. The decision always uses
  **each** unit's own `concelho` from `unidades.json`: so the Santo da
  Serra health centre, whose municipality is "Machico", closes on 8 May
  (Machico's holiday), not on 15 January (Santa Cruz) — the intended
  behaviour. Implemented by threading the municipality through
  `horarios.esta_aberto` / `proxima_abertura` down to
  `feriados.feriado_em`; see `FERIADOS_MUNICIPAIS` in
  `app/core/feriados.py`.
- **Red no longer shows "waiting time" or "people waiting".** In an
  emergent (red) case the patient is seen immediately — showing a wait or
  a queue would be misleading, and the SESARAM site itself publishes no
  waiting time for the emergent colour. The hospital reference in red
  drops those two indicators (the action is still to call 112).
- **Blue now shows alternatives, like green.** In a non-urgent (blue)
  situation the main health centre (nearest / fastest to reach) is
  recommended, and an "Alternatives" section now lists the next two
  centres — previously only one was shown. On Porto Santo the island rule
  keeps only the local unit.
- **"SEISRAM" → "SESARAM" in the texts.** All mentions in comments, docs
  and copy now read SESARAM. The **real web addresses** of the
  waiting-times system (`web.sesaram.pt/SEISRAM_WBE_WEB/…`) are left
  untouched, because `SEISRAM_WBE_WEB` is the actual production path —
  changing it would break the link.
- **The 24-hour question: "pee" → "urine" (PT).** "…difficulty
  controlling your pee or stools?" becomes "…difficulty controlling your
  urine or stools?". Child-directed questions ("Has the child stopped
  weeing…") keep the everyday word.
- **Plain language leads on the complaints.** For several complaints the
  clinical term swaps place with the plain-language explanation: the bold
  title is now what the person recognises, with the technical term below.
  Head injury (T.C.E.) → **A blow or injury to the head**; Eye problems →
  **A problem with the eyes or vision**; Palpitations → **A feeling of
  fast or irregular heartbeats**; Gastrointestinal bleeding → **Blood in
  vomit or stools**; Major trauma → **A serious accident or injury**;
  Rashes → **Spots, bumps or a rash on the skin**. And "Unwell newborn
  (< 28 days)" keeps its label, while the Portuguese title expands "RN"
  to "Recém-nascido". Flowcharts and the clinical-validation document
  were regenerated.
- **Cleaner frontend.** The travel-time methodology note ("simplified
  network" / "local table in the app") was removed from the screen: it
  added nothing for the patient and the detail stays documented for
  reviewers. The route chips ("est." / "recorded") keep the useful
  context.
- **Expanded synonym dictionary.** Free-text search gained many more
  everyday terms (and English equivalents) per complaint, keeping the
  same keys (`app/data/sinonimos.json`).

As always, these texts and clinical defaults are a proposal and need
review by a clinical team before any real use.

## v0.14.1 — plain-language questions for patients

A readability and flow pass on top of the Manchester model. The triage
logic (priorities and colours) is unchanged; what changes is how the
questions read and what the person sees on screen.

- **Questions rewritten in everyday language.** Every discriminator now
  carries a patient-facing wording (`texto_utente` / `texto_utente_en`)
  written to be understood by someone with little schooling, folding the
  old clinical description straight into the question. Jargon nobody
  recognises is translated into what the person actually notices — the
  NEWS score becomes symptom-based ("Do you feel very unwell or close to
  fainting?"), and transport levels A/B/C become plain wording ("taken by
  helicopter with medical care"). The official clinical wording
  (`texto` / `texto_en`) and the `descricao` are kept untouched in the
  rules, so the flowcharts and the clinical-validation document still
  show the exact Manchester questions — reviewers can read the official
  text at `/fluxogramas` without hunting for a separate source.
- **No colour during the questions.** The Manchester priority bar and
  colour were removed from the question screen; the colour is now shown
  only on the final result, so it doesn't steer the answers. The separate
  help text is gone too — its content moved into the question itself.
- **The upfront "emergency signs" page was removed.** Those signs were a
  hand-made example list and not a set of P1 discriminators shared across
  every flow, so the app now starts straight at complaint selection; each
  flow's own red (P1) discriminators are still asked first. The
  `/api/red-flags` endpoint stays available but is no longer surfaced.
- **Fairer "no positive discriminator" outcome.** Answering "no" to
  everything used to always give blue (P5). For flows whose least-urgent
  discriminator is already urgent, that was a clinically odd drop. The
  outcome is now **one priority band below the least-urgent discriminator
  in the flow**, capped at blue: *Request for third parties* ends yellow
  (P3) instead of blue, *self-harm* and *major trauma* end green (P4);
  the other 53 flows (whose least-urgent discriminator is green) still end
  blue, exactly as before. The three affected flowcharts were regenerated.

As always, the patient wording and these clinical defaults are a
proposal and need review by a clinical team before any real use.

## v0.14.0 — Manchester discriminators (discriminator-based triage engine)

The biggest clinical-model change so far. The eight hand-made example
flows were replaced by the real **Manchester Triage System
discriminators**, imported from the official reference table
(flowchart, priority, discriminator and clinical description). The
triage engine moved from arbitrary decision trees to a
**discriminator-based model**, much closer to how Manchester actually
works.

- **Discriminator-based engine.** Each complaint is now a list of
  discriminators ordered by clinical priority (P1–P5). The engine asks
  one yes/no question per discriminator, from the highest priority
  down: the **first "yes" decides the colour** and ends the triage; if
  every answer is "no", the outcome is **blue** (the table's "no
  positive discriminator"). This replaces the `sim`/`nao` → `proxima`
  tree walk. Priority maps to colour canonically: P1 red, P2 orange,
  P3 yellow, P4 green, P5 blue.
- **56 flowcharts, 1187 discriminators.** Up from 7 example complaints.
  Adult and paediatric flows, marked with a `pediatrico` flag. Each
  discriminator keeps its official numeric id (`disc_id`) for future
  audits and cross-referencing.
- **Clinical descriptions shown to patients.** The reference table's
  description column (the clinical explanation of each discriminator)
  is imported into each discriminator's `descricao` and shown as the
  question's help text, so the user understands what is being asked.
- **Reproducible import.** New `scripts/importar_manchester.py`
  regenerates `app/data/rules/*.json` from the source table (kept in
  `docs/manchester/`), with a curated PT→EN dictionary for the 186
  unique discriminator texts and the 56 flow names. Re-runnable.
- **Priority indicator in the UI.** The old three-phase progress dots
  were replaced by a five-segment Manchester priority bar that shows,
  in the matching colour, which priority level is currently being
  assessed.
- **Simpler, stricter validation.** The startup validator no longer
  checks for cycles/unreachable questions (impossible in a flat list);
  it now checks that every discriminator has a valid priority, a colour
  matching that priority, non-empty text, and that discriminators are
  ordered from P1 to P5. New Mermaid rendering draws the linear
  discriminator sequence. Rules stay editable JSON, outside the code.
- **Not yet clinically validated.** The discriminators come verbatim
  from the reference table and still require clinical validation before
  real use — the validation document (`scripts/gerar_validacao_clinica.py`)
  was updated to the new model for exactly that review. Discriminator
  descriptions are Portuguese-only for now (the interface stays fully
  bilingual and falls back to Portuguese for that clinical text).

## v0.13.1 — explainability, logging and consolidation

A consolidation release, guided by an external code-review: no new
clinical features, but the prototype now explains itself — to patients,
to clinicians and to whoever reads the repository.

- **Explainability ("Why this recommendation?").** Every
  `/api/encaminhamento` response now carries `motivos`: the ordered,
  bilingual list of factors behind the decision — estimated colour,
  the policy applied (and its source: configuration, flowchart outcome
  or safe fallback), whether the unit is open, estimated travel time,
  the current waiting time, the experimental swap rule when it acted,
  and the island rule on Porto Santo. The interface shows the list in
  an expandable block on the recommendation card, so a clinician can
  audit the decision without reading code. New module
  `app/core/motivos.py`; the decision logic itself did not change.
- **`routing.py` split (single responsibility).** The user-facing
  phrases (opening times in English, "opens Monday at 08:00", arrival
  texts, day context) moved to `app/core/routing_textos.py`; routing
  now only decides, `routing_textos` words it, `motivos` explains it.
  All the old names remain importable from `routing`
  (`docs/adr/0010-divisao-routing.md`).
- **Application logging.** The app now uses the standard `logging`
  module: an INFO line at startup (version, flows and questions
  validated), WARNINGs when a waiting-times source fails or stale data
  is served, when OSRM falls back to the calibrated network, and when
  the configured reference hospital has no open emergency department in
  the data (the safe-fallback path of v0.12.1). Level adjustable with
  `ONDE_IR_LOG`. Logs never contain user data — no coordinates, no
  answers (`docs/adr/0011-logging.md`). The CLI scripts keep `print()`
  on purpose: their output is their interface.
- **Documentation reorganised (this file is part of it).** The version
  history left the READMEs and lives here; the data-editing guides
  moved to `docs/DATA_GUIDE.md` (PT: `docs/GUIA_DOS_DADOS.md`); the
  design decisions now also exist as one-page ADRs in `docs/adr/`; the
  validation status has its own checklist in `docs/VALIDATION.md`
  (PT: `docs/VALIDACAO.md`); and measured latency numbers live in
  `docs/PERFORMANCE.md`, produced by the new
  `scripts/benchmark_desempenho.py`. The READMEs became a short front
  door (what it is, how to run it, how it works, where everything
  lives) — roughly a quarter of the previous size.
- **Continuous integration.** A GitHub Actions workflow
  (`.github/workflows/ci.yml`) now runs the data validation, the
  translation audit and the full test suite with coverage on every
  push and pull request.
- **Tests: 282 (was 261), all passing** — the new ones pin the
  explainability of every branch, the log warning on the hospital
  fallback (and that it leaks no user location), the benchmark, and
  the shape of the reorganised documentation, so none of this can
  silently rot.

## v0.13.0 — an engineering release — Docker, architecture docs and measured coverage

No clinical logic changed in this version (rules, routing policy, unit
data and translations are exactly as in v0.12.1, and all 261 tests keep
passing). The whole release is about making the project easier to run,
evaluate and hand over:

- **Docker.** A `Dockerfile` (Python 3.12 slim, non-root user, health
  check on `/api/saude`) and a one-service `docker-compose.yml`. Anyone
  can now start the prototype with `docker compose up --build`, with no
  Python setup — useful for demos and for whoever picks the project up
  next. Running natively still works exactly as before.
- **Architecture documentation.** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
  (and [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) in Portuguese)
  explains the *why* behind the design: rules as data, validation at
  startup, statelessness and the deliberate absence of a database, the
  layered travel model, the scraping safety nets, the degradation modes,
  and the criteria that would justify changing each decision. The README
  stays as the *how to use*; the architecture document is the *how to
  think about it*.
- **Measured test coverage.** `pytest-cov` joins the requirements and
  `scripts/cobertura_testes.py` measures coverage (currently **91%** over
  `app/`, with 261 tests), optionally generates a browsable HTML report,
  and — with `--atualizar-readme` — rewrites the badges at the top of
  both READMEs so they can never silently go stale.
- **A more informative front door.** Badges and *The project in numbers*
  at the top of both READMEs give the real dimensions of the prototype at
  a glance (flows, questions, units, parishes, measured road times,
  endpoints), each number coming from the actual data files.

## v0.12.1 — red, orange and yellow go straight to the hospital

The change came from the supervision meeting: SESARAM's guidance is that
every red and orange case, and (for now) every yellow, should be referred
directly to Hospital Dr. Nélio Mendonça — not to the nearest open
emergency point. Until this version, those colours considered any open
urgência (hospital or a health centre's 24 h urgent care).

- **A destination policy, kept in data.** The rule lives in
  `app/data/encaminhamento.json` (`hospital_id` plus the list of colours
  in `direto_para_hospital`), editable by the clinical team like
  everything else — no code changes. Removing a colour from the list
  restores the proximity behaviour (nearest open urgência, ordered by
  road time) for that colour. Every routing response now carries a
  `politica` block (`destino`, `fonte`, `aplicada`) so interfaces and
  integrations can explain the decision.
- **Red keeps 112 first.** The action for red is still "call 112"; what
  changes is the unit shown underneath, now the reference hospital (that
  is where the emergency services transport to) instead of the nearest
  urgência.
- **The valve for "certain yellows", ready to use.** A yellow outcome in
  `app/data/rules/*.json` may declare `"destino": "atendimento_urgente"`,
  and that specific outcome goes back to the nearest open urgent-care
  point (with the v0.11 road-time ordering and the experimental
  wait-time swap rule). The start-up validator only accepts the field on
  yellow outcomes and only with valid values, so a typo cannot silently
  change routing; the drawn flowcharts (validation document and the
  `/fluxogramas` preview) mark these outcomes with "(may go to urgent
  care)". No production rule uses it yet — it is there for when the
  clinical team says which yellows qualify.
- **Island rule untouched.** On Porto Santo nothing crosses the sea: all
  colours still point to the local unit, with the transfer note for the
  serious ones.
- **Safe fallback.** If the configured hospital id does not exist in the
  data or has no open emergency service (a data error), the app falls
  back to the nearest open urgência instead of sending anyone to a
  closed door, and flags it (`politica.recuo`).

27 new tests cover the policy from several concelhos, the `politica`
block, the colour-specific waiting time at the hospital, Porto Santo,
the yellow exception (including the Curral das Freiras road-time case),
the start-up validation, the API round trip (`destino` accepted by
`/api/encaminhamento` and propagated by `/api/integracao/triagem`), the
flowchart marker, and these README links. Total: 261.

## v0.12 — offline flowcharts everywhere, and a live preview

The trigger was a regression: the flowcharts had stopped appearing in
`docs/validacao_clinica.html`. The cause was the drawing library being
fetched from a public CDN (`unpkg.com`) at open time, behind a silent
`if (window.mermaid)` guard — when the CDN was slow or down (it was
repeatedly, through 2025–2026), the library never loaded and the trees
simply vanished, with no error to explain why. This version removes that
dependency, makes any failure visible, and adds a way to watch the trees
update as you edit the rules.

- **Self-contained validation document.** The Mermaid library (MIT) is
  now **embedded in the generated HTML** (`static/vendor/mermaid.min.js`,
  vendored). `docs/validacao_clinica.html` draws its flowcharts offline
  and can be emailed as a single file — no network, no CDN. If a diagram
  can't be drawn (say, after a rule edit introduces an error), the
  document now prints the error in place, with the Mermaid source right
  below, instead of hiding it.
- **A live preview at `/fluxogramas`** (with the server running, open
  http://127.0.0.1:8000/fluxogramas). A new internal page (not linked
  from the patient interface — it's a tool for whoever edits and
  validates rules) shows every flowchart drawn from the current
  `app/data/rules/*.json`. Edit a rule, save, and the tree redraws:
  `GET /api/fluxogramas` **re-reads and re-validates the rules from disk
  on every request**, so there's no server restart. It auto-refreshes
  every 5 s (toggleable), offers a PT/EN switch, has a "copy Mermaid
  source" button per tree (paste into mermaid.live to edit visually),
  and if a rule file is invalid it shows the validation message verbatim
  while keeping the last valid trees on screen.
- **Bilingual flowcharts.** The trees now render in English too, from
  the `*_en` fields already in the rules, with a deliberate fall-back to
  Portuguese where a translation is missing (a half-translated tree is
  useful and flags the gap; a tree full of holes isn't). Outcome boxes
  use the colour's English name (RED, ORANGE…); the internal style
  classes stay in Portuguese.
- **No CDN in the app either.** Leaflet (the map) and the QR generator
  were also loading from `unpkg.com`; both are now vendored under
  `static/vendor/` and served locally. At runtime the app makes no
  third-party script requests at all. The only external resources that
  remain are the map tiles (CARTO) and Google Fonts, both with graceful
  degradation if unavailable — the app stays usable offline, just with
  system fonts and no basemap.
- **Updating the vendored libraries.** They're plain files under
  `static/vendor/`; to bump a version, replace the file (e.g.
  `npm pack mermaid@<version>` and copy `dist/mermaid.min.js`), keep the
  matching `LICENSE`, and update `VERSAO_MERMAID` in
  `scripts/gerar_validacao_clinica.py` (a test checks the two agree).

19 new tests cover the vendored libraries (self-contained bundle, no CDN
in `index.html`), the document embedding the library and one drawable
block per flowchart, the disk-backed `.mmd` files matching the current
rules, the English translation and its Portuguese fall-back, and the
live-preview API (all flows, EN, invalid-language 422, fresh read per
request, readable validation error) and page. Total: 234.

## v0.11.3 — road times in a local table and waiting chips

The motivating case comes from v0.11.2: from Achada da Rocha (Gaula),
the local model misordered Camacha and Gaula. This version tackles it
with an explicit, removable stopgap, and tidies the results card along
the way.

- **A local road-time table (removable module).**
  `app/data/tempos_medidos.json` stores, per locality and per parish,
  the driving time and distance to the relevant units (the hospital and
  the nearest health centres). When the patient is within
  `raio_ancoragem_km` (3 km) of a registered area, with no terrain
  barrier in between, the app uses that value, adjusted for the offset
  to the anchor; otherwise it falls back to the calibrated network.
  Priority: live OSRM (if configured) > table > network.
- **Two ways to fill the table, and they can coexist.** The recommended
  one is automatic: `python scripts/calcular_tempos_medidos.py --motor
  ors --chave YOUR_KEY` requests routes in batches from a routing
  engine (OpenRouteService, free key, or your own OSRM server with
  `--motor osrm`) and fills all 598 pairs in about a minute, stamping
  `fonte` and `calculado_em` on each pair. It saves after every batch:
  interrupting and resuming is safe, and filled pairs are never
  re-requested. The manual path remains:
  `python scripts/tempos_medidos_relatorio.py --links` produces
  ready-to-open Google Maps links, useful to double-check or correct
  suspicious pairs, and `--divergencias` lists where the table and the
  network disagree most. `python scripts/atualizar_tempos_medidos.py`
  rebuilds the scaffold after editing the localities without losing
  filled values; with `--todos`, destinations become every unit on the
  island (more pairs, meant for automatic filling).
- **How to remove the stopgap:** delete `app/data/tempos_medidos.json`
  (or set `VIAGEM_TEMPOS_MEDIDOS=0`) and the app falls back to the
  calibrated network on its own; `app/core/tempos_medidos.py` and the
  three scripts can be deleted too, nothing else depends on them. In
  production, the right path is still a routing service (see
  `docs/INTEGRACAO.md`).
- **Honesty about quality.** OpenRouteService and OSRM use
  OpenStreetMap with generic speed profiles and no traffic: for Madeira
  they give far better times than the local model, but below Google
  Maps. That is why the on-screen transparency note changes when the
  method is "medido", each pair records its `fonte`, and
  `GET /api/viagem?unidade=<id>` exposes the method for inspection.
- **Waiting chips on the card.** The sentence "Wait for your colour:
  ~35 min · 12 people waiting" gave way to two amber chips (clock and
  people) on the same row as the distance and time chips; when the wait
  is for the patient's own colour, the chip carries a "your colour"
  note.
- **Road distance on the chip.** When the table answers, the distance
  chip shows kilometres by road (note "by road") instead of the
  straight line, and the time chip swaps "est." for "recorded".
- **Alternatives with mini chips.** Each alternative shows the
  municipality and a row of mini chips (distance, driving time, open or
  closed, wait), more readable than the running sentence and one visual
  step below the main card; the reopening time sits on its own discreet
  line.
- **"Change location" became a mini button** — a pill, more obviously an
  action than the old underlined link.

33 new tests cover the data file and the scaffold generator, the
anchor-based lookup (radius, offset, barriers, kill switches), the
OSRM > table > network priority, the routing flow and `/api/viagem`,
and the filler script against a simulated engine (tests make no network
requests). Total: 215.

## v0.11.2 — cleaner copy and distance/time chips

A small polish release. No routing logic changed; the 170 previous tests
still pass and 12 new ones guard the changes below.

- **No dashes anywhere the patient can see.** Every em/en dash in
  interface strings was rewritten with commas, colons or full stops:
  `textos.js`, the self-care advice (`autocuidado.json`), the swap
  messages in `routing.py`, the backend travel-time note (`viagem.py`)
  and the clinical PDF titles. A regression test sweeps `textos.js`, the
  data files and a real `/api/encaminhamento` response (PT and EN) and
  fails on any dash that sneaks back in.
- **Simpler manual-location labels.** "Freguesia (se souber)" is now just
  "Freguesia" (and "Sítio ou zona"); the first option in each list is
  already "Não sei", so the parenthesis was redundant. The intro text of
  the "Where are you?" screen was rewritten in the same spirit.
- **Opening hours read as prose.** Unit schedule *texts* went from
  "08:00-20:00" to "das 08:00 às 20:00" (the machine-readable `horas`
  fields are untouched). The English translator `_horario_en` learned the
  new wording ("Weekdays, 08:00 to 20:00").
- **Distance and drive time became chips.** On each unit card they left
  the running meta line ("Health centre, Santa Cruz, 1.7 km · ~7 min…")
  and are now two distinct pills under the header, with small inline
  icons (pin and car) and a light blue tone that matches the open/closed
  badge language. Without a road estimate, the distance chip carries the
  old "straight line" note.
- **Production paths for real travel times documented.** The prototype's
  local model can mis-order two nearby units (from Achada da Rocha it
  narrowly prefers Camacha over Gaula; drivers know better).
  `docs/INTEGRACAO.md` now spells out the three ways to fix this for
  real: self-hosted OSRM for a pilot (already supported via
  `VIAGEM_OSRM_URL`), a **paid routing API (Google Routes API or
  equivalent) as the recommended production option**, with the mandatory
  GDPR/DPO assessment, and a local road-time table as a stopgap (implemented in v0.11.3).

## v0.11.1 — a finer manual location (parish and locality)

**Why.** When automatic location fails or is wrong, the app used to let
the user pick only the **municipality** — and it borrowed the
coordinates of the first health unit there. That is far too coarse:
someone in Camacha or Caniço who picks "Santa Cruz" lands on the town
centre, on the wrong side of the municipality. With the v0.11 road model
this now has a visible cost: from Camacha, the town-centre guess routes
to Santa Cruz's health centre (**~19 min**) when the Camacha one is
**~8 min** away.

**How.** A new editable data file, `app/data/localidades.json`, holds
the RAM as a tree of **municipality → parish → locality** (11
municipalities, 53 parishes, 145 localities), with coordinates the
intern collected and verified; municipality centres are the town
centres, consistent with `rede_viagem.json`. The "Where are you?" screen
(`GET /api/localidades`) offers three native dropdowns in cascade: pick
the municipality, optionally the parish, optionally the locality — names
people know by heart, no map to pinch, no GPS. Picking just the
municipality still works exactly as before ("Not sure" on the other
two), so nothing is lost. As with the flowcharts and the road network,
it is **data, not code**: `app/core/localidades.py` validates it at
startup (unique ids, every point inside the right island's box and
consistent with the travel network, every parish with a way to be
located) and emits **soft warnings** for human eyes — a locality more
than 12 km from its municipality centre, near-duplicates, or entries
still to be confirmed. `python scripts/validar_dados.py` runs the same
checks. Each level exposes a computed `centro` (a parish with no
coordinates of its own uses the centroid of its localities); the picker
resolves to the most specific level chosen and still keeps everything
on-device.

**Data-quality notes (for the team to confirm).** Some parishes currently
appear without associated localities because it was not possible to obtain
complete and reliable information from publicly available sources. There is
no single official source listing every locality in every parish of Madeira,
so the current dataset was compiled from parish council websites and other
available references. As a result, some localities may still be missing,
although all municipalities and parishes of the Autonomous Region of Madeira
are represented. Before deployment by SESARAM, the dataset should be
reviewed and completed to ensure that all localities are correctly
identified. This information is particularly useful when users do not allow
access to their location, as local residents can often describe where they
are using the names of well-known localities. For visitors or recent
residents who may not know these names, the application provides an
**"I don't know"** option for both parish and locality selection.

## v0.11 — driving times on a calibrated road network

**Why.** Until v0.10, "nearest" meant straight-line distance, and the
experimental switch rule added a real waiting time (scraped from
SESARAM) to a guessed travel time (straight line ÷ 50 km/h) — a
measurement plus a guess. In Madeira the straight line genuinely
misleads: Curral das Freiras has Funchal "next door" on the map with a
mountain in between, and the road to Câmara de Lobos passes the hospital
door. v0.11 replaces the guess with a road estimate — **without sending
anyone's location off the server and without runtime network calls**.

**How (three layers, in `app/core/viagem.py`).**
The default layer is a **calibrated road network**
(`app/data/rede_viagem.json`): ~16 reference points joined by the real
road corridors (VR1, VE3, VE4, ER101, …) with typical minutes, plus
terrain **barriers** (the Curral ridge, Pico Grande) that short
straight-line access hops may not cross. The time between any two points
is the shortest path on that graph (Dijkstra), with short local hops
estimated by a simple detour-factor model. Like the clinical flowcharts,
it is **editable data, not code** — anyone who knows the island can fix
a link's minutes; startup validation catches structural mistakes (also
run by `python scripts/validar_dados.py`). Optionally, setting the
`VIAGEM_OSRM_URL` environment variable to an **institution-hosted OSRM**
server switches to true routing (one `/table` request for all units),
with a short timeout, cache, failure cooldown and automatic fallback to
the network. It is **off by default**: using the public demo server
would send patient coordinates to a third party (GDPR) — a decision that
belongs to the institution, discussed in `docs/INTEGRACAO.md`.

**What changed in behaviour.**
Candidates are now ranked by **estimated driving time** (distance as the
tie-breaker), messages say "8.9 km, ~29 min by car", unit cards and
alternatives show the minutes, and the switch rule compares *real wait +
road travel*. Islands never mix: between Madeira and Porto Santo the
estimate is `None`. The response carries a `viagem_info` block and each
unit a `tempo_viagem` one (`{"minutos", "metodo": "rede"|"medido"|"osrm"}`; the "medido" method
also carries `distancia_km`, by road), and
`GET /api/viagem` exposes the estimator for inspection.

**Honest evaluation.** `python scripts/avaliar_viagem.py` compares both
methods against 16 reference journeys
(`app/data/percursos_referencia.json`, typical times, to be confirmed):
mean absolute error drops from **10.4 min (straight line) to 1.9 min**,
worst case from **24 to 5 min**. Editing the network's minutes and
re-running the script is the calibration loop.

## v0.10 — confirmed data, on-device history, and full English

- **Confirmed unit coordinates.** Several health-centre coordinates were
  confirmed and marked `dados_confirmados: true`; the remaining ones stay
  flagged `false`. (v0.10)
- **On-device history.** Past assessments are saved **only in the browser**
  (localStorage) — never sent to the server — so the patient can revisit
  what they answered and when, and delete it at any time. This keeps the
  "we store nothing" promise on the server side. (v0.10)
- **Self-correcting version badge.** The version shown in the header is read
  from the backend (`/api/saude`) at startup, so it can no longer go stale.
  (v0.10.1)
- **PDF opens in a visible tab.** The PDF button ("Open PDF") opens the
  document in a new tab, with a download fallback, so the result is visible
  instead of a silent download. (v0.10.1)
- **One-page PDF.** The guidance PDF was trimmed to the essentials (priority,
  recommendation, unit, warning signs, contacts) and now always fits a
  single page; the straight-line distance was removed from it. (v0.10.2)
- **Translation audit.** `python scripts/auditar_traducoes.py` reports any
  interface or clinical text missing its English version — detection, not
  machine translation (clinical text must be translated by a person).
  (v0.10.2)
- **Full English.** The six remaining clinical flowcharts were translated,
  and the backend-generated text (routing message, day name, unit opening
  hours) now has English versions too, so English mode no longer leaks
  Portuguese. (v0.10.3)

## v0.9 — PDF export and integration endpoint

**Guidance PDF.** On the result screen the patient can get a one-page
guidance summary as a PDF (priority colour, complaint, recommendation,
suggested unit with address/phone/opening hours, warning signs and
contacts). It is generated on the server with `reportlab` (pure Python,
installs with `pip` on any system, including Windows). The print button
remains available.

**Integration-ready.** Three endpoints aimed at external consumption (see
`docs/INTEGRACAO.md`): `POST /api/integracao/triagem` (triage + routing in a
single call), `POST /api/exportar_pdf` (PDF download) and
`POST /api/exportar_pdf_base64` (the same PDF in base64, for attaching).
`docs/INTEGRACAO.md` describes, neutrally, what is ready, the integration
potential, and the open questions to clarify with SESARAM's IT team about
the internal target platform.

## v0.8 — real-time waiting times

**Where they come from.** SESARAM publishes, in the SESARAM system, two
public pages with waiting times — one for Hospital Dr. Nélio Mendonça
(by clinical area and by the five Manchester classifications) and one
for the health centres with urgent care. The app reads both pages
(`app/core/espera.py`), recognises the two formats ("8m", "2h37",
"1h05 / 3", per-colour tables) and links each row to the project's units
via `app/data/espera_nomes.json`.

**What shows in the app.** The recommended unit and the open
alternatives display the estimated wait; for the hospital it's the wait
for the **user's colour** (an orange case sees the "Very Urgent" wait,
not the overall average). Above it: "SESARAM waiting times, updated at
HH:MM". When there's no data — no internet, site down, or outside the
covered units — the app says so and decides as before, by distance and
opening hours only. Endpoint: `GET /api/espera` (`?atualizar=true`
forces a fresh fetch, respecting the minimum interval).

**Experimental routing rule (pending validation).** For orange and
yellow, the app may suggest a slightly farther unit if that saves total
time (estimated travel + current wait). The safeguards are deliberately
conservative and sit at the top of `espera.py` to be tuned with the
clinical team: it only switches if it saves **≥ 30 minutes** and the
detour is **≤ 15 km**; it never switches without data on both sides; and
it **never** applies to red. When it switches, it explains why in the
message. This — like the triage rules — is marked as **pending
validation** and is included in the clinical validation document.

**Ethics and robustness.** There's a short-lived cache (the site is
never hammered: at most one request per interval, with an honest
User-Agent), negative caching (no insisting on a site that's down) and
reuse of the last valid data when a fetch fails. The site's courtesy
"NOTE" — which appears **even with data** — is never mistaken for
unavailability. **In the long run, the robust path is an official
SESARAM API**: if the institution provides one, swapping the page reader
for that access is simple and recommended.

**Install — note.** This version uses two new libraries (`requests` and
`beautifulsoup4`). After extracting the zip, run
`python -m pip install -r requirements.txt` once before starting the
server.

**Useful scripts.** `python scripts/testar_espera.py` (on your machine,
with internet) contacts SESARAM and shows what it read and what's still
unmapped; `python scripts/simular_espera.py` writes a demonstration
scenario so you can see the switch rule work without depending on the
site (ideal for the presentation).

## v0.7 — clinical flowcharts and navigation QR

**Automatic flowcharts in the validation document.** The Manchester
protocol is published as flowcharts — and the clinical validation
document now speaks that language: every complaint includes the drawn
tree, generated from `app/data/rules/*.json` by
`app/core/fluxogramas.py`, with outcomes painted in the five colours and
questions numbered as in the list. Jumps between questions, dead ends or
wrongly assigned colours become visible at a glance. Drawing happens in
the browser with the Mermaid library **embedded in the document itself**,
so it renders offline and can be emailed as a single file (this was
originally loaded from a CDN, which turned out to be unreliable and made
the flowcharts vanish silently — see *New in v0.12*). Each diagram's
source lives in `docs/fluxogramas/*.mmd` and can be opened and edited
visually at https://mermaid.live.

**Navigation QR on the result.** The recommended unit's card shows a QR
code with Google Maps directions: point your phone's camera and
navigation opens — useful when the assessment is done on a computer, and
it also prints. The code is generated locally (`qrcode-generator`
library, MIT), sending nothing anywhere; if the library fails to load,
the block simply does not appear.

## v0.6 — translation, search and care cards

**PT/EN button.** The top-right corner switches the interface language at
any moment without losing your answers (the choice is remembered by the
browser; opening with `?lang=en` also works). Clinical content is
translated file by file with optional `*_en` fields next to the
Portuguese ones — the **Fever** flow (`app/data/rules/febre.json`) is
complete and serves as the model; for the remaining flows the app shows
Portuguese until the fields are added. The longer routing messages remain
in Portuguese for now. All interface strings live in
`static/js/textos.js`.

**Free-text complaint search.** The complaint screen now has a "describe
what you feel" box — for example "my stomach hurts" suggests Abdominal
pain. No artificial intelligence: it uses the flow names plus the
editable dictionary `app/data/sinonimos.json` (accents and case are
ignored; Portuguese and English terms both work).
`scripts/validar_dados.py` checks every synonym points to an existing
flow. Endpoint: `GET /api/queixas/sugerir?q=…`.

**Care cards (NHS structure, our colours).** The self-care block for
green and blue became two cards with a coloured heading band — "what to
do" (tick list ✓), "what to avoid" (crosses ✕) and "Seek help if:" —
inspired by the English health service's care cards, while keeping the
five Manchester colours untouched. The texts live in
`app/data/autocuidado.json`, are checked by the validator and are
included in the clinical validation document.

## v0.5 — interface: the "public service" direction

The visual language follows Portuguese institutional portals: a solid blue
band at the top and bottom, white surfaces with outlines (no shadows),
small-caps labels and a single type family (Public Sans). The result is
presented as a **referral slip** — a card with a spine in the triage
colour, designed to print well — and the map uses light tiles (CARTO over
OpenStreetMap data) with the recommended unit's marker in that same
colour. While data loads, animated skeletons replace "Loading…" (they turn
off automatically for users who request reduced motion).

The blues are deliberately provisional: once official SESARAM colours
exist, swap `--primaria` and `--primaria-escura` at the top of
`static/css/style.css`.
