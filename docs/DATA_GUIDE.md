# Data guide — editing the rules, the units and the demo mode

Everything a data editor (ideally someone from the clinical team) needs
to change what the application does **without touching Python**: the
triage rules, the units and their opening hours, and the simulated-time
mode used in presentations. Moved here from the README in v0.13.1.
(Versão portuguesa: `GUIA_DOS_DADOS.md`.)

## Editing or adding triage rules

Each complaint is a file in `app/data/rules/`, in the Manchester
**discriminator** model (v0.14.0). Minimal format:

```json
{
  "id": "dor_de_garganta",
  "nome": "Dor de garganta",
  "nome_en": "Sore throat",
  "descricao": "Dor ou irritação na garganta.",
  "pediatrico": false,
  "fonte": "Manchester discriminators; pending validation",
  "perguntas": [
    {
      "id": "dor_de_garganta_p1_1234",
      "disc_id": 1234,
      "prioridade": "P1",
      "cor": "vermelho",
      "texto": "Compromisso da via aérea?",
      "texto_utente": "A respiração está muito difícil ou ruidosa, como se o ar não passasse bem pela garganta (a roncar ou a gorgolejar)?",
      "texto_en": "Airway compromise?",
      "texto_utente_en": "Is breathing very difficult or noisy, as if air can't pass properly through the throat (snoring or gurgling)?",
      "descricao": "Clinical explanation of the discriminator (used in the flowcharts; its content was folded into texto_utente)."
    },
    {
      "id": "dor_de_garganta_p3_5678",
      "disc_id": 5678,
      "prioridade": "P3",
      "cor": "amarelo",
      "texto": "Dor moderada?",
      "texto_utente": "Tem dores a sério, que o impedem de fazer algumas coisas do dia a dia?",
      "texto_en": "Moderate pain?",
      "texto_utente_en": "Do you have noticeable pain that stops you doing some everyday things?"
    }
  ]
}
```

(Clinical content is kept in Portuguese because it is shown to
Portuguese-speaking patients; `texto`/`texto_utente`/`descricao` fall back
to Portuguese when the `_en` field is missing. `cor` means colour,
`prioridade` means priority.)

Format rules: the `perguntas` list is a sequence of discriminators
**ordered by priority** (P1 → P5). Each has a `prioridade` (P1-P5), a
`cor` that must match the priority (P1 red, P2 orange, P3 yellow, P4
green, P5 blue) and a `texto`. The `texto` (and `texto_en`) is the
**official Manchester clinical** question — it is what the flowcharts and
the clinical-validation document show. The `texto_utente` (and
`texto_utente_en`) is the same question rewritten in **plain everyday
language**, with the description already folded in — it is what the
frontend shows the patient (falling back to `texto` if missing). The
`descricao` (the Manchester table's column H) is kept for clinical
reference. There are no `sim`/`nao` branches: the engine asks one question
per discriminator, from the highest priority down, and the **first "yes"
decides the colour**; if all are "no", the outcome sits **one band below
the least-urgent discriminator in the flow, capped at blue**. A yellow
(P3) discriminator may also declare `"destino": "atendimento_urgente"`
(the v0.12.1 referral exception).

### Patient-language questions (`perguntas_utente.json`)

Since v0.15.3, the lay rewrites of the questions live in
`app/data/perguntas_utente.json` — **this is the file the clinical team
edits**, without touching code or the Excel file (the same pattern as the
advice in v0.15.2). Each item is keyed by the exact clinical text of the
discriminator (whitespace collapsed to single spaces) and has:

- `pt` / `en`: the rewritten question shown to the patient in each
  language (`verificar_perguntas.py` requires the full pair);
- `validado`, `validado_por`, `validado_em` (YYYY-MM-DD): the per-item
  **clinical validation state**, which lives **only in this file** — the
  rules do not duplicate it, on purpose, because they are also edited by
  hand and the copy would drift.

After editing the **sentences**, apply them to the rules:

```
python scripts/aplicar_perguntas_utente.py
```

The script rebuilds only `texto_utente`/`texto_utente_en` across the
`rules/` files (the clinical `texto` is untouched), is idempotent and
only rewrites the files that changed. Marking items as **validated**
needs no apply step — the engine reads the state at startup — and the
easiest way is not to edit the JSON by hand at all:

```
python scripts/marcar_validado.py perguntas --listar --contem "chest"
python scripts/marcar_validado.py perguntas "Dor precordial?" --por "Dr. Example"
```

(The same CLI serves the advice — `marcar_validado.py aconselhamento
...` — and there it runs the apply step automatically to resync the
SHA-256.)

The policy here is **different** from the advice one, and is written in
the file itself (the `politica` field): for questions, falling back to
the official clinical text **is safe** — it is the validated Manchester
question. The rewrite is a readability layer, never a logic layer: the
priority and the colour always come from the official discriminator. That
is why `verificar_perguntas.py` (also in CI) requires **full coverage** —
a discriminator without a rewrite entry is an error, because the patient
would see the clinical text without anyone having decided that — and
catches out-of-sync rewrites, orphan keys and incomplete validations.
And, in production, the `ONDE_IR_APENAS_VALIDADO=1` gate makes the engine
**revert** not-yet-validated rewrites to the official clinical question
(never hide — hiding a question would change the triage).

The server **validates everything at startup** (unique ids, valid
priorities and colours, colour consistent with priority, priority order)
and refuses to start with malformed rules. Rule files can be regenerated
from the official table with
`python scripts/importar_manchester.py <table.xls> app/data/rules`.
After changing rules, run `python -m pytest` and add a test for each
clinically important path (see `tests/test_triage_engine.py`).

When in clinical doubt, always err **towards more** urgency.

## Patient advice ("What you can do")

The file `app/data/aconselhamento.json` holds the practical advice shown
on the result screen, organised by flow and by colour (v0.15.0). Format:

```json
{
  "descricao": "...",
  "fluxos": {
    "dor_toracica": {
      "vermelho": {
        "itens": [
          {
            "texto": "Não reativo e não respira: iniciar T-CPR",
            "texto_utente": "Se a pessoa não acorda e não respira, ligue já para o 112 e não desligue: ao telefone ensinam-no a fazer compressões no peito.",
            "texto_utente_en": "If the person does not wake up and is not breathing, call 112 right away and stay on the line: they will guide you through chest compressions."
          }
        ]
      }
    }
  }
}
```

Each item has `texto` (the **clinical** advice exactly as in the
Manchester table, for the professional and for API integrators) and, where
a safe lay version exists, `texto_utente` (the same idea in **plain,
everyday language**) together with its English variant `texto_utente_en`
(v0.15.1), which the app picks when the interface is in English. The items
of each (flow, colour) are deduplicated, in first-appearance order in the
table.

**Safety policy (important).** Unlike the questions, the frontend does
**not** fall back to the clinical `texto`: it only shows the patient items
that have a `texto_utente`. Advice that is professional-only (assessing
clinical scales, contact isolation, dispatching resources, drugs by name,
calling the poison centre, sending the police...) is deliberately left
**without** a `texto_utente` and never reaches the patient — showing raw
clinical instructions to a layperson can be unsafe. Where the layperson's
action differs from the professional's, the safe at-home action is written
(for example, for a deformed limb, "do not try to straighten the limb,
keep it still", not "align the limb").

The plain-language rewrites live in
`app/data/aconselhamento_utente.json` (v0.15.2) — **this is the file the
clinical team edits**, without touching code. Each item is keyed by the
exact clinical text (whitespace collapsed) and carries:

- `pt` / `en`: the sentence shown to the patient in each language
  (`verificar_aconselhamento.py` requires the complete pair);
- `validado`, `validado_por`, `validado_em` (YYYY-MM-DD): the per-item
  **clinical validation state**. While `validado` is `false` the sentence
  counts as a proposal; setting it to `true` requires filling in who and
  when.

After editing (fixing a sentence, marking an item as validated), apply it
to the data **without needing the Excel file**:

```
python scripts/aplicar_aconselhamento_utente.py
```

(To mark validations, the shortcut is `python scripts/marcar_validado.py
aconselhamento "<clinical text>" --por "Name"` — it writes the three
fields and runs the apply step automatically; v0.15.3.)

The script rebuilds only the patient layer of `aconselhamento.json` (the
clinical `texto` is untouched), is idempotent, and records the SHA-256 of
the editable file under `fonte.reescritas` — if someone edits the
rewrites and forgets to run it, the verifier fails CI with instructions.
`aconselhamento.json` is therefore a **generated** file: do not edit it by
hand (the verifier catches that too). The `fonte.tabela` block records
exactly which Excel the advice came from (name, SHA-256, date, row count)
and is filled in by `scripts/importar_aconselhamento.py <table.xls>`
whenever the source table itself changes; the importer prints the coverage
(how many items already have a patient version) and the list of items
still without one, by frequency, to guide anyone extending coverage. Like
the self-care advice, these sentences (in both languages) **await
clinical validation** before real use — and, in production, setting
`ONDE_IR_APENAS_VALIDADO=1` in the environment makes the engine hide from
the patient everything not yet `validado` (the clinical text still goes to
integrators).

### Review view (`/revisao`)

Whoever reviewed the patient screen could not see what the safety filter
hides — and so could not easily confirm the filter is right. The internal
page `/revisao` (v0.15.2) shows, per flow and colour, the clinical advice
side by side with the PT/EN rewrite, each item's validation state and, in
grey, the items **hidden from the patient**; it has filters (hidden only,
pending only, search) and re-reads the data from disk on each refresh
(`GET /api/aconselhamento/revisao`). Since v0.15.3 it has two sections:
**Advice** and **Questions** (`GET /api/perguntas/revisao`), the latter
showing the official clinical question side by side with the PT/EN
rewrite and each item's validation state — nothing is hidden for
questions, so the "hidden only" filter does not apply there. It is the
tool intended for the item-by-item clinical validation session.

### Self-care × advice: how they relate

There are two blocks of patient advice, with different roles, which can
appear on the same screen: **self-care** (`autocuidado.json`) is generic
per **colour** (green/blue) — what to do/avoid at home and the warning
signs — and appears on the routing screen; the **advice**
(`aconselhamento.json`) is specific to the assessed **flow and colour**,
comes from the Manchester table and appears on the result screen (and at
the end of the routing screen). The relationship is **not yet clinically
reconciled**: `verificar_aconselhamento.py` lists, as a WARNING, sentences
that are very similar across the two (same colour), so the clinical
review can decide whether the redundancy is desirable or one side should
yield — that decision is clinical and deliberately kept out of CI.

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
- `GET /api/espera?atualizar=` — real-time waiting times (SESARAM cache)
- `POST /api/encaminhamento` — `{cor, lat, lng}` → full recommendation
  (with the applied `politica` block); optionally accepts `quando`
  (ISO 8601) to simulate the calculation time and `destino` (v0.12.1,
  yellow only), coming from the flowchart outcome
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
