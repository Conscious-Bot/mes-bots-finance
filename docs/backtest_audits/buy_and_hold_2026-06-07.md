# Backtest buy-and-hold book vs equal-weight (2026-06-07)

**Date audit** : 2026-06-07
**Periode** : 2022-06-07 → 2026-06-07 (4y)
**Fenetres WF** : 5 (train_years=2)
**Tickers** : 26 (26 en book DB, 26 resolus yfinance)
**Tool** : shared/backtest.py (wrapper bt 1.2.0) + shared/portfolio_analytics.py (ffn)

## Comparaison aggreges walk-forward

| Metric | Book weighted (qty proxy) | Equal weight baseline | Delta |
|---|---|---|---|
| Sharpe | +1.728 ± 1.090 (N=5) | +1.798 ± 1.382 (N=5) | — |
| Sortino | +2.649 ± 1.681 (N=5) | +2.785 ± 2.227 (N=5) | — |
| Max DD | -0.154 ± 0.068 (N=5) | -0.152 ± 0.049 (N=5) | — |
| Total return | +0.188 ± 0.131 (N=5) | +0.210 ± 0.174 (N=5) | — |
| CAGR | +0.564 ± 0.421 (N=5) | +0.657 ± 0.556 (N=5) | — |

## Resultats par fenetre

### Book weighted

| Fenetre | Sharpe | Sortino | Max DD | Total return | CAGR | N days |
|---|---|---|---|---|---|---|
| WF_2024_06 | 1.021 | 1.443 | -0.256 | 0.133 | 0.365 | 105 |
| WF_2024_10 | 0.250 | 0.376 | -0.116 | 0.013 | 0.032 | 104 |
| WF_2025_03 | 2.728 | 4.108 | -0.191 | 0.334 | 1.047 | 105 |
| WF_2025_08 | 1.889 | 3.149 | -0.119 | 0.158 | 0.441 | 104 |
| WF_2026_01 | 2.751 | 4.167 | -0.088 | 0.299 | 0.934 | 105 |

### Equal weight

| Fenetre | Sharpe | Sortino | Max DD | Total return | CAGR | N days |
|---|---|---|---|---|---|---|
| WF_2024_06 | 0.361 | 0.471 | -0.221 | 0.025 | 0.064 | 105 |
| WF_2024_10 | 0.260 | 0.354 | -0.159 | 0.014 | 0.035 | 104 |
| WF_2025_03 | 2.561 | 3.962 | -0.170 | 0.319 | 0.991 | 105 |
| WF_2025_08 | 3.200 | 5.213 | -0.106 | 0.349 | 1.103 | 104 |
| WF_2026_01 | 2.611 | 3.927 | -0.102 | 0.341 | 1.093 | 105 |

## Limites

- Mix devises native sur prix (yen + dollar + euro additionnes brutalement).
  Ratios CAGR/Sharpe/Drawdown restent valides relatifs, total absolu pas
  significatif.
- N=5 fenetres x 1 strategy. Bootstrap CI pas implementé ici,
  sample size petit pour conclusion robuste statistique.
- BAH strict (zero rebalance) pour les 2 strategies. Real-world : trim +
  add positions modifie la realite vs ce backtest.
- Pas de cout transaction modeles (BAH = neutral, mais a documenter pour
  futures strats avec rebalance).

## Doctrine respectee

- L9 LESSONS : agreges seuls interpretables, 1 seule fenetre = pas valide
- L14 anti-pattern #4 : 2 strategies FIGEES, pas grid search multi-config
- L16 splits temporels : fenetres derivees du calendar, pas tunables

## Reproduction

```
python3 scripts/backtest_buy_and_hold_book.py --years 4 --splits 5
```
