# Onde ir? Patient guidance for Madeira (RAM) — prototype (SESARAM)

This repository is a working prototype for a hospital-side application that guides patients to the right point of care in the Autonomous Region of Madeira: it triages symptoms through simple yes/no questions, estimates a Manchester-style priority colour, and recommends the nearest suitable unit given the current time and opening hours. The user-facing text and the code comments are written in Portuguese, because the target users and the health service are Portuguese; even so, the architecture, the data-driven clinical rules and the routing logic make it a solid, reusable base — an excellent prototype to build a real service on.

*("Onde ir?" means "Where to go?". A Portuguese version of this document is available in `README.pt.md`.)*

Web application that helps a patient decide **which health unit in the
Autonomous Region of Madeira (RAM) they should go to**: it runs a
simplified triage through yes/no questions, estimates a priority colour
(inspired by the Manchester Triage System) and recommends the most suitable
nearby unit, taking opening hours into account.

## Important notices (read first)

1. **Clinical validation is mandatory.** The decision flows in
   `app/data/rules/` and the colour → service-type mapping in
   `app/core/routing.py` are **development examples**. Before any use with
   real patients, they must be reviewed and approved by the SESARAM clinical
   team. Note: the official Manchester Triage flowcharts are licensed
   (Grupo Português de Triagem); this is a simplified in-house version.
2. **Unit data to be confirmed.** In `app/data/unidades.json`, coordinates
   are approximate and addresses, phone numbers, services and opening hours
   are marked with `(CONFIRMAR)` and `"dados_confirmados": false`.
   Everything must be confirmed with SESARAM before any real use.
3. **Privacy (GDPR).** The application does not store any patient data:
   there is no database, no sessions and no logging of answers. Location is
   used only at the moment of calculation and never stored. Keep it this way.
4. The tool **does not replace** clinical assessment or the official triage
   performed at emergency departments; the disclaimer shown in the interface
   is mandatory.

## How to run

Requirements: Python 3.11 or newer.

The first time only, install the dependencies:

```bash
python -m pip install -r requirements.txt
```

Each time you want to start the server:

```bash
python -m uvicorn app.main:app --reload
```

`python -m uvicorn` is used (rather than `uvicorn` directly) so it works on
any system, including Windows, without depending on the PATH.

Then open in the browser:

- Application: http://127.0.0.1:8000
- Interactive API documentation: http://127.0.0.1:8000/docs

To **stop** the server: Ctrl+C in the terminal. After changing the code,
press **Ctrl+F5** in the browser (hard refresh, so it does not use the
cached version); the running version can be checked at
http://127.0.0.1:8000/api/saude.

Run the tests:

```bash
python -m pytest
```

Optional: to isolate this project's dependencies from the rest of the
system, you can create a virtual environment before installing, with
`python -m venv .venv` and then activate it (Windows: `.venv\Scripts\activate`;
macOS/Linux: `source .venv/bin/activate`).

## Project structure

```
onde-ir-sesaram/
├── app/
│   ├── main.py               # FastAPI application (API + static frontend)
│   ├── api/routes.py         # REST endpoints
│   ├── models/schemas.py     # request validation (Pydantic)
│   ├── core/
│   │   ├── triage_engine.py  # triage engine (reads the JSON rule files)
│   │   ├── fluxogramas.py    # rules → Mermaid flowcharts (PT/EN; v0.12)
│   │   ├── routing.py        # colour + location + time → destination
│   │   ├── horarios.py       # open/closed at a given moment
│   │   ├── feriados.py       # public holidays (national + RAM regional)
│   │   ├── geo.py            # Haversine distance
│   │   ├── viagem.py         # driving-time estimator (network + optional OSRM)
│   │   ├── tempos_medidos.py # local road-time table (removable; v0.11.3)
│   │   ├── localidades.py    # municipality → parish → locality (manual mode)
│   │   ├── unidades.py       # unit repository
│   │   └── cores.py          # Manchester colours and contacts
│   └── data/
│       ├── rules/            # 1 JSON file per complaint + red_flags.json
│       ├── rede_viagem.json  # calibrated road network (editable)
│       ├── tempos_medidos.json # recorded road times (editable; v0.11.3)
│       ├── localidades.json  # parishes and localities (editable)
│       └── unidades.json     # RAM health units
├── static/                   # frontend (HTML + CSS + plain JS)
│   ├── vendor/               # Mermaid, Leaflet, QR generator — no CDN (v0.12)
│   └── fluxogramas.html      # live flowchart preview (internal tool; v0.12)
└── tests/                    # pytest (engine, hours, routing, API)
```

## How it works (3 blocks)

1. **Triage** — the frontend first asks about emergency signs
   (`red_flags.json`): if any is selected → red and 112. Otherwise, the
   patient picks a complaint and answers yes/no questions. Questions are
   organised into 3 phases visible in the interface: (1) general questions,
   (2) specific questions, (3) severity assessment. The engine is
   *stateless*: the frontend resends all answers with each request and gets
   back the next question or the result.
2. **Colour** — the result has a colour (red, orange, yellow, green, blue)
   with a target observation time, shown as a wristband.
3. **Routing** — given the colour, the location and the time in Madeira,
   `routing.py` picks the nearest open unit with the right service. Example
   of why time matters: a green case at 3 a.m. should not be sent to a
   closed health centre; it gets SNS 24 + an emergency department as a
   fallback.

## Editing or adding triage rules

Each complaint is a file in `app/data/rules/`. Minimal format:

```json
{
  "id": "dor_garganta",
  "nome": "Dor de garganta",
  "descricao": "Dor ao engolir, garganta inflamada.",
  "fonte": "Who validated it and when",
  "perguntas": [
    {
      "id": "dg_q1",
      "texto": "Tem dificuldade em respirar ou em engolir a própria saliva?",
      "sim": { "resultado": { "cor": "laranja", "motivo": "..." } },
      "nao": { "resultado": { "cor": "verde", "motivo": "...", "nota": "..." } }
    }
  ]
}
```

(The content is kept in Portuguese because it is shown to Portuguese-speaking
patients. `sim`/`nao` mean yes/no, `cor` means colour.)

Format rules: each question has `sim` and `nao` branches; each branch either
points to another question (`{"proxima": "id"}`) or ends
(`{"resultado": {"cor": ...}}`). The server **validates everything at
startup** (unique ids, complete branches, valid colours, existing
references) and refuses to start with malformed rules. After changing rules,
run `python -m pytest` and add a test for each clinically important path
(see `tests/test_triage_engine.py`).

When in clinical doubt, always err **towards more** urgency.

## Editing units and opening hours

In `app/data/unidades.json`, each unit has a `servicos` (services) dictionary
whose values are opening hours in one of two formats:

```json
{ "tipo": "24h", "texto": "Urgência aberta 24 horas" }

{ "tipo": "semanal", "texto": "Dias úteis, 08:00-20:00",
  "horas": { "seg": ["08:00-20:00"], "ter": ["08:00-20:00"],
             "qua": ["08:00-20:00"], "qui": ["08:00-20:00"],
             "sex": ["08:00-20:00"], "sab": [], "dom": [] } }
```

(`tipo` = type, `semanal` = weekly, `horas` = hours; `seg…dom` are the days
Monday to Sunday.) Services recognised by routing: `urgencia_polivalente`,
`urgencia_basica`, `atendimento_urgente`, `consulta_aberta`. Known
limitation: time ranges cannot cross midnight; for "until midnight" use
`"08:00-23:59"`.

**Public holidays (new in v0.4).** On national holidays and the two RAM
regional holidays (1 July and 26 December), services with a `"semanal"`
schedule automatically count as **closed** — even if the holiday falls on a
weekday. If a service does open on a holiday, add the `"feriado"` key to the
`horas` dictionary, for example `"feriado": ["09:00-13:00"]`. `"24h"`
services are not affected.

How they are obtained (in `app/core/feriados.py`): **fixed-date** holidays
(New Year, 25 April, 1 July, Christmas, etc.) are defined in the program
itself; the **moving** ones that depend on Easter (Good Friday and Corpus
Christi) are **computed mathematically** from each year's Easter date. There
is no connection to an external calendar or the internet: it works for any
year and never needs manual updating. The resulting calendar can be checked
at `GET /api/feriados?ano=2026`. Deliberately not included: municipal
holidays (they vary by municipality) and discretionary days off (Carnival,
24 and 31 December) — confirm with SESARAM whether these affect opening
hours.

## Tools for non-programmers editing the data

After editing any JSON (rules or units), check everything with:

```bash
python scripts/validar_dados.py
```

It reports errors in plain language (malformed time ranges, coordinates
outside the RAM, invalid colours, questions in a loop…) and lists the units
that still have data to confirm, serving as a checklist for the data survey.

For the clinical validation session, generate the printable document:

```bash
python scripts/gerar_validacao_clinica.py
```

This creates `docs/validacao_clinica.html`, one complaint per page, with
numbered questions, the outcomes, and a signature/date block for the
professional who validates it. Corrections made on paper are then carried
into the JSON files (updating the `fonte` field with who validated and when).

## API (summary)

- `GET /api/saude` — health check
- `GET /api/queixas` — available complaints
- `GET /api/red-flags` — emergency signs
- `GET /api/fluxogramas?idioma=pt|en` — Mermaid flowcharts for the
  current rules, re-read from disk on each request (v0.12; backs the
  `/fluxogramas` live preview)
- `POST /api/triagem` — `{queixa, respostas}` or `{red_flags}` → question/result
- `GET /api/unidades` — all units
- `GET /api/unidades/proxima?lat&lng&servico&n` — nearest units
- `GET /api/viagem?lat&lng&lat_destino&lng_destino` — estimated driving
  time between two points (inspection; v0.11); with `&unidade=<id>`
  instead of destination coordinates, the local road-time table can
  answer (method "medido"; v0.11.3)
- `GET /api/localidades` — municipality → parish → locality tree for the
  manual location screen (v0.11.1)
- `GET /api/espera?atualizar=` — real-time waiting times (SEISRAM cache)
- `POST /api/encaminhamento` — `{cor, lat, lng}` → full recommendation;
  optionally accepts `quando` (ISO 8601) to simulate the calculation time
- `GET /api/contactos` — 112 and SNS 24
- `GET /api/feriados?ano=` — national + regional holidays used in the
  opening-hours logic

## Demonstration mode (simulated time)

To show that time matters during a presentation, open the application with
`?hora=...` in the URL (`hora` = time), for example:

```
http://127.0.0.1:8000/?hora=2026-06-29T03:00:00
```

Routing is then calculated as if it were 3 a.m.: a green case is no longer
sent to a closed health centre and is directed to the nearest open 24 h
urgent-care unit instead. A banner on screen indicates that the time is
simulated.

Two other moments that work well in a presentation (new in v0.4):

```
http://127.0.0.1:8000/?hora=2026-07-04T15:00:00   (Saturday afternoon)
http://127.0.0.1:8000/?hora=2026-07-01T15:00:00   (holiday: Madeira Day)
```

For a green case, the app explains that it is a Saturday/holiday, states
when the nearest health centre reopens, and presents the two options: wait
at home with SNS 24 support, or go to the open urgent-care unit.

## Interface (v0.5): the "public service" direction

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

## New in v0.6: translation, search and care cards

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

## New in v0.7: clinical flowcharts and navigation QR

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

## New in v0.8: real-time waiting times

**Where they come from.** SESARAM publishes, in the SEISRAM system, two
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

## New in v0.9: PDF export and integration endpoint

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

## New in v0.10: confirmed data, on-device history, and full English

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

## New in v0.11: driving times on a calibrated road network

**Why.** Until v0.10, "nearest" meant straight-line distance, and the
experimental switch rule added a real waiting time (scraped from
SEISRAM) to a guessed travel time (straight line ÷ 50 km/h) — a
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

## New in v0.11.1: a finer manual location (parish and locality)

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

## New in v0.11.2: cleaner copy and distance/time chips

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

## New in v0.11.3: road times in a local table and waiting chips

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

## New in v0.12: offline flowcharts everywhere, and a live preview

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
- **A live preview at `/fluxogramas`.** A new internal page (not linked
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

## Known limitations

- Outside the areas covered by the local table (v0.11.3), driving
  times come from a **simplified, hand-calibrated network** with
  typical values: no live traffic, no rush hour, and short local hops are
  approximated. They are estimates for ranking and expectation-setting,
  not navigation. The reference journeys and the network's minutes are
  pending confirmation by the team.
- The unit data still includes entries to be confirmed (see the notice at
  the top and the `"dados_confirmados"` field).
- The triage rules and advice texts are examples, not yet clinically
  validated.
- Automatic location, on a computer, is estimated from the internet
  connection and may be imprecise; the user can always correct it by
  choosing the municipality and, if known, the parish and locality
  (v0.11.1). The locality coordinates are the intern's, still pending the
  team's confirmation (see the `"pendentes"` and `"verificado"` fields in
  `app/data/localidades.json`).
