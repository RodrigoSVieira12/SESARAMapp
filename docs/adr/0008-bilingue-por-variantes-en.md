# 8. Bilingual through `_en` variants + an auditor

**Status:** Accepted · **Date:** v0.6 / v0.10 (recorded v0.13.1)

## Context

The service is Portuguese, but the interface must also work in English for
non-Portuguese speakers (residents, tourists). Two things need translating:
the fixed UI text, and the data-driven content (rule questions, advice,
routing messages). Translating clinical content by machine would be unsafe.

## Decision

Every translatable string carries a Portuguese value and an `_en` variant
alongside it — in the UI text file and in the data files — and the frontend
picks the `_en` when the language is English, falling back to Portuguese
when it is missing (the safe omission). Backend-generated messages follow
the same convention (`mensagem`/`mensagem_en`, and the `motivos` list).
`scripts/auditar_traducoes.py` walks every source and reports anything
untranslated, returning a non-zero exit code so CI can enforce it — but it
never translates anything itself.

## Consequences

- The fallback means a missing translation degrades to Portuguese, never
  to a blank or a key.
- Translation coverage is measurable and CI-enforceable.
- Clinical content is translated by a person, as it must be.
- Cost: two values to maintain per string; the auditor keeps them honest.

## When to revisit

Adding a third language would make the parallel-variants approach heavier;
at that point a proper message-catalogue (e.g. gettext/ICU) would be worth
it. For two languages, variants + auditor are simpler and sufficient.
