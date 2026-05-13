# TODO — mes-bots-finance

**Last refresh**: 13 May 2026 (post Day 2 marathon + afternoon extension, ~12h cumulative)
**Mode actuel**: High Standard / Solidification — Path 5/6 strategic target

---

## ✅ CLOSED — Day 2 marathon + afternoon (14 items)

### P0 sweep (6/6)
- ✅ #1 Property-based tests Hypothesis (37 → 49 passing, math invariants locked)
- ✅ #2 Daily backup 04:00 + restore test + 14d rotation
- ✅ #3 Handler usage telemetry middleware + /handler_stats
- ✅ #3.5 SQLite WAL mode (concurrency dette critique)
- ✅ #4 Sources tier S/A/B empirical (docs/SOURCES.md v2)
- ✅ #5 Failure modes registry top 5 (docs/failure_modes.md)

### P1 dette (4/4)
- ✅ #1 last_signal_at NULL → insert_raw_signal atomic + backfill 27 sources
- ✅ #2 materiality_v2 coverage 16% → 100% (chained architecture)
- ✅ #3 SemiAnalysis 0 signaux → max_results 20→50, paid sub activé
- ✅ #4 Stratechery + Apollo dedup (signals reassigned, dups deleted)

### P2 ships (4/4)
- ✅ /kpi_status + weekly cron Sun 22:30 (Path 5/6 dimension 2 activated)
- ✅ Ship A — horizon diversification (catalyst=14, narrative=60, impact-narrowed)
- ✅ Ship B — CI minimal GitHub Actions (.github/workflows/ci.yml + requirements split)
- ✅ Ship C — /cost_trajectory + weekly cron Sun 22:00 (budget alerting vs $50/mo)

---

## 📊 État empirique actuel

- 66 signals ingérés, **100% materiality_v2 coverage** (vs 16% ce matin)
- 27 active sources avec timestamps valides (vs 9)
- 5 Tier S empirical: Adam Tooze, Chamath, Wall Street Rollup, Coin Metrics, SemiAnalysis
- 45 open predictions (cluster J+28 = 10 juin, ON TRACK pour KPI #2)
- Cost: $0.50/jour observé → **$15/mo projected (5% du budget $50)**
- Tests: **49/49 passing** Hypothesis property-based
- 49 handlers Telegram avec telemetry middleware
- 22 crons actifs (incluant backup 04:00 + 4 weekly summaries Sun)

---

## 🚧 P2 backlog restant

### Immédiat
- **PIT bitemporal ADR** (~2h) — architectural decision record pour credibility/materiality history
  - Track "value at time T" pour audit + backtest credibility ledger
  - Crucial pour Path 5/6 narrative (defensible evolution)
- Quick wins bundle (~1h):
  - ingest_gmail_job new_count over-reports (cosmetic stats fix)
  - docs/glossary.md stub
  - docs/data_lineage.mermaid diagram

### Court terme (~10h cumulé)
- Refactor bot/main.py 2428 LOC → bot/handlers/*.py split par domaine (4h, risk élevé)
- Type hints + ruff/mypy basics (4h)
- Docs restructure: REFERENCE_SCHEMA.md + HANDLERS_INDEX.md + PROCEDURES.md + runbooks/ (3h)

### Moyen terme (>30j)
- Universe gating policy in CONVENTIONS.md (1h)
- Onboarding "resuming after break" checklist (1h)
- Calibration plot Path 6 (à activer post J+60 quand Brier N≥10)
- FMP $14/mo activation (month 4-6 si track record justifie)

---

## ⏱ KPI timer actifs

| KPI | Cadence | Current | Status | Action si breach |
|---|---|---|---|---|
| **#2 NON-NEG** | Hebdo dim | 1 résolu, 40 due in 28d, forecast J+28: 41 | ⏳ ON TRACK | Stop 5j build |
| #3 Brier rolling 90d | Hebdo | N=0 (insufficient) | 🔍 NOT YET MEASURABLE | Alert si >0.25 |
| #4 Panic sells core | Mensuel 1er | 0 | ✅ GREEN | Pause + bias analysis |
| #5 Decisions journalisées | Mensuel | N/A (0 material decisions) | 🔍 | No new thesis si <90% |
| #6 TWR vs SPY/QQQ 12M | Mensuel | Not implemented | ⏸ | Revue strat trim. |

**Cible KPI #2 J+28 = 10 juin 2026**. Forecast naturel: ✅ satisfied par batch resolution.

---

## 🎯 Path 5/6 strategic position

### Dimension 1 — Technique solidification: **TERMINÉE pour now**
14 items shippés, 49 tests, 0 régression, audit-grade sur 6 axes critiques.

### Dimension 2 — Track record mesure: **ACTIVATED**
KPI monitoring runtime via /kpi_status + weekly auto-post. Timer J+28 actif depuis 13 mai.

### Dimension 3 — Dépersonnalisation: **NOT STARTED**
Reste templated prompts + profile-driven config. À démarrer month 6+.

### Dimension 4 — Positionnement public: **NOT STARTED**
Reste Substack/LinkedIn. À activer post J+90 quand Brier mesurable + 30+ resolutions.

---

## 🚨 P0.7 / P1 dettes découvertes session (déjà closed)

Tracking pour la mémoire, ne pas re-shipper :
- ✅ insert_raw_signal manquait last_signal_at update + IntegrityError handling
- ✅ Cluster temporel 45 predictions à horizon=30 (artefact bulk ingestion, fix shipped pour futures)
- ✅ /llm_costs existait déjà — séparé de /cost_trajectory (operational vs strategic)
- ✅ SQLite locking sur changements journal_mode (besoin de stop bot complet)



---

## 📋 ADRs (Architecture Decision Records)

- **ADR 001** — PIT Bitemporal Credibility Ledger (`docs/adrs/001-pit-bitemporal-credibility.md`)
  - Status: **Proposed** (13 mai 2026)
  - Decision: bitemporal append-only ledger pour credibility, materiality, half-life
  - Implementation: déferrée à juin (post KPI #2 satisfait OU 1er recal mensuel)
  - Path 5/6 value: backtest + calibration plot dynamique + drift detection


---

## DETTE decouverte session 13/05 (carry-forward)

### Phase B5 journal logging regression (cmd_position_buy/sell)

Detection ruff F811: cmd_position_buy + cmd_position_sell etaient definis 2x
(lines 1888 + 2830). Version active (later) est SIMPLIFIEE sans journal_mod
integration. Version riche Phase B5 etait dead code shadowed.

Impact empirique: /position_buy /position_sell ne loguent PAS dans decisions
table. Compromet KPI #5 (100% decisions journalisees).

Action: Phase B5 features supprimees avec dead code en Ship 1.5.
A re-integrer en session future. Priority P1, effort ~1h.
