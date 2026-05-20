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


---

## Appropriation roadmap items (defined 14 May 2026 Day 3 close)

### Phase 1 pre-conditions (P0 once Sprint 1.1 closes, ~26 mai)
- [ ] FileVault enabled (Settings, Privacy and Security)
- [ ] Audit ~/mes-bots-finance NOT in iCloud Drive sync path
- [ ] Manual backup restore end-to-end test on data/bot.db
- [ ] Wire risk.validate() into cmd_position_buy / cmd_position_sell
- [ ] Verify paper_only toggle blocks all position writes when True

### Phase 2 trigger (~12-15 juin, post J+28 KPI #2 batch)
- [ ] Choose 2-3 quality compounder positions for first entry (no PLTR/NVDA/crypto)
- [ ] Pre-position backup + tag manual_pre_first_real_position_TIMESTAMP
- [ ] First /position_buy with real ticker + size + thesis text
- [ ] Note expected emotional response in VALUE_LOG.md
- [ ] 30d observation cycle compare expected vs actual

### Phase 3-4 (milestone-gated, post-July)
Trigger: 30d of Phase 2 with no panic sell on neutral positions
Then: introduce PLTR-equivalent positions one at a time

See FICHE_TECHNIQUE.md "Appropriation roadmap" section for full rationale.


---

## Thesis candidates queue (added 2026-05-15 Day 4 afternoon, post-conversation chokepoint analysis)

Source: conversation analytique chokepoints/AI waves avec autre IA, ~150 tickers cités, ~30 candidates serious. Voir docs/thesis-candidates-queue.md pour pipeline structuré.

### Pre-flight gates avant tout add to config.yaml

**Gate 0 — Observation window respected**: NO universe expansion before 2026-06-10 (KPI #2 batch resolution). Adding tickers during observation pollutes the calibration cohort.

**Gate 1 — Pure-play test**: ticker exposes >70% revenue/EBITDA to thesis driver. Conglomerates rejected (DD, BASF, Evonik diluted plays out).

**Gate 2 — Valuation discipline**: P/E or EV/EBITDA must be in the bottom 40% of comparable peer set OR have a falsifiable mispricing thesis. "Chokepoint exists" alone is insufficient — the chokepoint must not be priced.

**Gate 3 — Falsifiable invalidation on 6-12 months**: testable price/event/data triggers, not "narrative deteriorates."

**Gate 4 — Articulable mispricing**: explanation for why Mr Market is wrong must not rely solely on "narrative is undercovered."

### Candidates from 2026-05-15 conversation (max 5 to add post-J+28)

Priority A (strong pure-play + measurable valuation gap):
- **Kioxia (285A.T)** — NAND pure-play, IPO récente, comparison vs Micron testable
- **Mitsubishi Heavy Industries (7011.T)** — turbines + nuclear + defense, P/E ~half of GE Vernova
- **Stevanato (STVN)** — borosilicate vials for GLP-1, oligopole, falsifiable on demand/utilization metrics

Priority B (intéressant but qualification needed):
- **Ypsomed (YPSN.SW)** — auto-injector pens duopole
- **Lasertec (6920.T)** — EUV mask inspection monopole BUT verify multiple post-rally before adding
- **Ferrotec (6890.T)** — semi consumables, P/E ~12x

Priority C (watch only, NOT add to config.yaml):
- **DEME Group (DEME.BR)** — subsea cable vessels (geographic/political risk to assess)
- **NKT (NKT.CO)** — HV subsea cable
- **Momentive Technologies (MTUS)** — HPQ chokepoint hedge NVDA, but recent IPO + volatile + thesis depends on hyperscaler capex maintaining
- **Centrus Energy (LEU)** — HALEU pure-play, +5x déjà en 2024, sizing strict
- **MP Materials (MP)** — REE vertical, China dumping tail risk historiquement vérifié (Molycorp 2013-2016)

### Action items

- [P2 post-J+28] Apply Gates 1-4 to Priority A candidates with empirical valuation pull from yfinance/EDGAR
- [P2 post-J+28] Decision: add 0-3 candidates to config.yaml watch tier (NOT core)
- [P3] Document the analytical framework used (chokepoint scoring /30) as either valid or rejected with rationale
- [P3 ADR-002] Universe scaling strategy decision: vertical (depth, quality) vs horizontal (size). Currently 178 tickers, 1 thesis, 45 predictions all clustered J+28. Universal expansion (1000+ tickers) violates PHILOSOPHY High Standard Mode unless justified by track record evidence post-J+28.

### What NOT to add to TODO

The conversation produced ~150 names. Of those, ~30 made the "serious" cut. Of those, ~5 might survive Gates 1-4. The discipline is to let 90% of intellectual stimulation dissolve before it becomes a position. The bot exists precisely to prevent this batch-logging.



---

## Universe expansion 2026-05-15 (Option 2 — limited 3 tickers, no thesis logged)

Added to `config.yaml` `universe.watch`:
- **Kioxia (285A.T)** — NAND pure-play
- **Mitsubishi Heavy Industries (7011.T)** — turbines/nuclear/defense decotted vs GEV
- **Stevanato (STVN)** — borosilicate vials chokepoint GLP-1

Justification: limited universe expansion (not behavior change to existing 45 predictions cohort) to begin signal ingestion ahead of post-J+28 thesis evaluation. 27-day soak period.

**Hard rules**:
- NO /thesis_set before 2026-06-11
- NO position commitment before /thesis_set
- At 2026-06-11: re-evaluate with empirical signal data + KPI #2 batch results
- Promotion to thesis requires full pipeline: /analyze_debate → /asymmetry → /thesis_set → /thesis_premortem

Cross-ref: docs/thesis-candidates-queue.md "In soak" section, docs/adrs/002-universe-scaling-strategy.md.



---

## 2026-05-15 afternoon: 21 sector theses logged (5 sector narratives)

5 sector_thesis_id groupings, 21 theses total inserted via storage.add_thesis() + update_thesis_status() pour notes structurées. All direction='watch', status='active', conviction 2-4.

Sectors:
1. **HPQ_WAFER_CHOKEPOINT_2026** (4 tickers): 4063.T, 3436.T, 6890.T, MTUS
2. **POWER_GEN_AI_BOTTLENECK_2026** (5 tickers): 7011.T, GEV, CEG, BWXT, 5411.T
3. **PHARMA_FILL_FINISH_GLP1_2026** (4 tickers): STVN, WST, YPSN.SW, DIM.PA
4. **PHYSICAL_AI_ROBOTICS_ENABLERS_2027** (4 tickers): 6324.T, 6268.T, 6861.T, CGNX
5. **STORAGE_AI_HYPERSCALE_2026** (4 tickers): 285A.T, STX, 000660.KS, PSTG

Universe.watch expanded 84 -> 96 tickers (added: WST, DIM.PA, 6268.T, CGNX, STX, PSTG, 6324.T, 6861.T pour assurer signal coverage).

Hard rules:
- NO /position_buy on these tickers before /thesis_revisit at J+30+ (2026-06-15+)
- /thesis_revisit individual theses to update conviction with empirical signals
- Sector-level review at J+30 / J+60 / J+90 / J+180 (dates in docs/personal/sector-theses-tracker.md)
- If conviction drops to 1 on multiple theses within same sector, re-evaluate sector claim itself (not just tickers)

Next action 2026-06-15 (post-J+28): batch /thesis_revisit on 21 theses with signal data accumulated during soak period.



---

## P1 Sprint 1.2 — add_thesis() canonical entry point fix

Discovered 2026-05-15 evening: `shared/storage.py:add_thesis()` (L68) stores drivers/invalidation/triggers as plain strings, while `insert_thesis()` (L288) correctly serializes via `_t_json.dumps(_to_list(...))`. Divergent behavior between two parallel APIs causes downstream consumers (format_thesis_card, /thesis_list) to fail when add_thesis() was used.

**Affected callers** (to audit): all bot/main.py functions calling storage.add_thesis vs storage.insert_thesis.

**Fix options**:
- (a) Make add_thesis() call _to_list + json.dumps internally on string fields, matching insert_thesis() behavior (preferred)
- (b) Deprecate add_thesis(), migrate all callers to insert_thesis()

**Workaround currently in place**: Data migration converted plain strings to JSON list for the 21 sector theses logged 2026-05-15. Future add_thesis() calls will recur the bug.

Cross-ref: friction.md 2026-05-15 evening entry.



---

## Sprint 1.2 P0 — Handler consolidation 65 -> 20 verb-root

**Spec**: `docs/personal/handlers-consolidation-plan.md` (created 2026-05-15)
**Empirical basis**: 2.1d telemetry, 10.8% typo rate, Pareto 54% on 9 handlers
**Trigger**: post-J+28 = 2026-06-10+
**Effort estimate**: 8-12h across 4-5 commits (1 per verb-root module)
**Dependency**: Sprint 1.1 mechanical extraction must complete first (Monday 2026-05-19)

Ordered ship sequence (post-Sprint 1.1):
1. /thesis verb-root (handlers/thesis.py) — highest typo rate, biggest win
2. /portfolio verb-root (handlers/portfolio.py)
3. /journal + /signals + /market + /insider_detail (medium impact)
4. /ops + /predictions + /filings + /tiers (low usage, residual)

KPI for success: typo rate <2% at J+60.



---

## 🔬 Deepening dimensions — added 2026-05-16

Features ajoutées en attente de prérequis empiriques. **Aucune implémentation avant que les prérequis soient remplis**. Ré-évaluer empiriquement à chaque trigger date.

### À activer post-M+6 minimum (~juillet 2026)

- [ ] **Calibration plot par bucket (1.2)** — ~4 jours
  - **Prérequis empirique** : N≥30 résolutions
  - Trigger date earliest : 2026-07-15 (après J+28 batch resolution + 30j additional)
  - Compute calibration par bucket de confidence (10-20%, 20-40%, 40-60%, 60-80%, 80-100%)
  - Generate matplotlib calibration curve PNG
  - Handler `/calibration_curve` : send PNG via Telegram
  - Identifier zones overconfident / underconfident empiriquement
  - Inject drift dans prompts `/analyze` (Path 5/6 dimension 2 calibration engine)
  - Impact : précision >> score scalaire Brier

- [ ] **Source dependency mapping (3.4)** — ~5 jours
  - **Prérequis empirique** : N≥30 outcomes résolus traçables à source
  - Trigger date earliest : 2026-07-15
  - Schema : chaque thesis logged → champ `source_inspiration_ids[]` (FK signals)
  - Post-resolution : trace outcome accuracy par source
  - Handler `/source_alpha` : par source → win_rate, avg_brier, count_theses
  - Identify top 2-3 vs bottom 5-10 sur signal/noise ratio
  - Cron monthly : trim universe sources si bottom 5 underperform >3mo
  - Impact : concentrate signal, eliminate noise empiriquement

### À activer post-M+9 minimum (~août-sept 2026)

- [ ] **Anti-rationalization detector (2.2)** — ~7 jours
  - **Prérequis empirique** : corpus de ≥10 theses avec status='invalidated'
  - Trigger date earliest : 2026-09-01
  - Hook dans `cmd_log_thesis` : embedding new thesis vs failed theses corpus
  - BGE similarity threshold : si top-3 match cumul >0.85 → flag
  - Sonnet call : "Cette thesis ressemble à TICKER_X (Brier 0.65) failed sur drivers Y. Différence empirique vs narrative ?"
  - User force-acknowledge ou cancel decision
  - Logue similarity matches dans `theses.anti_rationalization_flags`
  - Impact : catch "this time is different" patterns automatiquement

### À évaluer post-M+12 (gros build, scope risk élevé)

- [ ] **Counterfactual paper portfolio (1.3)** — ~45 jours
  - **Prérequis empirique** : ADR 001 PIT bitemporal implémenté + decision rules formalisées
  - Trigger date earliest : 2026-12-01
  - Construire decision engine déterministe :
    - Input : signals + thesis state + position state + risk params
    - Output : signed action (buy/sell/hold) + size + reasoning
    - Rule-based, zero LLM in hot path (reproducibility)
  - Run paralllèle au portfolio réel, mêmes prix d'entrée
  - Cron daily : compute divergence paper vs réel
  - Handler `/bias_cost` : différence cumulative = coût empirique des biais
  - **Risques connus** :
    - Definition of "rules you should follow" subjective → confirmation bias inverse
    - N=21 positions, bruit statistique massif vs signal biais
    - Maintenance lourde (rules evolution sur 24mo)
  - Impact si réussi : mesure exacte coût émotionnel des biais
  - Impact si raté : theater of measurement, false confidence
  - **Decision gate avant build** : revue ADR dédiée requise avant ship


---

## P3 — Type hints fixes deferred from A3 ship 654369b (2026-05-16)

Three mypy errors in modules that have high type coverage already but need
small fixes to be added to strict override:

- [ ] **intelligence/insider_digest.py:115,126** — `Value of type "dict[Any, Any] | None" is not indexable`
  - Two locations where dict access happens without None check
  - Fix: add `if d is None: continue` OR cast(dict, d)
  - Effort: ~15 min

- [ ] **intelligence/price_monitor.py:239** — `Incompatible return value type (got "int | None", expected "int")`
  - Function declares return int but can return None in error path
  - Fix: change return type to `int | None` OR raise on None case
  - Effort: ~10 min

- [ ] **shared/positions.py:77,107** — `Incompatible return value type (got "dict[Any, Any] | None", expected "dict[Any, Any]")`
  - Two functions return None in error path but declared dict
  - Fix: change return type to `dict[Any, Any] | None`
  - Effort: ~15 min

After all 3 fixed, add modules to mypy strict override in pyproject.toml + ci.yml.
Trigger: Sprint 1.2 type hints completion sweep OR opportunistic when these
modules are touched.

---

## P0 DISCOVERED 16/05/2026 evening — Handler UX review one-by-one

**Empirical finding (user honest feedback)**: 73 handlers registered but
many display illisible/rebarbatif output. Code passes gates but
empirical value not delivered.

**Symptom**: gap between "smoke test Python OK" and "Telegram output
actually useful for decision making".

**Action plan**:

1. Inventory: list all 73 handlers grouped by category (already exists
   in docs/HANDLERS_INDEX.md to verify currency).

2. Categorize by usage intent:
   - CRITICAL: commands wanted daily/weekly (5-7 candidates)
   - OCCASIONAL: useful trimestriel
   - DEAD: never-use candidates -> deletion review per PHILOSOPHY
     "complexité a un coût cognitif"

3. Empirical audit CRITICAL handlers:
   - For each, capture verbatim Telegram output
   - Document in friction.md: command, output, intent, gap, priority
   - Identify pattern: is it format issue? labels énigmatiques?
     too much text? no TL;DR? wrong info hierarchy?

4. Fix strategy (TBD post-audit):
   - Incremental fixes per handler OR
   - Refactor unified output format if pattern emerges

5. DEAD handlers: trigger suppression per modify deprecation
   policy CONVENTIONS.md §15 (mark DEPRECATED 1 month, then delete)

**Priority**: P0. Test empirique reveals features without usable
output are not features. Blocks Path 5/6 narrative (track record
requires demonstrable empirical value).

**Effort**: 2-3h audit + variable fixes.

**Trigger**: post-J+28 batch resolution OR immediate if pre-J+28
audit reveals critical UX gaps.

---

## Sprint 1.2 — Handler consolidation + UX fix (planned 2026-05-16)

**Doc**: `docs/sprint-1.2-plan.md`
**Decisions**: `docs/handler-review-2026-05-16/decisions.md` (12 blocs)
**Surface reduction**: 73 -> 24 commands (-67%)

**Trigger**: post-J+28 (2026-06-10) OR earlier if UX blocks daily ritual.

**Estimated effort**: 23-28h Phase A-M + 8-15h Phase N UX fix.

**Critical path**:
- Phase A (renames only, 4 cmds): low risk, can ship pre-J+28
- Phase B-M (family unifications): post-J+28 only
- Phase N (UX redesign output): on demand per daily ritual blocker

---

## Day 5 closed (16 May 2026, 38 commits)

### Morning marathon (33 commits)
- Sprint 1.1: 9/10 PLAIN chunks bot/main.py 3324 -> 1115 LOC (-66%)
- 8 new features: /find, /portfolio_sectors/narratives/drift, /journal_audit, /signal_drilldown, /thesis_health, /bias_pattern
- mypy strict: 11 -> 30 modules
- Tests: 49 -> 189 Hypothesis property-based
- Chunk 3 TYPED reserved Sprint 1.2 (17 handlers, ~345 LOC)

### Pivot 1 — Handler UX audit (1 commit, 4a8eaa1)
- User feedback: "73 handlers, beaucoup affichent des textes incomprehensibles"
- 12 blocs K/U/D in docs/handler-review-2026-05-16/decisions.md
- 73 -> 24 commands planned (Sprint 1.2)
- docs/sprint-1.2-plan.md Phases A-N execution plan

### Pivot 2 — UX-fix sweep (3 commits, empirical Telegram validated)
- /brief v3.1 (43831d9): 16 lines, KPI #2 timer, top 5 conviction
- /digest v2 (0b01fd4): VERDICT line, header metadata, 1-line bruit
- /portfolio v2.1 (0d1735d): ALERTS + conviction + common names cache

### Pivot 3 — Portfolio thesis logging (1 commit, 5aeea1c)
- DELETE positions.NVDA zombi + bot_state reset
- INSERT 21 theses from user 5-thesis doc (Tier S/A/B mapping)
- 4 orphan c1 flagged for J+30 review (AMD, GOOGL, TSLA, SAF.PA)
- docs/snapshots/ for audit trail

---

## 🚧 P0 next session — Path A (10 min cleanup)

- **Supersede 6 watch theses HPQ + Pharma** (SQL ready in HANDOFF.md)
  - HPQ: 3436.T, MTUS (redundant Shin-Etsu)
  - Pharma: WST, STVN, DIM.PA, YPSN.SW (out of current focus)
  - Result: 39 -> 33 active theses
- Decide on remaining 12 watch theses (POWER_GEN, PHYSICAL_AI, STORAGE)
  - User reco: keep POWER + PHYSICAL, drop STORAGE
- Document handler-ux-2026-05-16/log.md (currently untracked)
- /portfolio empirical Telegram retest post-thesis-logging (should show all c1-c5, no c-)

---

## 🚧 P1 next session — Path B (30-45 min per handler)

Sprint 1.2 UX-fix sweep continues:
- /find (user favori) — diagnose + redesign + smoke + commit
- /journal audit (post-thesis logging KPI #5 enforcement)
- /thesis health (overview after 21 logged)
- /signal_drilldown (rename to /signal per Sprint 1.2)
- /biases (was /bias_pattern, rename)

---

## ⏱ KPI runtime check (Day 5 close)

| KPI | Cadence | Current | Status |
|---|---|---|---|
| **#2 NON-NEG** | Hebdo dim | 1 résolu 30d, 46 due in 24d | ⏳ ON TRACK |
| #3 Brier rolling 90d | Hebdo | N=0 (insufficient) | 🔍 NOT YET MEASURABLE |
| #4 Panic sells core | Mensuel 1er | 0 | ✅ GREEN |
| **#5 Decisions journalisées** | Mensuel | All theses logged = baseline established | ✅ DAY 5 ENABLED |
| #6 TWR vs SPY/QQQ 12M | Mensuel | Not implemented | ⏸ Sprint 1.2 |

**Cible KPI #2 J+24 = 10 juin 2026**. 46 predictions auto-resolve.

---

## 📋 Sprint 1.2 backlog (post-J+28)

Per docs/sprint-1.2-plan.md:
- Phase A: 73 -> 24 handlers consolidation (sub-command routing)
- Phase B: /thesis family fusion (9 handlers -> 1 with subcommands)
- Phase C: /portfolio sub-commands (sectors/narratives/drift in 1)
- ...
- Phase N: Full execution

---

## DETTE découverte Day 5 (carry-forward, not blocking)

### Tech
- Alembic migration for ticker_names table NOT added (table exists DB-only)
- /brief still uses "(check fx)" fallback instead of get_current_price_eur
- /digest VERDICT sometimes inconsistent with body (Sonnet inventing min 1 urgent)
- positions.currency column for real FX (workaround via get_current_price_eur)
- shared/ticker_names.py: no refresh logic (manual SQL update if company rebrands)

### Data hygiene (empirical discovery)
- 18 watch theses from 15/05 sector_thesis_id framework still active (decision pending)
- 4 orphan c1 positions need 30-day review window opens J+31 (16 juin)
- bot_state.last_heartbeat_ts may go stale (timestamp from 11/05 in JSON?)

### Discipline
- AMD, GOOGL, TSLA, SAF.PA held without thesis until Day 5 (orphan flagged)
- This empirical gap = exactly the "vendre trop tôt sans thesis structurée" risk

---

## 🎯 Mission queue next session (validated 16/05 evening)

**Execution order**:
1. P1 /thesis_health empirical retest (5 min gate) - validates 88db101 prompt fix
2. P1 UX-fix /find (30-45 min) - user favori, 5th handler
3. P1 UX-fix /journal audit (30-45 min) - KPI #5 enforcement
4. P0 Source coverage gap (1-3h) - Japan/Korea/EU newsletter sourcing
5. P2 Timezone audit (1h) - fix "-1d old" global
6. P2 Tier inflation review (30 min) - c4 saturation methodology

**Total**: 4-7h spread across 3-5 sessions.
**Deadline**: J+24 = 10 juin 2026 (KPI #2 batch resolution).


---

## Day 5 final close (16 May 2026 ~20:45 KST, HEAD=cec0f41)

### Ships Day 5 evening v3+extended (16 commits post-tag day5-final)

- ✅ 108d57d HPQ + Pharma cleanup (6 watch superseded, 6890.T rollback)
- ✅ 88db101 Intl pipeline fix (config+prompts US-bias-removed+thesis_health narrative=)
- ✅ 192b62c HANDOFF refresh post Day 5 evening
- ✅ a60b062 Mission queue 6 steps
- ✅ 65c7265 /analyze today_str fix
- ✅ b68120c /asymmetry 3-section bucketize (computed/incomplete/watch/errors)
- ✅ 6b97f2d F1b Phase 1 fx layer + /asymmetry strip verdict
- ✅ c1032b8 DB snapshot pre target/stop fill
- ✅ 7cec21e HANDOFF refresh v3 close
- ✅ cec0f41 C1+C2 today_str /analyze_debate + /thesis_premortem

### 9 handler UX-fixes Day 5 total
1. /brief v3.1 (instant vision, KPI #2 timer, top 5 conviction)
2. /digest v2 (header metadata + verdict line + 1-line bruit + drill-down)
3. /portfolio v2.1 (alerts top, conviction, PnL%, common names)
4. /thesis_health v2 (3 intl fixes)
5. /analyze today_str (Opus stale data fix)
6. /asymmetry verbose (3-section bucketize)
7. /asymmetry strip verdict (confirmation bias removed)
8. /analyze_debate today_str (multi-round dialectic anchor)
9. /thesis_premortem today_str (Opus failure-mode anchor)

### Dette systémique today_str ÉLIMINÉE empirique
- 4 LLM handlers fixés : /digest, /analyze, /analyze_debate, /thesis_premortem
- Pattern identifié + addressed empirique
- **Carry-forward audit** : /risk_check empirique semble OK (Day 5 evening test "January earnings" cohérent) mais audit empirique à confirmer

### 17 target/stop UPDATEs via framework empirique
- c5: stop=-25% target=+70% (L5 metrology cyclical mod=-20%)
- c4: stop=-20% target=+60% (L1 litho mod=-22%, HBM cyclical mod=-25%)
- c3: stop=-18% target=+50% (story stock mod=-25%, defense low vol mod=-15%)
- 4 orphans c1 (AMD/GOOGL/SAF.PA/TSLA) SKIPPED → review J+30=2026-06-16

### FX layer Phase 1 R3 calibrated empirique
- shared/prices.py HARDCODED_FX_TO_EUR
- JPY=0.005467, KRW=0.000591, USD=0.858 (calibrated vs broker)
- 6 modules NOT migrated yet (carry-forward S1)
- Phase 2 R1 SQLite fx_rates + daily cron deferred

### Philosophical insights Day 5 v3
- /asymmetry verdicts auto-derivés = tautologie + confirmation bias nocif
  → Stripped icons + labels + ratio number
  → Raw distances only (current/entry/target/stop in EUR + %)
- /analyze_debate convergence 0.93 NVDA "18-month thesis with cliff Q3-Q4 2026"
  → exactement le counter-bias system working empirique
  → bot dit où est le cliff AVANT panique

### Carry-forward critical (next session)

**P1 — F1b S1 full replace (8 modules, 60-90 min)**:
- intelligence/morning_brief.py (line 244 + comment line 302)
- intelligence/price_monitor.py:185
- intelligence/learning.py:125
- intelligence/thesis.py:149
- intelligence/shadow_decisions.py
- shared/positions.py:158
- bot/handlers/positions.py:103
- bot/handlers/portfolio_views.py:78

**P1 — Clarify dup function shared/prices.py**:
- Line 104 `get_current_price_in_eur` (new Day 5)
- Line 262 `get_current_price_eur` (existing)
- Investigate before migration to avoid double API call

**P1 — F1b Phase 2 R1 SQLite fx_rates table (60 min)**

**P2 — /risk_check today_str audit** (5 min check, +10 min if bug)

**P2 — Regenerate 21 PF pre-mortems** with anchored prompt (~$1 + 20 min, optional)

**P2 — Calibration tracking** (90+ min) : historique targets hit/missed

**P2 — Challenger layer** (120+ min) : compare targets to analyst consensus

**P3 — 26 silent tickers KPI #5** : user action, log decisions on AMD/AVGO/MRVL/GOOGL/MSFT/META

**P3 — 4 orphans c1 review J+30** : 2026-06-16



---

## P3 Q3 (post-J+90 = ~10 aout 2026) — dormant-handler triage

**Trigger** : telemetry handler_calls table avec >=90j de donnees continues
(actuellement demarre ~13/05/2026, mature ~15/08/2026).

**Empirical state Day 9 (17/05/2026)** :
- 47 unique handlers used / 73 registered (35% surface dormant)
- Top-10 = 60% calls (brief/digest/portfolio/health/help/asymmetry/find/
  kpi_status/analyze/handler_stats)
- Long tail 26 handlers a 1-2 calls (window 4-5j effectif, premature)
- Naming variants chaos sur theses : 5 commands listed (`theses`,
  `theses_list`, `thesis_list`, `list_theses`, `list_thesis`) - cross-check
  registry pour identifier aliases vs typos vs duplicates

**Action post-J+90** :
1. /handler_stats 90 -> Pareto curve mature
2. Identifier handlers <=1 call sur 90j -> candidats deprecation
3. Cross-check vs bot/main.py CommandHandler registry (intersect set diff)
4. Decision : delete / alias / keep selon utilite empirique vs design
5. Reduit organiquement bot/main.py LOC avant split architectural

**Path 5/6 alignment** : "Plus de discipline dans l'usage > plus de
discipline dans le code". Deprecation = solidification, pas regression.


---

## Day 9 session close (17 May 2026 ~14:15 KST)

### Closed this session (all 5 ships + extensions post-day9-close tag 52bd3a0)
- P1: CONVENTIONS Section 16 (7 rules codified) + Day 9 close tag aligned
- P2: telemetry middleware verified DB-side + lesson 8 channel verification appended
- P3: KPI #6 wired (shared/portfolio_metrics.py + 8 Hypothesis tests + observability wire + canonical schema)

### Empirical state end-of-Day-9
- 226 tests passing (218 prior + 8 new portfolio_metrics)
- 16 modules strict-typed mypy (+ shared.portfolio_metrics)
- ruff 0 errors all files
- Bot PID 41435 alive, scheduler 23 crons
- HEAD 85440e4 = origin/main, day9-close tag stable @ 52bd3a0
- 5 KPIs all wired:
  - #2 ON TRACK (45 resolutions dues 28d, forecast J+28: 46)
  - #3 INSUFFICIENT DATA (N=0, awaits 10 juin batch resolution)
  - #4 GREEN (0 panic sells)
  - #5 NO MATERIAL DECISIONS 30d (post-DELETE row 7 hygiene)
  - #6 INSUFFICIENT (1d/365d provisional, auto-flip 10 mai 2027)
- /kpi_status Overall: 2 GREEN | 0 YELLOW | 0 RED | 3 N/A (sum to 5)

### Backups Day 9 close (local, audit trail)
- data/backups/pre_kpi5_delete_20260517_133157.db (Sprint 2 epsilon hygiene)
- data/backups/pre_zeta_backfill_20260517_134038.db (Sprint 3 zeta hygiene)
- data/backups/day9_close_db_20260517_1411.db (atomic snapshot 3.1MB, 32 tables, integrity OK)
- data/backups/day9_close_20260517_1411.tar.gz (full data/ tar 3.2MB)

### Carry-forward Day 10 (none urgent, observation phase active)
- DEFER strict: bot/main.py 2428 LOC split (architectural session frais)
- DEFER strict: USD canonical migration (post J+30 = 10 juin 2026)
- Q3 (post-J+90 = ~15 aout 2026): dormant-handler triage post-telemetry-mature
- KPI #6 auto-transition post-J+365 = 10 mai 2027 (no action needed)

### Active timer
- **J-23 vers KPI #2 batch resolution = 10 juin 2026** (45+ predictions due)
- Observation phase: aucune feature build, monitoring passif uniquement
- Discipline CONVENTIONS Section 16 (8 rules total) stricte applied

---

## Day 10 Sprint — 17 May 2026 (observation freeze LIFTED)

Order: D → E → F → B → B' → A → C

- ✅ D Investigation position_buy n=2 anomaly Day 9 (NOT A BUG, friction.md captured)
- 🚧 E bot/main.py split → bot/handlers/* (4 batches, ~2.5-3h)
- ⏳ F USD canonical migration (~3-5h)
- ⏳ B L4 KPI #1 uptime wire vers /kpi_status (~45min)
- ⏳ B' handler_calls.is_typo column + migrate existing rows (~30min, adjacent observability)
- ⏳ A M2 SMH sectoral benchmark wire KPI #6 (~1.5-2h)
- ⏳ C Q3 dormant-handler triage post-telemetry (~2h)


---

## ✅ CLOSED — Day 14 (2026-05-20, ~6h session)

### ADR 005 EUR canonical refactor

**4 commits** since day13-close:
- `1cefee6` morning_brief FX (Bug 3 EUR canonical discovery)
- `b601bfd` ADR 005 core + cost_in + 6 Hypothesis tests + 2 test rewrites
- `8e345c2` Group C labels (risk_manager + bias_tagger prompts + journal_bias + format_position_history)
- `0bedcff` ADR 005 doc + Lesson 15 + HANDOFF + format_position_detail residuals + .gitignore

**Dettes résolues:**
- ✅ FM-10 latent currency mix (avg_cost EUR canonical via cost_in helper)
- ✅ KPI #6 bullshit -4.12% → real -4.05% currency-coherent
- ✅ 4 sites Group A broken (positions.py:146, portfolio_views.py:94+247, find.py:36, portfolio_metrics.py:113-119)
- ✅ Group C display labels (3 sites code + 5 sites string labels)
- ✅ morning_brief avg_cost_usd uniform EUR→USD (commit 1cefee6)
- ✅ Pipeline backlog clearing (28 signals classified + materiality_v2 chained, 4 zombies killed)
- ✅ Gmail OAuth re-auth flow (28 new signals, dead token cleanup)

**Documentation shipped:**
- docs/adrs/005-eur-canonical-positions.md (full ADR + 21-position empirical ratio audit table)
- CONVENTIONS.md Lesson 15 (empirical verification beyond SQL)
- HANDOFF.md Day 14 close section

**Tests**: 275 → 281 (+6 cost_in Hypothesis)

### Carry-forward P1 strategic (next session decision points)

- **Concentration breach** — `style.position_max_pct = 5%` violated by 6 positions (46.5% AI_compute cluster). 4063.T 10.5%, TSM 9.0%, ASML.AS 9.0%, SNPS 7.0%, 7011.T 6.0%, STMPA.PA 5.3%. Decision (a) trim / (b) bump policy 8-10% documented / (c) ignore legacy + watch new — required before next /position_buy.
- **KPI #2 timer J-20** to 2026-06-10 (45 predictions batch resolution day)
- **NVDA** — 2 high 8-K 5.02 in 12d, 2 unresolved decisions, /risk_check NVDA candidate
- **VALUE_LOG.md entry Day 14** — first /digest with action-grade synthesis tied to biases (Path 6 narrative evidence)

### Carry-forward P2 — ADR 005 incomplete coverage audit

Cross-source ratio audit pending (Lesson 15 pattern):
- `theses.entry_price/target_partial/target_full/stop_price` currency
- `decisions.price_at_decision` currency
- `position_events.price/pnl` currency
- `positions.realized_pnl` currency

### Carry-forward P2 — Infra

- OAuth Cloud Console "Push to Production" (15 min, prevent weekly token re-revocation)
- score column scale 0-10 vs 0-100 recal in build_signals_context_block
- Price snapshot drift /brief vs /portfolio caching audit (UX consistency)

### Carry-forward P2 — Universe

- Universe pruning audit J+30 mid-juin (313 tickers vs PHILOSOPHY "less surface")

---

## Day 14 evening — ADR 006 Phase 2A + 2B CLOSED

### Closed
- ✅ Phase 2A — CoreCPI fix + ISMMfg → MfgIP_yoy + 18 Hypothesis tests (e49c326)
- ✅ Phase 2B — _dispatch_alerts + 3 cron wrappers + bot/main.py wiring + smoke verify (1e4c745)
- ✅ Tests 281 → 299 passing
- ✅ Crons 22 → 25 active (Tier 1 daily 06:00 / Tier 2 Mon 06:30 / Tier 3 1st 07:00 Paris)
- ✅ ADR 006 doc updated with Phase 2A+2B closeout sections
- ✅ HANDOFF.md Day 14 evening close appended
- ✅ Tag `day14-debt` on HEAD `1e4c745`

### Carry-forward Phase 2C (~1h, next session UX layer)
- `/debt_history INDICATOR` — 30d sparkline + phase transitions per indicator
- `/debt_alerts on|off` — global mute toggle for autonomous alerts (default ON)

**Priority**: P2 (low). Core protective layer LIVE without these. Marginal UX value vs further observation time.

### Empirical state at close (20 May 2026 ~11:30 KST = ~04:30 Paris)
- Composite: **42.0 pts → Phase 2 STRESS** persisted in DB
- Tier 1 daily cron will fire at 06:00 Paris (in ~1.5h from close)
- First autonomous alert opportunity: if Gold/RepoSRF transition OR composite escalates to P3
- VALUE_LOG candidate event tomorrow morning: if alert fires while Olivier sleeps, then surfaces at wake = Path 6 narrative evidence

---

## Day 14 evening (FINAL CLOSE post-audit) — UTC datetime sweep tracking + Lessons 16-20

### Closed Day 14 evening (post-audit)
- ✅ L1 cron exception envelope (commit 2eebde3) — `_cron_run` shared helper, all 3 debt crons wrapped
- ✅ H1 alert content actionability (2eebde3) — `_PHASE_ACTIONS` injected in composite alert
- ✅ H3 None-prev composite docstring (2eebde3) — `_dispatch_alerts` behavior contract documented
- ✅ Phase 2C ship complete (2eebde3) — `/debt_history INDICATOR` + `/debt_alerts on|off`
- ✅ H2 integration tests (d6463fa) — 9 scenarios mocking notify.send_text, 299 → 308 tests
- ✅ Lessons 16-20 codified in CONVENTIONS.md
  - Lesson 16: heredoc double-escape + triple-quote nesting
  - Lesson 17: audit must read complete control flow (anti-false-positive)
  - Lesson 18: cron try/except + notify envelope mandatory
  - Lesson 19: alerts MUST include actionable recommendation
  - Lesson 20: UTC explicit on all persisted datetimes

### S1 false alarm closure (audit accuracy log)
Lesson 17 codified after I claimed SEVERE bug in `cron_tier1_daily` partial-tier composite. Re-read of `run_scan` lines 391-400 revealed the code already merges stale cached Tier 2+3 with fresh-scanned tier values into a full 15-indicator composite (with `stale: True` markers). My audit was wrong — pattern-matched without reading full control flow. Codified to prevent recurrence: never declare SEVERE without quoting the specific 3-5 lines exhibiting the bug.

### P2 — UTC datetime sweep (legacy violations, tracked)

20+ `datetime.now()` (naive) violations of CONVENTIONS §1 + Lesson 20. Sweep deferred to a dedicated session to avoid scope creep during observation period. Tracked inventory:

**shared/** (high-impact paths, fix first when touched):
- `shared/storage.py:40` — `last_heartbeat_ts` (cron heartbeat every minute, persisted in bot_state.json)
- `shared/positions.py:47` — position event timestamps
- `shared/edgar.py` — 6 sites (lines 48, 81, 247, 280, 355, 498) cache layer + cutoffs

**intelligence/** (signal pipeline):
- `intelligence/digest.py:315` — gmail ingest cutoff
- `intelligence/morning_brief.py:142, 217, 290` — thesis age + cluster timing
- `intelligence/calendar.py:47, 48, 68` — macro event cutoffs
- `intelligence/price_monitor.py:161, 207` — thesis lifecycle + override timestamps

**bot/handlers/** (display layer, lower stakes but consistent):
- `bot/handlers/thesis_health.py:112`
- `bot/handlers/anti_erosion.py:25` — friction/value log entries
- `bot/handlers/find.py:120, 145, 171` — date cutoffs

**Strategy**: when touching ANY of these files for unrelated work, fix the datetime usage in same commit (R14 "touch = type" rule extended to UTC). Avoid top-down sweep — high risk of regressions in modules without test coverage.

**Ruff custom rule candidate**: write a custom ruff plugin or grep-based pre-commit hook that flags `datetime.now()` (zero args). Day 15+ infra task.

### State at this close (20 May 2026, ~12:00 KST)

- 308/308 tests passing (299 base + 9 new debt_dispatch integration)
- 25 crons live (22 + 3 debt_monitor with try/except envelope)
- Composite persisted: 42.0 → Phase 2 STRESS (Gold P3, RepoSRF P3, MfgIP_yoy P2)
- Bot PID rotating naturally, current = 71677 (last restart 11:53:52 KST)
- `_alerts_enabled()` toggle live (default True)
- Path 6 narrative material: clean audit + lessons codification = engineering rigor evidence



---

## CHANTIER #1 — Immaculate Sweep J-21 (started 20/05/2026)

**Objectif Olivier (verbatim)**: "tout soit bien plug que tout les liens soit propres,
que la boucle fermee fonctionne bien, que la recolte de data, feed de data, apprentissage
soit solide, que les chiffres soient bons actuels et se refresh correctement, que tout
fonctionne bien de bout en bout proprement" + "propreté du code".

Closing date: 10/06/2026 (KPI #2 batch resolution day = decision point).

### Audit baseline 20/05/2026 (Bash 103-105)

System integrity:
- 66 signals 30d, 100% materiality coverage, 33 24h healthy
- 17/17 debt indicators fresh
- LLM cost $0.50/jour, $15-20/mo projected vs $50 budget HEALTHY
- 33 tables, integrity_check ok, WAL 0B clean, disk 15% used
- Bot DOWN detected mid-audit (SIGHUP zsh) — restarted PID 73366

System gaps identified:
- KPI #5 decisions: 2 logged on 21 positions distinct = 9.5% (1 distinct ticker = 4.8%)
- briefs table absent (ephemeral or persist?)
- 51/52 sources stuck 0.5 default credibility (expected pre-J-21)
- task='' on 19/21 LLM call sites (NOT a bug, by design — tier= is canonical)

Code cleanliness baseline:
- ruff 0 errors (post-fix)
- mypy 0 errors on 77 source files (post-fix)
- vulture: 2 false positives (Telegram signatures)
- 13 files with datetime.now() zero-arg violations (~35 sites)
- shared/storage.py: 1962 LOC (biggest non-backup file)
- bot/main.py: 801 LOC (already <1000 implicit target)
- 3 TODO comments (legit defers, not debt)

### Done P0 (4 commits, 20/05 evening)
- fce38c3 fix(debt_monitor) replace RepoSRF (ON RRP ambiguous) → BankReserves WRESBAL
- 246aaea fix(debt_monitor) BankReserves phase_ranges in millions USD (FRED native)
- 1d90ffe chore(immaculate-sweep) P0 free wins mypy 6→0 + _os dead + isort 14 files
- 9d8848c fix(immaculate-sweep) ruff --fix harmonize imports (combine-as-imports)

### P1 Sprint this week (~1.5h)
- [ ] KPI #5 investigation: trace cmd_position_buy → log_decision flow.
      Empirical: 2 decisions on 21 positions distinct. Three hypotheses to test:
      (a) bulk backfill 16/05 bypass expected (Phase B5 works on live adds)
      (b) Phase B5 hook still broken (Ship 5 regression)
      (c) no material live decisions taken since 12 mai
      Method: simulate /position_buy + verify decisions row created.
- [ ] docs/REFERENCE_SCHEMA.md accuracy audit. Mental model wrong on 4 columns
      this session: predictions.outcome_evaluated_at→resolved_at, claim_json absent,
      signals.materiality_v2 dispersed (impact_magnitude/reversibility/etc),
      llm_calls.timestamp→created_at.

### P2 Sprint week 27/05 - 02/06 (~5-7h dispersés)
- [ ] UTC sweep top-down (exception R14 "touch=type", immaculate is explicit mandate):
      - shared/storage.py (8 sites): heartbeat, events, theses, predictions, outcomes
      - shared/edgar.py (6 sites): age caches, cutoffs
      - intelligence/morning_brief.py (3 sites), digest.py (1), price_monitor.py (2),
        calendar.py (4)
      - bot/handlers/find.py (3), anti_erosion.py (1), thesis_health.py (1)
      - shared/positions.py (1), prices.py (1), uptime.py (1)
      - scripts/init_db.py (2)
      Total ~35 sites. Strategy: per-file commit, gates after each.
- [ ] Decision: briefs persistence.
      Either create briefs table + persist /brief outputs (track record artifact
      for Path 5/6 narrative), or accept "ephemeral by design" + document.

### P3 Defer post-10/06
- [ ] shared/storage.py 1962 LOC split (architecturally complex per R5 single-gateway)
- [ ] task= field everywhere for finer LLM attribution (low ROI, tier= sufficient)
- [ ] vulture as occasional audit only, not CI gate (overlap with ruff ARG001)

### Closing criteria 10/06
At J+0 (10/06) batch resolution, Chantier #1 closed if:
1. ruff 0 / mypy 0 / pytest passing maintained
2. UTC sweep complete (0 datetime.now() zero-arg)
3. KPI #5 either functional or explicitly N/A documented
4. REFERENCE_SCHEMA.md accurate
5. Lessons 21-24 codified in CONVENTIONS.md

### Lessons codified this session (20/05/2026)
- L21: grep before invoke — 3 name-guess fails (tier_scan, recompute_composite_from_latest, WRESBAL units)
- L22: imports via ruff --fix only, never isort standalone (split vs combine conflict)
- L23: task= field in llm wrapper is optional by design; tier= is canonical for cost attribution
- L24: vulture is occasional-audit tool, not CI gate (overlap + false positives on Telegram args)


---

## MIGRATION VPS FUTURE — Archive plan (drafted 20/05/2026)

**Status**: deferred. Trigger = post-10/06 KPI #2 GREEN + concierge demand validated.

**Target stack**: Hetzner CX22 (€4.51/mo, 4 vCPU / 4 GB / 40 GB SSD) + Backblaze B2
(€1/mo backups) + Uptimerobot free. Total ~€6/mo. Replaces Mac local dependency.

### Migration phases (4-8h focused, 1-2 days dispersed)
1. Préparation locale (1-3h): audit secrets, snapshot scripts, lock files
2. Provisioning VPS (30 min): create + SSH key
3. System setup (1-2h): Ubuntu 24.04 LTS + pyenv 3.14.4 + UFW + fail2ban
4. Code + data transfer (1h): git clone + scp secrets + SQLite .backup snapshot
5. Service config (1h): systemd unit + logrotate + backup cron + monitoring
6. First boot + smoke test (1-2h): 10-15 commands sequence verify
7. Cutover atomique (15 min): stop Mac → start VPS (no overlap, Telegram one-poller)
8. Observation 24-48h (Mac standby)

### Preparation tasks (can do now, no VPS required)
- [ ] Gmail OAuth Cloud Console push to Production (avoid 7-day refresh token expiry)
- [ ] Audit MIGRATION_SECRETS.md (gitignore) inventory
- [ ] .env.example commit (document all env vars)
- [ ] scripts/migration_snapshot.sh tested locally
- [ ] systemd unit file deploy/mes-bots-finance.service drafted
- [ ] requirements.lock.txt via pip freeze
- [ ] Backblaze B2 account + bucket created
- [ ] Hetzner account ready (no server yet)
- [ ] Smoke test checklist (10-15 Telegram commands)
- [ ] Local cold start test (clean venv reproduction)

### Specificités projet à anticiper
- Python 3.14: not in Ubuntu repos, pyenv install required
- Gmail OAuth: refresh token 7d if Testing mode, 6mo if Production
- SQLite WAL: snapshot atomique via .backup before transfer
- Telegram: ONE polling instance globally (no overlap)
- Timezone: timedatectl set Europe/Paris (APScheduler tz-aware)
- yfinance: IP rate-limit risk on cloud IPs (test post-migration)
- Anthropic/FRED: account-tied not IP-tied (no migration risk)

### Pièges classiques
- Marche sur Mac pas sur Linux (SQLite, paths case-sensitive, SSL libs)
- Refresh token Gmail expire pendant migration
- Telegram dual-instance overlap
- Timezone scheduler mismatch
- yfinance bloqué par Yahoo sur IP cloud
- Disk plein silencieux
- API key leak via git commit



---

## CHANTIER #1 — Status refresh end of session 20-21/05/2026

### Done (6 commits série, 20-21/05/2026)

**P0 free wins (4 commits)**:
- ✅ fce38c3 fix(debt_monitor) RepoSRF (ON RRP ambiguous post-QT) → BankReserves WRESBAL
- ✅ 246aaea fix(debt_monitor) BankReserves phase_ranges in millions USD (FRED native units)
- ✅ 1d90ffe chore(immaculate-sweep) mypy 6→0 + _os dead import + isort 14 files
- ✅ 9d8848c fix(immaculate-sweep) ruff --fix harmonize imports (combine-as-imports)

**P0 documentation (1 commit)**:
- ✅ 59931c6 docs(chantier-1) TODO Immaculate Sweep J-21 + Migration archive + Lessons 21-24

**P1 KPI #5 investigation closed (1 commit)**:
- ✅ 4964f22 docs(kpi5) baseline reset 21/05/2026 + Lesson 25 Phase B5 validated live

Empirical resolution via smoke test (decision #8 entry SMOKE + #9 full_exit SMOKE):
- Hypothesis (a) bulk backfill bypass = CONFIRMED
- Hypothesis (b) Phase B5 broken = ELIMINATED (chain validated live)
- Hypothesis (c) zero live entry since 12/05 = CONFIRMED
- Decision: forward-only honest tracking from 21/05/2026, no retroactive backfill

### Remaining P2 (5-7h focused future session)

- [ ] **UTC sweep top-down** : ~35 sites datetime.now() zero-arg sur 13 files
  - shared/storage.py (8 sites)
  - shared/edgar.py (6 sites)
  - intelligence/{morning_brief,digest,price_monitor,calendar}.py (10 sites)
  - bot/handlers/{find,anti_erosion,thesis_health}.py (5 sites)
  - shared/{positions,prices,uptime}.py (3 sites)
  - scripts/init_db.py (2 sites)
  Strategy: per-file commit, gates after each, NO top-down sweep brute (touch=type per R14 sauf exception immaculate mandate)

- [ ] **Briefs persistence decision** (2h)
  - Currently no `briefs` table; /brief outputs ephemeral
  - Decide: persist for Path 5/6 track record artifact, OR accept ephemeral + document

### NEW P3 — Schema discipline tooling (issu Lesson 21 répétée 5×)

**Problem**: Lesson 21 (grep before invoke) violated 5 times in single session despite codification :
1. tier_scan invented (réel run_scan)
2. recompute_composite_from_latest invented (n'existe pas)
3. WRESBAL units billions assumed (réel millions)
4. position_events.created_at assumed (réel timestamp)
5. conviction_history.ticker + risk_checks.ticker assumed (n'existent pas)

Doc-only règle insuffisante. Pattern trop ancré. Vrai fix demande contrainte structurelle.

**Options à explorer (post-J-21)**:
- (a) Wrapper Python `schema.assert_column_exists(table, col)` à appeler avant tout query
- (b) Custom ruff plugin qui scan SQL strings dans le code Python vs vrai schema sqlite
- (c) Abandonner SQL ad-hoc au profit ORM typé (SQLAlchemy + reflection)
- (d) Generated typed wrapper depuis schema via codegen
- (e) Pré-commit hook qui exécute sqlite3 .schema vs queries dans diff

Effort: variable 2-8h selon option. Aligne avec PHILOSOPHY "Tout output non instrumenté est gaspillé" — un schema implicite est un output non-instrumenté.

### Closing criteria 10/06 (unchanged)
1. ruff 0 / mypy 0 / pytest passing maintained ✓ (current: clean)
2. UTC sweep complete (0 datetime.now() zero-arg)
3. KPI #5 either functional or explicitly N/A documented ✓ (done)
4. REFERENCE_SCHEMA.md accurate
5. Lessons 21-25 codified ✓ (done)
6. **NEW** Schema discipline tooling shipped (P3 option chosen)



---

## CHANTIER #1 — P2 UTC SWEEP CLOSED (21/05/2026)

### Done — 7 commits série post-end-session-refresh
793ce4e fix(thesis_health) tz strip → promote pattern regression
f9fb321 fix(uptime) strptime tz-aware UTC regression
9419768 fix(utc-sweep) final batch 10 sites bot/handlers + shared + scripts
48ddb32 fix(intelligence) complete UTC sweep 3 remaining digest + price_monitor
ac7db2e fix(intelligence) UTC sweep 11 sites across 4 files
388351b fix(edgar) UTC sweep 6 sites
9299671 refactor(storage) remove _t_dt/_t_td/_t_json alias pattern
513e5e7 fix(storage) UTC sweep 6 sites
6a8a58d refactor(storage) purge 3 dead prediction functions schema drift

### Empirical tally
- 39 datetime.now() sites swept → UTC-aware (12 storage + 6 edgar + 11 intelligence + 10 final)
- 3 dead prediction functions purged storage.py (-51 LOC)
- _t_dt/_t_td/_t_json alias pattern removed storage.py
- 2 regression bugs found + fixed (uptime strptime + thesis_health strip)
- 308 tests passing / ruff 0 / mypy 0 maintained throughout

### NEW P3 follow-ups discovered during sweep

**P3-A: tz-strip anti-pattern (8 live sites)**
`datetime.now(UTC).replace(tzinfo=None)` pattern equivalent to deprecated utcnow().
Sites:
- intelligence/insider_buy_cluster.py L64, L136, L142
- intelligence/analyze.py L424, L464
- shared/storage.py L868 (flagged Bash 120, preserved for downstream contract)
- bot/handlers/sources_admin.py L50
- bot/handlers/signals_filings.py L65

Strategy: audit each downstream consumer (DB column expectations, comparison
sites) THEN harmonize to tz-aware OR document explicit naive contract. ~3-5h.

**P3-B: local re-import / alias pattern cleanup**
Multiple files re-import datetime modules at function scope (redundant with
top-level import OR aliased to avoid conflicts):
- edgar.py L348, L479: `from datetime import datetime, timedelta` local
- digest.py L379: `from datetime import datetime as _dt` alias
- calendar.py L171: `from datetime import date as _date, timedelta as _td` alias
- calendar.py L263: `from datetime import datetime` local

Strategy: same pattern as storage.py Bash 120 cleanup. Replace aliases with
canonical names, remove redundant local imports. ~1h focused.

**P3-C: NEW lesson 26 codified** ← already done this session

### Remaining Chantier #1 backlog J-21

- [ ] P2 briefs persistence decision (2h) — unchanged
- [ ] P3-A tz-strip anti-pattern harmonization (3-5h)
- [ ] P3-B local re-import cleanup (1h)
- [ ] P3 schema discipline tooling (Lesson 21 5× violations — see prior section)

### Closing criteria 10/06 — progress
1. ruff 0 / mypy 0 / pytest passing maintained ✓
2. UTC sweep complete ✓ **(this session)**
3. KPI #5 either functional or explicitly N/A documented ✓
4. REFERENCE_SCHEMA.md accurate — NOT done (P1 carry-forward)
5. Lessons 21-26 codified ✓
6. Schema discipline tooling shipped — NOT done (P3 carry-forward)



---

## POST-CHANTIER #1 BACKLOG — High-ROI infra (added 21/05/2026 end of session)

Triaged from a wishlist of 40+ items down to 2 multipliers worth shipping
during observation window (J-19 → 10/06/2026). Strictly post-Chantier #1,
no work before next session.

### Item 1 — Query observability wrapper (~2h)

Goal: catch + diagnose silent SQL failures (cf. _store_analysis-class bugs)
in 10sec instead of 30min.

Design sketch:
- New `shared/storage.py` :: `def query(sql, params=None, *, tag=None)`
- Wraps `cx.execute()` with:
  - Duration (perf_counter)
  - Rows count (cursor.rowcount or fetchall len)
  - Exception capture + context (table+column from sqlite error msg if possible)
  - Caller frame inspect (`inspect.stack()[1]` for module:function:line)
  - Tag métier (optional explicit label, e.g. "positions.load_open")
- Log format:
  - Happy: `[SQL] {tag or caller} {duration_ms}ms rows={n}`
  - Error: `[SQL ERROR] {tag} table={t} column={c} caller={f}\n  {exception}`
- Use logging.getLogger("sql") with own handler if separated routing needed

Migration progressive (NO big-bang):
- Phase 1: ship the wrapper + unit tests
- Phase 2: migrate sensitive sites only (storage.py heavy paths,
  intelligence/digest.py, intelligence/price_monitor.py, intelligence/morning_brief.py)
- Phase 3 (optional, later): ruff custom rule encouraging `query()` over
  bare `cx.execute()` for new code

Multiplier ROI: next "silent SQL fail" bug becomes self-diagnosing.

### Item 2 — Invariants métier tests (~2h)

Goal: catch silent data corruption that schema discipline can't detect.

Target file: `tests/test_invariants_metier.py`

Assertions to ship (5-8 critical):
1. `qty >= 0` on positions (no negative inventory)
2. No two ACTIVE positions on same ticker (uniqueness invariant)
3. Brier scores ∈ [0, 1] on resolved predictions
4. `decisions.return_{30,90}d_pct` mathematically consistent with
   `price_{30,90}d / price_at_decision` (within float epsilon)
5. `theses.target_partial < target_full` when direction='long'
   (and inverse for direction='short')
6. Timestamps monotones per time-series (position_events.ts strictly
   increasing per position_id)
7. (optional) `theses.entry_price > 0` when status='active'
8. (optional) `signals.score ∈ [0, 100]` when score IS NOT NULL

Run in CI gate (pytest -q already wires it). Fast (single sqlite read per
invariant). No mocking needed.

Multiplier ROI: data corruption surfaces at next pytest run instead of
when the bot produces wrong output to user.

### Items NOT shipping during observation (deferred or rejected)

REJECTED — viole stack contraint (PHILOSOPHY.md):
- Postgres migration → Python 3.14 + SQLite locked
- Cloud deployment / Grafana / centralized logging → MacBook Pro local
- Health check HTTP endpoint → pgrep + uptime.log + /handler_stats suffices

DEFERRED post-10/06 (conditioned on KPI #2 GREEN + external demand):
- Multi-user / beta family/friends → not a single external user today
- Onboarding guided / PDF exports / visibility levels → pre-product-market-fit UX
- Environment-based config (dev/prod/beta) → one environment exists
- Bias Detector personnalisé → presupposes N>=30 resolutions
- Conviction decay intelligent → same data volume problem

DEFERRED post-J+90 (conditioned on real data signal):
- UX polish handlers → /handler_stats Pareto reveals which to polish
- Brief + digest actionability tuning → A/B requires baseline first

ALREADY SHIPPED (not re-ship):
- Logging structuré + niveaux → logging stdlib used in bot.log + handler_calls
- Métriques crons → /handler_stats + /llm_costs + /cost_trajectory + /kpi_status
- Détection doublons signaux → echo_clusters + Stratechery/Apollo dedup Day 2
- Typed row access → sqlite3.Row pattern already in storage.py
- Migration discipline → alembic_version table + scripts/alembic/ exist
- Brier + calibration infra → ready, awaits 10/06 batch

### Observation rules until 10/06/2026 (per PROCEDURES.md)

- NO new features. NO new tickers. NO new sources. NO new handlers.
- Daily /brief ritual.
- Sunday auto-summaries (handler_stats + cost + kpi_status).
- 10/06: ~44 predictions auto-resolve → first real Brier measurement.
- Decision point Path 5/6 based on KPI #2 outcome.
