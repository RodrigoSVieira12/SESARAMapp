# Onde ir? Patient guidance for Madeira (RAM) — prototype (SESARAM)

*("Onde ir?" means "Where to go?". A Portuguese version of this document is
available in `README.md`.)*

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
│   │   ├── routing.py        # colour + location + time → destination
│   │   ├── horarios.py       # open/closed at a given moment
│   │   ├── feriados.py       # public holidays (national + RAM regional)
│   │   ├── geo.py            # Haversine distance
│   │   ├── unidades.py       # unit repository
│   │   └── cores.py          # Manchester colours and contacts
│   └── data/
│       ├── rules/            # 1 JSON file per complaint + red_flags.json
│       └── unidades.json     # RAM health units
├── static/                   # frontend (HTML + CSS + plain JS + Leaflet)
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
- `POST /api/triagem` — `{queixa, respostas}` or `{red_flags}` → question/result
- `GET /api/unidades` — all units
- `GET /api/unidades/proxima?lat&lng&servico&n` — nearest units
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
the browser (Mermaid library via CDN), so the document needs internet
when opened; without it, the numbered questions remain. Each diagram's
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

## Known limitations

- Distances are computed **in a straight line** (Haversine), not by road.
  In Madeira, given the terrain, the real driving distance can be
  considerably longer; for the prototype this is enough to rank units by
  proximity.
- The unit data still includes entries to be confirmed (see the notice at
  the top and the `"dados_confirmados"` field).
- The triage rules and advice texts are examples, not yet clinically
  validated.
- Automatic location, on a computer, is estimated from the internet
  connection and may be imprecise; the user can always correct it by
  choosing the municipality.
