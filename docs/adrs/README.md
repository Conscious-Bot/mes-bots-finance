# ADRs — Index

Catalogue chronologique des decisions d'architecture. **19 ADRs** au total, **4 numeros en collision** (005, 006, 007, 008) — heritage de plusieurs sessions ayant reutilise le meme entier. Resolution differee post-10/06 (cf. TO-RESOLVE en bas) ; en attendant, **citer par slug, pas par numero seul** pour eviter l'ambiguite.

## Convention de reference

| Recommande | A eviter |
|---|---|
| `ADR cluster-cap-grandfather` | `ADR 008` (3 candidats : cluster-cap-grandfather, llm-cascade-architecture, cluster-cap-shock-underwriting — ambigu) |
| `ADR 009 conviction-soft-tiers` | `ADR 009` (OK car unique, mais le slug reste robuste si renumerotation) |

Citer le slug rend les refs resistantes a un renumber futur et leve les collisions actuelles a la lecture.

## Catalogue chronologique

| # chrono | Date | Fichier | Statut | Titre |
|---|---|---|---|---|
| 01 | 2026-05-13 | `001-pit-bitemporal-credibility.md` | Proposed | Point-in-Time Bitemporal Credibility Ledger |
| 02 | 2026-05-14 | `005-schema-versioning-alembic.md` | — | Schema Versioning Strategy with Alembic |
| 03 | 2026-05-15 | `002-universe-scaling-strategy.md` | Proposed | Universe scaling strategy (vertical vs horizontal) |
| 04 | 2026-05-15 | `003-portfolio-targets-pit-multi-account.md` | Accepted | Portfolio Targets PIT Bitemporal Multi-Account |
| 05 | 2026-05-18 | `004-usd-canonical-migration.md` | — | USD canonical migration |
| 06 | 2026-05-18 | `006-process-discipline-r19-stack.md` | Accepted | Process Discipline: R19 v2-v5 Stack for Bash Shipping |
| 07 | 2026-05-18 | `007-bidirectional-thesis-tracker.md` | Accepted | Bidirectional Thesis Tracker: Core Behavioral Discipline Mechanism |
| 08 | 2026-05-18 | `008-llm-cascade-architecture.md` | Active | LLM Cascade Architecture (Haiku/Sonnet/Opus tier routing) |
| 09 | 2026-05-20 | `005-eur-canonical-positions.md` | Accepted | EUR-Canonical avg_cost Storage |
| 10 | 2026-05-20 | `006-debt-crisis-monitor.md` | Accepted | Debt Crisis Monitor (15-indicator phase-based tail-risk overlay) |
| 11 | 2026-05-21 | `007-briefs-ephemeral.md` | Accepted | Briefs ephemeral by design |
| 12 | 2026-05-21 | `008-cluster-cap-grandfather.md` | Accepted | Cluster cap 35% + position cap soft + grandfather strict |
| 13 | 2026-05-24 | `dashboard-design-system.md` | — | Dashboard design system (refonte propre) |
| 14 | 2026-05-25 | `006-target-partial-cible-only.md` | — | Profit-take : trigger cible-only, debranchement de target_partial |
| 15 | 2026-05-25 | `007-credibility-single-authority-brier.md` | Accepted | Credibilite source : autorite unique Brier |
| 16 | 2026-05-26 | `009-conviction-soft-tiers-and-brake.md` | Accepted | Alertes soft tierees par conviction + mecanique du frein (subordonne a cluster-cap-grandfather) |
| 17 | 2026-05-26 | `010-cluster-cap-shock-underwriting.md` | Accepted | Cap cluster = 35% (risk-adjusted via choc underwrite), config aligne |
| 18 | 2026-05-27 | `011-probability-at-creation-stale-read-fix.md` | Accepted | probability_at_creation: stale-read fix, fail-loud, backfill |
| 19 | 2026-05-30 | `012-deprecate-8k-severity-classifier.md` | Accepted | 8-K severity classifier soft-deprecated comme mesure d'evidence_strength (conserve pour alerting low-latency) |

## Collisions de numero (a resoudre)

| Numero | Fichiers en collision | Resolution probable |
|---|---|---|
| **005** | `005-schema-versioning-alembic` (14/05) · `005-eur-canonical-positions` (20/05) | alembic peu utilise (2 versions seulement) → garder eur-canonical-positions sous 005, renumeroter schema-versioning-alembic en libre |
| **006** | `006-process-discipline-r19-stack` (18/05) · `006-debt-crisis-monitor` (20/05) · `006-target-partial-cible-only` (25/05) | TBD au moment de la resolution |
| **007** | `007-bidirectional-thesis-tracker` (18/05) · `007-briefs-ephemeral` (21/05) · `007-credibility-single-authority-brier` (25/05) | TBD |
| **008** | `008-llm-cascade-architecture` (18/05) · `008-cluster-cap-grandfather` (21/05) | TBD — cluster-cap-grandfather est l'ADR le plus refere du repo, doit garder 008 |

## ADRs sans statut declare

- `004-usd-canonical-migration` · `005-schema-versioning-alembic` · `006-target-partial-cible-only` · `dashboard-design-system`

Ajouter `**Status**: <Proposed|Accepted|Superseded|Deprecated>` en tete de chaque pour leur prochain edit.

## TO-RESOLVE (post-10/06, hors freeze observation)

1. **Renumerotation chrono unique** des 4 collisions. Strategie : conserver le numero pour l'ADR le plus cite/recent ; renumeroter les autres en >= 012. Ne PAS toucher aux ADRs non-collidants (001-004, 009-011) — leurs refs (20+ fichiers `intelligence/`, `shared/`, `tests/`, markdowns racine) restent stables.
2. **Add `**Status**:` + `**Date**:`** sur les 4 ADRs sans header.
3. **`dashboard-design-system.md`** est hors-numerotation. Decider : lui attribuer un numero chrono (012) ou acter qu'il vit hors-serie (alors le renommer `meta-dashboard-design-system.md` pour le sortir du tri numerique).
4. **Ajouter convention au CONVENTIONS.md** : "tout nouvel ADR prend `git ls docs/adrs | sort -V | tail -1` + 1, jamais picke a la main".

Le risque de la renumerotation est de casser la memoire interne du user (qui sait "ADR-008 = cluster cap"). C'est pourquoi la convention "cite par slug" doit s'adopter AVANT le renumber, pour absorber la transition.
