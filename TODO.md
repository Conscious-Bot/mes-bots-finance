# TODO — mes-bots-finance

**Last refresh**: 14 May 2026 afternoon (post-recovery diagnostic + 3 commits dette clearance)
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


---

## Ship 1 closed (13 May 2026 ~3h, post afternoon extension)

**Type hints + ruff/mypy professional treatment**:
- ruff: 421 -> 0 errors (full sweep + auto-fix + manual cleanup)
- mypy: 0 errors on shared/{storage,llm,prices,notify,config,math_helpers}.py
- 7 real bugs discovered and fixed (F811 cmd_position_buy/sell, F811 get_or_create_source dead chain, F821 timezone, B005 lstrip x2, _resolve_model tuple, _compute_cost None return, prices.py tuple returns)
- 1 dette regression noted (Phase B5 journal logging in cmd_position_buy/sell)
- CI YAML extended with mypy gate
- CONVENTIONS.md updated with type hints policy

**Deferred to future sessions** (not blocking, gradual adoption):
- Ship 2: type hints intelligence/* (learning, materiality_v2, asymmetry, etc.) ~30 files
- Ship 3: type hints data_sources/* + bot/main.py key functions ~2428 LOC
- Ship 4: docs restructure (REFERENCE_SCHEMA, HANDLERS_INDEX, PROCEDURES, runbooks/)
- Ship 5: refactor bot/main.py into bot/handlers/* split

These deferred items have diminishing Path 5/6 marginal value vs observation time
(KPI #2 timer ticking until June 10 batch resolution). Recommended: incremental
type hint adoption as code is touched, not top-down sweep.


---

## Debt clearance complete (Ships 5-8, 13 May 2026 evening)

### Closed:
- ✅ **Phase B5 journal regression** (Ship 5) - KPI #5 fully functional now
- ✅ **Smoke test coverage gap** (Ship 6) - 12 new fail-fast tests
- ✅ **shared/edgar.py latent type errors** (Ship 7) - 8k_scan + insider crons protected
- ✅ **data_sources/gmail_.py untyped** (Ship 8) - ingestion entry point covered

### Status: OBSERVATION READY
- 14 modules strict-typed (ingestion -> scoring -> prediction -> restitution covered)
- 61/61 tests passing
- ruff/mypy gates active in CI YAML (12 modules)
- Bot vivant, all 22 crons scheduled

### Carry-forward (NOT urgent, gradual adoption):
- Type hints remaining ~25 modules (P3, incremental)
- Refactor bot/main.py 2428 LOC split (P3, architectural choice)
- ADR 001 PIT bitemporal implementation (P2, trigger = KPI #2 GREEN or 1st recal)
- User TODO: setup GitHub repo + push (CI gates only enforce locally until then)

### Observation rules (per docs/PROCEDURES.md):
- NO new features. NO new tickers. NO new sources.
- Daily /brief ritual. Weekly Sunday auto-summaries.
- June 10: KPI #2 batch resolution (45+ predictions due)
- If KPI #2 GREEN: trigger ADR 001 Phase 1 (PIT implementation)


---

## risk/ module status (clarified Phase 3, 13 May 2026)

**Status**: feature-ready, intentionally not yet wired into runtime.

Two modules ready for post-observation integration:
- `risk/risk_engine.py` :: `validate(decision)` - pre-trade guard
  - Drawdown stop/reduce gates (from cfg risk.drawdown_stop_pct)
  - Position size cap check (cfg style.position_max_pct)
  - Conviction minimum floor (cfg style.conviction_min)
  - paper_only block when execute_real requested
- `risk/sizing.py` :: `position_size(edge, variance, capital, regime_factor)` - Quarter Kelly + hard cap
  - 7 unit tests in tests/test_sizing.py (formula, edge cases, regime scaling)

### Integration plan post-J+28 (after observation period):

1. Wire `risk.validate()` into `cmd_position_buy` + `cmd_position_sell` BEFORE positions_mod.add_buy/sell call. Block with reason if validate().ok is False.
2. Add `/size_recommend TICKER edge variance` handler returning Quarter Kelly suggestion.
3. Expose ValidationResult.severity in journal logging.

### Why deferred:

Wiring during observation would risk:
- False blocks on legitimate paper trades during data accumulation
- Behavior change before KPI #2 baseline established
- Confounding any regression analysis

Observation principle: code freeze on behavior-affecting changes.


---

## CLOSED — Day 3 (14 May 2026, ~7h cumulative)

### Morning (Sprint 1.2 + 1.3 closeout, ~5h)
- Sprint 1.3 Alembic schema versioning + bootstrap + ADR-005 (commit 0e3a04d)
- Sprint 1.2 item 1: shared/data_source_base.py + 16 Hypothesis tests (304ff51)
- Sprint 1.2 item 2: GmailSource migration (73d17a3)
- Sprint 1.2 item 3: EightK + BuyCluster sources + edgar RateLimiter (980cddb / 195503e / ba2691e / 12d22a1)
- Sprint 1.2 items 4+6: docs/runbooks + docs/post-mortems + 5 ops runbooks (a134c59)
- Sprint 1.2 item 5 (ADRs 002/003/004 retroactifs): DEFERRED

### Afternoon (recovery diagnostic + cleanup, ~2h)
- **Postmortem 2026-05-14**: uptime_monitor case-sensitivity bug (b5e2fb4)
- **Doc drift fix**: dual backup paths in 3 docs (efa88d7)
- SESSION_STATE + TODO refresh (this commit)
- ~~Quick-win cost alert in `cost_trajectory` cron~~ — **already shipped Day 2 as Ship C** (line 1173 weekly_cost_summary_job at 90% threshold). Recon confirmed. No new code.

### Sprint 1.4 STATUS RESOLVED (no work shipped)
- **Was**: "Cost enforcement, ~10h, week 18-25 May" (initial scope)
- **Revised this morning**: replaced by quick-win (~30min)
- **Actual reality (confirmed by recon)**: **already shipped Day 2 afternoon as Ship C**.
  `weekly_cost_summary_job` cron + `_cost_compute_trajectory` engine already implement
  MTD + projection + 3-tier status + alert at 90% threshold.
- **Empirical state**: 7d cost = $1.16, projected $5/mo = 10% of $50/mo budget.
  Existing weekly check at 90% is sufficient for this consumption regime.
- **Process lesson**: I nearly re-shipped this. Grep SESSION_STATE/commit-log
  for named features BEFORE scoping a sprint. See meta-lesson in SESSION_STATE.

---

## KPI table (corrected post 2026-05-14)

| KPI | Cadence | Status | Action si breach |
|---|---|---|---|
| **#1 uptime > 95%** | Daily | detector fixed today; pre-fix data = noise | Real measurement starts 2026-05-14 12:26 KST |
| **#2 NON-NEG** >=5 resolved/28d | Hebdo dim | ON TRACK (45 due 10-11 juin) | Stop 5j build |
| **#3 Brier < 0.20 rolling 90d** | Hebdo | NOT YET MEASURABLE (N=1) | Alert si >0.25 post-N>=10 |
| **#4 0 panic sell core** | Mensuel 1er | GREEN | Pause + bias analysis |
| **#5 100% decisions journalisees** | Mensuel | N/A (0 material decisions 30d) | No new thesis si <90% |
| **#6 TWR vs SPY/QQQ 12M** | Trim. | not implemented | Revue strat. trim. si <-5pp |

**Cible KPI #2: 10 juin 2026, 45+ resolutions batch.**

---

## Open AIs from postmortem 2026-05-14

- AI #3 due 2026-05-21: `scripts/bot_health_check.sh` multi-signal alive check
- AI #4 due 2026-05-21: smoke test `pgrep -fi` regression guard
- AI #5 due 2026-05-15: purge or annotate uptime.log historical false negatives
- AI #6 due 2026-05-28: TZ standardization across logging components
- AI #7 P2: bot_state.json stale fields refresh
- AI #8 P0 process: CONVENTIONS.md detector-backed-KPI validation rule

These are NOT in this week's scope. They're listed here so they're not forgotten
when re-entering work post-J+28 (10 juin batch resolution).


---

## Tier 1+2 closed evening 14 May 2026 (db4bd43 + 26678e9)

### Closed
- Sprint 1.1 equivalence checkpoint scripts/sprint_1_1_checkpoint.py
- Sprint 1.7 unification candidates scaffold docs/sprint-1.7-unification-candidates.md
- Baseline chunk 0 baselines/sprint-1.1-chunk-0.json (98 funcs at 2158adf)
- AI #3 scripts/bot_health_check.sh + 5 regression tests (124 tests total)

### New P3 carry-forward
- KPI_DASHBOARD.md schema drift: KPI #9 references outcome_evaluated_at,
  actual schema has resolved_at. 15min fix. Second instance of doc drift
  after backups path Day 2 evening. Triggers §16 detector if 3rd case emerges.
- Predictions schema doc audit: grep project for any other outcome_evaluated_at
  refs. Defer to Sprint 1.1 Monday pre-flight as recon step.

### Status
- Observation mode active until 2026-06-10 (27d KPI #2 timer)
- 45 open predictions due 2026-06-10
- 124 tests passing, bot health GREEN
- Sprint 1.1 STRICT mode confirmed for Monday 2026-05-19

### AI #12 NEW (P3, post-J+28, 30-60min): Storage.py legacy dead code + alembic discipline gap

Discovered during P3 KPI doc drift investigation Day 3 evening (post 93e6f7d).

Findings:
1. shared/storage.py:126-175 contains 3 legacy functions (log_prediction, expired_unresolved_predictions, record_outcome) referencing columns absent from current predictions schema (expires_at, outcome_evaluated_at, actual_outcome_json, correct).
2. Zero external call sites confirmed via grep, pure dead code.
3. Active flow uses NEW functions insert_prediction/get_due_predictions/resolve_prediction_row (storage.py:634-689) via intelligence/learning.py auto_register_predictions and resolve_due_predictions.
4. alembic_version row = 0001 (baseline only) but actual schema differs from baseline. Migration discipline gap.

Action post-J+28: delete 3 legacy functions, decide alembic discipline (revive migrations OR document informal schema evolution + write current schema as new baseline).

Risk if not done: low. Dead code = cognitive overhead + slight attack surface (silent OperationalError on accidental call). Path 5/6 defensibility benefit from clean codebase.
