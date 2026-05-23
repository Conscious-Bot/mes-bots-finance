# HEIMDALL Sentinelle (mes-bots-finance) — Fiche Technique (Lean)

**Version**: 23 mai 2026 (Day 17 — post Brier root-fix + dashboard)
**Auteur**: Olivier Legendre
**État**: High Standard / Observation jusqu'au 10/06/2026 (KPI #2 batch resolution)
**Bot**: Telegram @Hawk_Dove_bot

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

## État empirique (23 mai 2026)

| Métrique | Valeur |
|---|---|
| Tests | 345 (Hypothesis property-based + smoke) |
| Théses actives | 33 |
| Prédictions | 157 total (156 ouvertes, 1 résolue), max_id 157 |
| Cluster résolution | ~40-44 dues le 10 juin |
| Signaux | 208 cumulés (~66/30j) |
| Sources actives | ~52 (majorité à 0.5 crédibilité défaut, pré-10/06) |
| Univers | 313 tickers (23 core / 123 watch / 167 extended) |
| Handlers Telegram | 75 (telemetry actif) |
| Crons | 27 |
| ruff / mypy | 0 erreur (strict sur modules cœur, clean sur l'ensemble) |

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
