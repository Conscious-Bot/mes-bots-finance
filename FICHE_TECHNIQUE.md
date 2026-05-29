# HEIMDALL Sentinelle (mes-bots-finance) — Fiche Technique (Lean)

**Version**: 29 mai 2026 (Day 24 — post Sprint 19 : adversarial co-pilot + boucle vivante + user_strategy)
**Auteur**: Olivier Legendre
**État**: High Standard / Observation jusqu'au 10/06/2026 (KPI #2 batch resolution)
**Bot**: Telegram @Hawk_Dove_bot

## Session 29/05/2026 — 53 commits

Refonte profonde du systeme d'aide a la decision :

### Architecture (sprints 5-19)
- **Sprint 5-6** : Note du portefeuille deterministe (6 dims) + Note PF panel + simulate_grade + injection copilot
- **Sprint 7** : Chat surface dashboard (RAG profil + grade + positions + theses + interventions)
- **Sprint 8** : /grade Telegram + backfill 41 pre_mortems
- **Sprint 9** : Chat persiste (chat_messages) + chat-driven trade execution + Layer 2 conceptions + Layer 3 preferences
- **Sprint 9.d** : Passive signal extraction (chat_extracted_signals)
- **Sprint 12** : Tagger sur 4 axes (driver/stage/moat/macro_factor) pour redefinir redondance et decorrelation
- **Sprint 13** : Trajectory grade + factor exposures + stress tests
- **Sprint 14** : SPOF graph upstream + Mauboussin implied sizing + valo > bull case
- **Sprint 15** : Kill-criteria monitor + alertes Telegram
- **Sprint 16** : PEA/CTO wrapper + tax-loss + FX exposure + alpha vs SOXX
- **Sprint 17** : Data-defined clusters par correlation rendements
- **Sprint 18** : Gates concentration + vraie Fragilite + remove old narrative panel
- **Sprint 19** : user_strategy declare (target 75%, benchmark SOXX, concentrator_thematic)
                + kill-criteria pre-alert + chat compound + auto-classification

### Glossaire canonique (FR clair) - 5 axes + 2 notes
- **Solidite** : Incontournable / Solide / Incertain / Fragile (ex T1+/T2/T3/T4)
- **Pari** : Pari principal / Autre pari (ex cluster_cap / decorrelation)
- **Doublon** : Solo / Doublon (driver+stage strict)
- **Sante** : Sain / Sous surveillance (verifie ticker_meta + review freshness)
- **Calibrage** : OK / Trop gros / Trop petit (vs cap conviction)
- Notes : **Construction** = Solidite + Pari + Calibrage / **Fragilite** = Sante + cycle/valo

---

## Mission

Système d'intelligence finance perso en boucle fermée self-learning (Telegram + Claude). **Mécanise la discipline** pour compenser deux biais asymétriques :
1. Vend les winners trop tôt (locking-in + mean-reversion) — historique PLTR @9, NVDA @130
2. Ne vend pas la crypto aux tops d'indicateurs (FOMO/greed)

Le bot **ne trade pas**. Il force la réflexion structurée pré-commit via thesis tracker bidirectionnel, calibration Brier, multi-round debate, /risk_check Opus, journal auto-résolu. Boucle : ingestion → process LLM → décision → prédiction (horizon mesurable) → outcome → rétrospection → enrichissement contexte → loop.

---

## Stack contraintes

- Python 3.14, SQLite **WAL mode**, APScheduler, embeddings BGE-small-en-v1.5 locaux
- Cascade Anthropic : Haiku (volume) / Sonnet (enrich) / Opus (raisonnement)
- Dashboard read-only : `dashboard/render.py` (static-gen → dashboard.html) + `dashboard/serve.py` (stdlib, 127.0.0.1:8000)
- **PAS** FastAPI / Postgres / Redis / LangGraph. Local MacBook Pro, pas de cloud.
- Coût observé : **~$15-20/mo** (budget $50)

---

## État empirique (29 mai 2026 — Day 24, post-session)

| Métrique | Valeur |
|---|---|
| Tests | **352** (Hypothesis + smoke, 100% pass) |
| Thèses actives | **28** (canoniques) — 13 archivees 'out_of_scope' (NVDA/MRVL/CEG/GEV/BWXT/...) |
| Positions tenues | **27** (sans VRT/TER fermees post-trades, avec SNOW nouveau) |
| Prédictions | 188 total, 8 décisions resolved encore 0 J+30 |
| Signaux | 291 cumulés |
| Univers canonique | **29 tickers** (1 source de verite via positions + scripts/canonical_perimeter.json) |
| Handlers Telegram | **73** (telemetry actif, top : /analyze 54, /brief 43, /digest 40) |
| Crons | **35** (incl. daily portfolio_grade 23h15, kill_criteria 07h30, weekly bot_conceptions Sun 19h, monthly bot_preferences 1er 04h) |
| ruff | 0 erreur |
| **Note PF** | **A+ 91/100** (post user_strategy : target cluster 75%, aucun gate actif) |
| Tables DB | 47 (incl. 11 nouvelles cette session : chat_messages, chat_extracted_signals, bot_conceptions, bot_preferences, ticker_axes, ticker_meta, kill_criteria_alerts, data_clusters_snapshots, portfolio_grades, portfolio_narrative_clusters, user_profile) |
| Migrations Alembic | 15 (0015 = data_clusters_snapshots) |
| Pages dashboard | **7** (vigie / positions / theses / **strategie** / concentration / signaux / urgence) |
| Panels dashboard | 20 distincts |

### Strategie utilisateur declaree (config.yaml.user_strategy)
- archetype : `concentrator_thematic`
- target_cluster_cap_pct : 75 (vs default 35)
- target_decorrelation_pct : 15
- accepted_concentrated_factors : ["AI capex", "AI inference/compute demand"]
- benchmark_ticker : SOXX (vs ^SOX)
- thesis_horizon_years : 7

### Book actuel (29/05/2026, post-trades VRT/TER -> CCJ/SNOW)
- Cost basis : 43 091€
- Market value : 53 558€ (+24.3%)
- Wrapper : PEA 17% / CTO 83%
- Pari principal : AI capex 66.5% (vs cible 75% — at_or_below)
- Cycle/valo expose : 30% (>cible 20% : STMPA fade, 000660.KS fade, 6920.T fade+valo>bull, ALAB fade+valo>bull, COHR, AMD)
- Doublons strictes : MU↔SK Hynix (Memory cycle + HBM/DRAM IDM) — 2.5% du book
- Sante : 82.9% sains, 7 sous surveillance (fade ou valo>bull)

---

## Architecture (couches)

1. **SUBSTRATE** — schéma DB (33 tables), config.yaml, secrets
2. **INGESTION** — Gmail (max_results 50), EDGAR, FRED, yfinance, CoinGecko
3. **ENTONNOIR** — signal_type Haiku + materiality_v2 Sonnet chaîné + echo BGE
4. **SIGNAUX** — insider clusters, 8-K cat, crypto zones, debt-crisis monitor (15 indicateurs)
5. **SYNTHESIS** — multi-round debate, /analyze deep, /risk_check Opus (avec injection signaux newsletters)
6. **APPROPRIATION** — position book, journal auto-resolve, bias_tagger
7. **RESTITUTION** — /brief, /digest 2x/j, /kpi_status, /cost_trajectory
8. **OBSERVE (dashboard)** — HEIMDALL Sentinelle, lecture seule ; toute décision reste sur Telegram

**Passerelles uniques** : DB → shared/storage.py, LLM → shared/llm.py, Telegram → shared/notify.py, config → shared/config.py, prix → shared/prices.py (HARDCODED_FX_TO_EUR), display → shared/display.py.

**Avertissement schéma** : CONVENTIONS.md et KPI_DASHBOARD.md décrivent des colonnes périmées (claim_json, outcome_evaluated_at n'existent pas). Vérité = `sqlite3 data/bot.db ".schema <table>"`. predictions porte : resolved_at, final_price, return_pct, outcome, probability_at_creation, brier_score. theses → narratif via `notes` (`sector_thesis_id: <ID>`).

---

## Brier / track record — état honnête

probability_at_creation était un snapshot de crédibilité source (~0.5 sur 157/157) = Brier vide. Réparé le 23/05 (`estimate_probability` câblé dans insert_prediction), **effet sur id ≥ 158 uniquement** — aucune créée à ce jour. Les 157 prédictions legacy (dont le cluster du 10 juin) restent à 0.5 → résolveront en Brier vide-mais-vert. **NE PAS publier comme track record.** Vraie courbe à partir des id ≥ 158, exploitable ~fin juin.

---

## KPIs runtime

| KPI | Cible | État 23/05 |
|---|---|---|
| #1 uptime 30d | >95% | 99.9% ✅ |
| **#2 NON-NEG** ≥5 résolues/28d | ≥5 | 1 résolu, ~40-44 dues 10/06, J-18 ⏳ ON TRACK |
| #3 Brier <0.20 rolling 90d | <0.20 | N=1 🔍 insufficient (vrai mesure post id≥158) |
| #4 0 panic sell core | 0 | 0 ✅ |
| #5 décisions journalisées | 100% | forward-only depuis 21/05 (baseline reset) |
| #6 Pf vs SPY/QQQ/SMH | >-5pp | 🔍 INSUFFICIENT (need 365d) |

---

## Concentration

EXCESSIVE : cluster AI Compute ~80% du book (cap narratif advisory 30-35%, 6 lignes > 5%). Le bot signale en OVERWEIGHT advisory (ADR 008) ; trim/hold = décision opérateur (Olivier), pas une règle config.

---

## Path 5/6

**Path 5** (acquihire $200K-$1M, 18-24mo) ET/OU **Path 6** (Substack + prosumer subscription, 24-36mo).
Dim 1 solidification : avancée. Dim 2 track record : activée (KPI runtime + timer 10/06). Dim 3 dépersonnalisation : month 6+. Dim 4 public : Substack post-Brier mesurable (~fin juin+).

---

## Documents canoniques

| Fichier | Rôle |
|---|---|
| `docs/AGENT_HANDOFF.md` | Manuel de reprise pour agent IA (contrat de travail, structure, conventions) |
| `HANDOFF.md` | Log de session chronologique (lire le tail) |
| `SESSION_STATE.md` | Handoff session courte |
| `TODO.md` | Backlog actionnel courant |
| `PHILOSOPHY.md` | High Standard Mode + boucle |
| `CONVENTIONS.md` | Naming + structure + Lessons 1-41 |
| `docs/adrs/` | ADR 001-008 (registry décisions archi) |
| `docs/failure_modes.md` | FM-1 à FM-12 + runbooks |
| `dashboard/render.py` + `serve.py` | Couche OBSERVE |

---

## Principes directeurs

1. Le bot ne trade pas, il force la discipline pré-commit
2. Précision dans la mesure > surface monitorée
3. Cascade LLM : Haiku volume, Opus raisonnement
4. Bidirectionnel : anti-vend-trop-tôt ET anti-tient-trop-long
5. Matière empirique > construction (KPI #2 NON-NEG)
6. High Standard : tests + coût modélisé + observabilité avant feature
7. Pas de scope creep : stack contraint jusqu'à break explicite
8. Less surface > more discipline
9. Backup + versioning obligatoire
10. Track record > features

---

## Appropriation roadmap (cadre 14/05, échelle de mois)

Le bot instrumente des DÉCISIONS réelles ; sans positions réelles, les boucles bidirectionnelles n'ont rien à instrumenter. Staging psychologique, pas un toggle :
- **Phase 1** (~fin mai) : pré-conditions sécurité (FileVault, bot.db hors iCloud, restore test, risk.validate wired, paper_only vérifié)
- **Phase 2** (~mi-juin, post-10/06) : 2-3 quality compounders neutres (pas PLTR/NVDA/crypto)
- **Phase 3** (~juillet, post-30j Phase 2) : positions chargées, PLTR-equivalent en dernier
- **Phase 4** (~août-sept) : full portfolio + execute_real si retenu

Policy 2-week observation post-opening (Day 16) : pas d'action portfolio offensive avant J+14 d'une thèse. À encoder dans PHILOSOPHY.md + guardrail bot.

## MAJ 27/05/2026 — Dashboard cockpit (canonique)
Cockpit HTTP (dashboard/serve.py, http://127.0.0.1:8000/dashboard.html) : identite visuelle canonique -- palette par etat (rouge breche / ambre attention / vert sain / bleu donnee / ink valeur), metal sur readouts (technique --c) et titres chrome (silver dark / graphite frost, 46px). 3-leviers Taille / Cible / Stop distincts. Reference : CONVENTIONS.md.
Stock-only depuis 26/05 (axe crypto/biais #2 en pause). Prochain jalon : batch KPI #2 le 10/06.
