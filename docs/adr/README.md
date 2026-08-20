# Architecture Decision Records (ADRs)

Short, one-page records of the decisions that shaped this prototype, and
why. Each ADR captures the context, the decision, its consequences, and
what would justify revisiting it. They are deliberately terse: the fuller
narrative lives in [`../ARCHITECTURE.md`](../ARCHITECTURE.md); these exist
so a single decision can be cited, linked and reconsidered on its own.

Format inspired by Michael Nygard's ADRs. Numbers are stable and never
reused; a superseded ADR is kept and marked, not deleted.

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-regras-como-dados.md) | Clinical rules are data, not code | Accepted |
| [0002](0002-validacao-no-arranque.md) | Validate the data at startup (fail fast) | Accepted |
| [0003](0003-sem-base-de-dados.md) | Stateless and database-free | Accepted |
| [0004](0004-fastapi.md) | FastAPI as the web framework | Accepted |
| [0005](0005-scraping-com-rede-de-seguranca.md) | Waiting times by scraping, with a safety net | Accepted (provisional) |
| [0006](0006-viagem-em-camadas.md) | Travel time in layers, no hard external dependency | Accepted |
| [0007](0007-frontend-sem-framework.md) | Static frontend, no framework, local vendor | Accepted |
| [0008](0008-bilingue-por-variantes-en.md) | Bilingual through `_en` variants + an auditor | Accepted |
| [0009](0009-explicabilidade.md) | Every recommendation explains itself (`motivos`) | Accepted |
| [0010](0010-divisao-routing.md) | Split `routing.py` by responsibility | Accepted |
| [0011](0011-logging.md) | Application logging, never user data | Accepted |

*ADRs 0001–0008 record decisions made across v0.1–v0.13.0 and are written
down here in v0.13.1; 0009–0011 are the v0.13.1 decisions themselves.*
