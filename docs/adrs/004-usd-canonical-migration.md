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
