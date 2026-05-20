# ADR 005 — EUR-Canonical avg_cost Storage

**Status**: Accepted
**Date**: 2026-05-20 (Day 14)
**Supersedes**: implicit Day 11 ADR 004 Batch 4A "USD-canonical with NATIVE storage" (aspirational, never realized)

---

## Context

Day 11 (8 May 2026) Batch 4A introduced a "currency-aware pnl" refactor whose
inline comments claimed `positions.avg_cost` was stored in NATIVE currency
(JPY for `.T`, KRW for `.KS`, EUR for `.PA`/`.AS`, USD otherwise) and that
display handlers would multiply by `fx_native_to_TARGET` for display in
target currency.

This claim was **aspirational**. The actual broker import path
(`legacy_import_2026_05_15`) stored `avg_cost` directly in EUR for all 21
positions, never executing the assumed native conversion at import time.

The mismatch manifested empirically on Day 13-14 in two cascading bugs:
- `morning_brief.py` `_positions_top5_section`: SK hynix displayed as
  `-1.1%` correct after `1cefee6` patch (uniform `eur_to_usd` instead of
  `fx_native_to_usd` on EUR-stored cost), proving EUR canonical.
- `compute_portfolio_return_eur` KPI #6: was `-4.12%` "bullshit" because
  non-EUR-native positions had `eur_inv = qty * avg_cost * fx_native_to_eur`
  which multiplied EUR-stored values by ~0.005 (JPY) or ~0.0006 (KRW),
  artificially deflating the entry side ~15-fold on those tickers.

Cross-currency ratio audit Day 14 confirmed empirically: all 21 positions
have `avg_cost / live_price_eur ∈ [0.937, 1.147]`. Tight cluster around 1.0
across JPY/KRW/USD/EUR native tickers = EUR canonical storage.

## Decision

Codify EUR as the canonical storage currency for `positions.avg_cost`.

Introduce `shared.positions.cost_in(avg_cost_eur, target_cur)` helper as the
**single source of truth** for EUR -> target currency conversion at display
or computation time.

All handlers that need a target-currency representation of `avg_cost`
**MUST** route through `cost_in()`. Direct multiplication by FX rates
(`avg_cost * fx_native_to_TARGET`) is **forbidden** — this pattern produces
1000x+ errors when avg_cost is EUR not native.

## Consequences

**Positive:**
- Eliminates cross-currency P&L errors observed on JPY/KRW positions
  (e.g. SK hynix cost basis `$0.76` -> correct `$1,216`)
- Single mental model: storage EUR, display via helper
- KPI #6 currency-coherent (verified entry €43,384 / current €41,628 /
  return -4.05% over 4.8 days, 21/21 priced)
- 6 Hypothesis property tests lock the invariants on `cost_in`

**Negative / tradeoffs:**
- Future broker imports MUST convert to EUR at import time
  (responsibility shifted from display to ingestion)
- Documentation needed in `CONVENTIONS.md` to prevent regression to
  "native-storage" mental model
- `_enrich_with_live` now does its own internal `cost_in(avg_cost, target_cur)`
  for unrealized_pnl coherence

## Alternatives rejected

**A. Migrate storage to NATIVE per Day 11 Batch 4A aspirational design**
- Would require live migration of 21 active positions
- Risk of double-converting via legacy code paths during transition
- Adds storage complexity (per-ticker currency lookup at read time)
- Rejected: high blast radius for theoretical purity gain

**B. Per-position `cur_in_db` metadata column**
- Over-engineering for a stable broker import convention
- Adds schema migration burden
- Useful only if multiple importers store different conventions (not the case)
- Rejected: solving a problem we don't have

**C. Status quo (ad-hoc handlers each apply fx differently)**
- 4 sites independently buggy (KPI#6, /portfolio, /find, _enrich_with_live)
- No single source of truth
- Display vs computation divergence
- Rejected: actively producing the bugs ADR 005 fixes

## Empirical evidence

Day 14 cross-currency ratio audit on real DB (21 open positions):

| Ticker     | Native | avg_cost | live_EUR | ratio |
|------------|--------|----------|----------|-------|
| 000660.KS  | KRW    | 1043.06  | 1028.34  | 1.014 |
| 4063.T     | JPY    | 38.52    | 37.35    | 1.031 |
| 6920.T     | JPY    | 208.22   | 192.33   | 1.083 |
| 7011.T     | JPY    | 22.12    | 21.95    | 1.008 |
| ASML.AS    | EUR    | 1309.00  | 1249.00  | 1.048 |
| BESI.AS    | EUR    | 260.80   | 254.90   | 1.023 |
| AMD        | USD    | 386.34   | 355.25   | 1.087 |
| TSM        | USD    | 358.86   | 336.86   | 1.065 |
| ... (21 total) ... |||||
| **Range**  | mixed  | varied   | varied   | **[0.937, 1.147]** |

All ratios near 1.0 regardless of native currency → EUR canonical confirmed.
Had storage been native: KRW ratios would be ~169200% (1/0.000591),
JPY ratios ~18293% (1/0.005467), USD ratios ~117% (1/0.858).

## Implementation

**Helper:** `shared/positions.py::cost_in(avg_cost_eur, target_cur="USD")`
- Returns None if input None
- Returns input if target_cur=EUR (idempotent)
- Otherwise multiplies by `get_fx_rate("EUR", target_cur)`

**Refactored sites (6):**
- `shared/portfolio_metrics.py::compute_portfolio_return_eur` (KPI #6 fallback)
- `shared/positions.py::_enrich_with_live` (FM-10 dette resolved)
- `bot/handlers/positions.py::cmd_portfolio`
- `bot/handlers/portfolio_views.py::positions block`
- `bot/handlers/find.py::_format_position`
- `intelligence/risk_manager.py::_build_portfolio_state` (LLM prompt USD coherence)
- `intelligence/bias_tagger.py::POSITION CONTEXT` (LLM prompt USD coherence)
- `bot/handlers/journal_bias.py::cmd_position_history`

**Tests added:**
- `tests/test_cost_in.py`: 6 Hypothesis property tests
- `tests/test_portfolio_metrics.py`: 2 pre-existing tests rewritten to ADR 005

**Out of ADR 005 scope (audit follow-up):**
- `theses.entry_price/target_partial/target_full/stop_price`: currency
  convention not yet audited (likely mixed by entry path)
- `decisions.price_at_decision`: same
- `position_events.price`, `position_events.pnl`: same
- `positions.realized_pnl`: same

## References

- Commit `1cefee6` — initial morning_brief discovery (Day 14 morning)
- Commit `b601bfd` — core fix + cost_in helper + tests (Day 14)
- Commit `8e345c2` — Group C display label coherence (Day 14)
- Lesson 15 (CONVENTIONS.md §16) — empirical verification applies beyond SQL
