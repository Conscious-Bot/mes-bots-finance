# Session State — mes-bots-finance

**Last updated**: 13 May 2026, fin de marathon Day 2 + extension (~10h cumulative)

## Mode actuel

**High Standard / Solidification** — Path 5/6 strategic target.
**Reste à shipper P1+ avant nouvelles features.**

## Status complet — End of Day 2

### P0 sweep (6/6 closed)
- ✅ #1 Property-based tests Hypothesis (37 passing, 100% cov helpers)
- ✅ #2 Backup quotidien 04:00 + restore test (integrity + 14d rotation)
- ✅ #3 Handler usage telemetry middleware + /handler_stats
- ✅ #3.5 SQLite WAL mode (concurrency dette)
- ✅ #4 Sources tier S/A/B empirical (docs/SOURCES.md v2)
- ✅ #5 Failure modes registry top 5 (docs/failure_modes.md)

### P1 dette (4/4 closed)
- ✅ #1 last_signal_at NULL (insert_raw_signal atomic + backfill 27 sources)
- ✅ #2 materiality_v2 coverage 16% → 100% (chained architecture + backlog cleared)
- ✅ #3 SemiAnalysis 0 signaux (root cause: max_results=20 + uptime) → bump 50, EDA Primer ingested
- ✅ #4 Stratechery doublons merged (+ Apollo bonus merge)

### P2 backlog (carry forward)
- New: ingest_gmail_job new_count over-reports (cosmetic stats)
- Existing: refactor bot/main.py 2428 LOC → handlers/*.py split (4h)
- Existing: docs restructure (REFERENCE_SCHEMA, HANDLERS_INDEX, PROCEDURES, runbooks/)
- Existing: PIT bitemporal migration ADR (~2h)
- Existing: CI minimal GitHub Actions on push (1h)
- Existing: type hints + ruff/mypy basics (4h)

## Empirical state actuel

- **66 signals** ingested 30j (vs 62 ce matin)
- **100% materiality_v2 coverage** (vs 16% ce matin)
- **27 active sources** (vs 31 — 4 dedup'ed: Stratechery x1, Apollo x1, et 2 sources phantom n_signals=1 reset à 0)
- **5 Tier S empirical**: Adam Tooze, Chamath, Wall Street Rollup, Coin Metrics, SemiAnalysis
- **All credibilities à 0.5 default** — KPI #2 (Brier resolution J+28) reste le blocker pour ledger movement

## Architecture status

- Python 3.14, SQLite WAL, APScheduler — stack inchangé
- 215 tickers (22 core / 81 watch / 112 extended)
- 19 crons (backup 04:00, handler_stats Sun 23:00, materiality_v2 catchup 1h)
- 64 handlers Telegram avec telemetry middleware
- 15 tables DB (incluant handler_calls nouvelle)
- 37 unit tests Hypothesis (100% pass)
- Coverage helpers math: 100% (clamp_credibility, compute_brier_score)
- Coût observé: ~$0.60-0.80/jour

## Entry point next session

1. `cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate`
2. `ps aux | grep bot.main` confirmer vivant
3. Lire ce SESSION_STATE.md + TODO.md
4. **Decision point**: rester en solidification (P2 backlog) ou commencer track record mesure (KPI #2 enforcement, Brier resolution monitoring)

**NE PAS BUILD nouvelles features**. P2 = solidification finition, pas extension.

## Documents canoniques

- `FICHE_TECHNIQUE.md` lean (~80 lines) — mission + stack + KPIs
- `docs/SOURCES.md` v2 — tiers S/A/B empirical (composite_avg)
- `docs/failure_modes.md` — top 5 failure scenarios + runbooks
- `TODO.md` — backlog + Path 5/6 roadmap + P1 dette closed
- `PHILOSOPHY.md` — High Standard Mode principles
- `tests/` — 37 tests Hypothesis property-based
- `scripts/backup.sh` + `Makefile` — automation
- `SESSION_STATE.md` — this file, handoff canonical



## Known artifact — cluster temporel predictions (13 May 2026)

**Empirical finding du marathon**:
- 45 predictions existantes ont TOUTES horizon_days=30 (hardcoded default)
- Toutes target_date entre 2026-06-10 et 2026-06-11 → batch resolution massif J+28
- Implication: KPI #3 Brier inutilisable jusqu'au 10 juin, puis N=40 d'un coup

**Fix shipped** (P2):
- `intelligence/learning.py:horizon_for_signal_type()` — diversification par signal_type
- SIGNAL_TYPE_HORIZONS: catalyst=14, data=30, opinion=30, narrative=60
- Impact ≥4 narrows horizon (catalyst 14→7, narrative 60→30)
- Effet: predictions FUTURES diversifiées, les 45 existantes laissées (intégrité historique)

**Tracker**: après 10 juin, observer si Brier devient meaningful avec N≥10 continu.


## Afternoon extension (13/05/2026 ~4h additional)

### P2 ships closed in series
- **/kpi_status handler + weekly cron Sun 22:30**: Path 5/6 dimension 2 monitoring active
  - KPI #2 forecast J+28: ON TRACK (40 due in 28d, projection 41 ≥ target 5)
  - KPI #3 Brier: insufficient data (N=0, awaiting June 10 resolutions)
  - KPI #4 panic sells: 0 ✅
  - KPI #5 decisions journalisées: N/A (no material decisions 30d)
  - KPI #6: not yet implemented (positions integration needed)

- **Ship A — horizon diversification** (anti-cluster temporel)
  - SIGNAL_TYPE_HORIZONS: catalyst=14, data=30, opinion=30, narrative=60
  - High impact ≥4 narrows further (catalyst→7, narrative→30)
  - 12 new Hypothesis tests (49 total)
  - Effect: FUTURE predictions diversified; existing 45 untouched (June 10 batch remains)

- **Ship B — CI minimal GitHub Actions**
  - .github/workflows/ci.yml: Python 3.14 matrix, pytest + coverage XML artifact
  - requirements.txt updated (numpy, yfinance, sentence-transformers)
  - requirements-dev.txt separated (pytest, hypothesis, pytest-cov)
  - README.md minimal with CI badge placeholder
  - Pending: user creates GitHub remote + push

- **Ship C — /cost_trajectory handler + weekly cost cron Sun 22:00**
  - MTD spend + linear projection vs $50/mo budget
  - Tier + task breakdown 30d
  - Daily 7d trend bar chart ASCII
  - Auto-alert via notify if RED (>90% budget)
  - Current trajectory: $0.50/day → $15/mo projected (5% budget, ✅ GREEN)

### Final cron schedule
heartbeat 1h, gmail 1h, calendar 5h, insider 6h, digest 7h+19h, journal_resolve 8h,
resolve 9h, brier_recal 1st 6h, echo_clusters 1h, score_pending 1h, half_life Sun 5h,
price_monitor 15min mkt hours, crypto 10h, buy_cluster_scan 6:20, resolve_buy_cluster 8:15,
8k_scan 6:30, **backup 4:00**, **cost Sun 22:00**, **kpi_status Sun 22:30**, **handler_stats Sun 23:00**,
signal_classify 30min, materiality_boost 1h, materiality_v2 1h

### Tests final: 49/49 passing
- shared/math_helpers: 100% coverage
- intelligence/asymmetry: 41%
- intelligence/materiality_v2: 17% (pure math path)
- intelligence/learning: NEW horizon_for_signal_type 100%

### Total session : 14 items shipped (6 P0 + 4 P1 + 4 P2), 49 tests, 0 régression
