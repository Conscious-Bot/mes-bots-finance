# ADR 004 — USD canonical migration

**Date** : 18 mai 2026 (Day 11)
**Status** : Accepted (user signoff option (b) full UX swap)
**Supersedes** : Day 7 FX migration (EUR canonical, partial)

## Context

Bot universe AI/semis US-dominant (76 tickers core, 14/21 positions AI_compute thesis). Data sources primaires (yfinance, EDGAR, FRED, CoinGecko) returnent USD natif. La Day 7 migration avait centralisé EUR canonique via `get_current_price_in_eur` + `HARDCODED_FX_TO_EUR` pour aligner avec EUR-denominated brokerage account.

### Problèmes post-Day-7

1. Double conversion USD→EUR→display crée bruit numérique sur small price moves, particulièrement intl tickers .T/.KS/.AS/.PA (~30% du portfolio)
2. Benchmarks SPY/QQQ/SMH natifs USD — conversion EUR ajoute volatilité FX qui dilue signal KPI #6 portfolio-vs-benchmark
3. Thesis price targets (analyst reports, newsletters US) sont en USD — conversion EUR introduit lag dans price_monitor triggers
4. Cognitive load : newsletters (SemiAnalysis, Stratechery) parlent USD, bot affiche EUR — friction de traduction mentale

## Decision

Migrate internal canonical from EUR to USD. Display primary devient USD. EUR available en secondary display pour portfolio total + position values (préserve ancrage brokerage).

### Schéma cible

**Producer layer** (`shared/prices.py`) :
- `HARDCODED_FX_TO_USD: dict[str, float]` (USD-pivot)
- `BASE_CURRENCY = "USD"`
- `get_current_price_in_usd(ticker)` — primary
- `get_current_price_in_eur(ticker)` — wrapper backward compat

**Consumer layer** (`portfolio_metrics`, `positions`, `price_monitor`) :
- Math interne en USD
- Conversion vers EUR uniquement au display layer

**Display layer** (`bot/handlers/*`, `intelligence/morning_brief.py`) :
- Primary : valeurs $
- Secondary : € en parenthèses pour portfolio total + position values
- Symbols : $ primary, € secondary, ¥/₩ natif pour intl positions

## Consequences

### Positive
- Élimine double-conversion noise sur intl tickers
- Benchmarks dans leur native currency, KPI #6 cleaner signal
- Aligne avec newsletter/research USD convention
- Thesis triggers USD = comparison directe avec analyst targets (no FX lag)
- Multi-currency support future plus simple

### Negative
- UX shift : /brief affiche $49K au lieu de €42K. Cognitive dissonance avec brokerage EUR pendant ~23 derniers jours avant KPI #2 batch resolution.
- Risque subtil de biaiser décisions pré-trade si perception portfolio total change pendant observation phase.
- Dual-currency code paths (`*_in_eur` wrappers) à maintenir jusqu'à cleanup post-juin.

### Mitigation
- EUR displayed secondary : `"$49,242 (€42,712)"` pour préserver ancrage brokerage
- Migration en 5 batches indépendamment réversibles via `git revert`
- Soft rollback : env var `BOT_DISPLAY_CURRENCY=EUR` switchback display (TBD batch 4)

## Implementation plan

5 batches, ~3.5-4.5h cumulé, gates R18 + R19 strict per batch :

1. **Batch 1** (~1h) : `shared/prices.py` foundation — `HARDCODED_FX_TO_USD`, `get_current_price_in_usd`, `BASE_CURRENCY = "USD"`
2. **Batch 2** (~45min) : `shared/portfolio_metrics.py` — `compute_portfolio_return_usd`, `fetch_benchmark_return_usd`, `compute_kpi6` USD primary
3. **Batch 3** (~1h) : `shared/positions.py` `_enrich_with_live` + `intelligence/price_monitor.py` thesis triggers USD canonical
4. **Batch 4** (~1h) : `bot/handlers/positions.py` + `portfolio_views.py` + `find.py` display $ primary + € secondary
5. **Batch 5** (~45min) : `intelligence/morning_brief.py` + `/digest` /brief USD primary

## Rollback

- Per-batch : `git revert <commit>`
- Full : `git reset --hard f3dc54c` (Day 11 cleanup floor, pre-migration)
- Soft : env var switchback (batch 4)

## References

- ADR 001 PIT bitemporal credibility (parallel architectural ADR)
- HANDOFF Day 7 close "FX migration COMPLETE" section
- CONVENTIONS Section 16 R11/R13/R14/R17/R18 + R19 candidate (subshell pattern)
- Day 11 sub-session item B (this work)


## Batch 3 amendment (18 May 2026, post-forensic)

Original plan: Batch 3 = `shared/positions.py _enrich_with_live` + `intelligence/price_monitor.py` thesis triggers, both flipped to USD canonical.

**Empirical forensic revealed**: `price_monitor.check_thesis_triggers` compares live price `p` against DB-stored thresholds `target_partial`, `target_full`, `stop_price`. These thresholds were typed by the user at thesis creation in unknown currency convention (likely native or EUR per legacy /thesis handler). Flipping `p` to USD without verifying threshold currency convention would cause silent trigger drift:
- False positives if thresholds are higher-magnitude currency (JPY threshold ¥4500, USD price $30 -> erroneous comparison)
- Missed triggers if thresholds are lower-magnitude currency

**Risk**: KPI #4 (zero panic sells core) is the failure mode this monitor protects against. Silent trigger drift during observation phase would corrupt the very metric being monitored.

**Revised Batch 3 scope**:
- **Part A (shipped)**: `_enrich_with_live(target_cur="EUR")` parametric, default EUR (backward compat preserved). Batch 4 display handlers will opt-in to USD by passing target_cur kwarg.
- **Part B (deferred post-J+30)**: `price_monitor` requires a DB forensic + threshold currency audit before flipping. Diagnostic plan:
  1. `SELECT id, ticker, target_partial, target_full, stop_price, notes FROM theses WHERE status='active'`
  2. For each thesis, compare threshold magnitude to plausible currency range (native, EUR, USD)
  3. If currency convention inconsistent across theses -> schema migration needed (currency column on theses table)
  4. If uniform -> simple `get_current_price_in(ticker, threshold_currency)` switch
  5. Codify result in ADR 004 Batch 3B addendum

**Impact on overall ADR 004**: full UX swap option-b achieved for DISPLAY layer (Batches 4-5). Internal price_monitor alerting math preserves correct comparison currency during observation. User-facing display shows USD primary post-Batch-5. KPI #4 fidelity preserved.

**FM-10 candidate (latent, pre-existing bug, NOT introduced by this batch)**:
`_enrich_with_live` computes `unrealized_pnl = (p - avg_cost) * qty` where `p` is in target_cur but `avg_cost` is in NATIVE currency. For any ticker whose native currency != target_cur, this difference is currency-mixed. Affects 8 international positions (.T, .KS, .AS, .PA). Fix scope: full currency-aware pnl computation, deferred to post-J+30 alongside Batch 3 Part B DB audit.


## Display layer coupling audit (18 May 2026, post-Batch 4C)

**Finding**: `shared/display.py` has `CANONICAL_FINANCE: Final[Currency] = Currency.EUR` + module docstring:
> "Future USD migration requires BOTH storage migration AND CANONICAL_FINANCE flip together. Display layer auto-updates with no handler edits."

**Diagnostic Batches 4A/4B**:
- 4A `cmd_portfolio` passes USD values to `format_position_line` -> internally `format_finance(value)` with CANONICAL_FINANCE=EUR -> would render `€{USD_value}` on restart. Symbol/magnitude mismatch.
- 4B `_compute_book_market_value` returns USD values consumed by sectors/narratives via `format_finance` + `format_aggregate_line` -> same mismatch.
- 4C find.py uses explicit `${X} (€{Y})` f-strings, bypasses format_finance -> CORRECT regardless of CANONICAL_FINANCE.

**Bot status**: still on cached f3dc54c, no restart since pre-Batch-1. Display still uniform EUR. No runtime damage. Caught by forensic during Batch 5 planning.

**Day 12 plan (Path γ — currency kwarg extension)**:
1. display.py: add `currency: Currency | None = None` kwarg to `format_finance`, `format_position_line`, `format_aggregate_line`, `format_brief_position_line`. Default to CANONICAL_FINANCE. Backward-compat for legacy callers.
2. 4A/4B retrofit: pass `currency=Currency.USD` explicitly at call sites.
3. Batch 5 morning_brief: same pattern.
4. Restart bot + smoke /portfolio /portfolio_sectors /portfolio_narratives /brief /find ASML.AS.
5. Tag day12-close.

Estimated Day 12: ~2-2.5h.

**Path δ alternative** (NOT chosen): flip CANONICAL_FINANCE = Currency.USD. Requires audit + migration of ALL existing format_finance callers to pass USD. Higher risk (silent legacy callers breaking).
