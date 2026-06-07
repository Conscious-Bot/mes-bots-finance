"""Backtest buy-and-hold vs equal-weight sur tes positions DB actuelles.

Usage : python3 scripts/backtest_buy_and_hold_book.py [--years N]

Doctrine (cf shared/backtest.py + L14 anti-pattern #4) :
- 2 strategies FIGEES (pas de grid search) : ton book actuel (qty * close)
  vs equal-weight buy-and-hold.
- Walk-forward 5 fenetres deterministes sur les N annees demandees.
- Output : docs/backtest_audits/buy_and_hold_<date>.md versionne.

Pas un guide de strategie. Juste : "qu'aurait fait un equi-weight sur tes
tickers actuels vs ta repartition ponderee actuelle ?". Eclaire le drift
entre sizing intuitif et baseline mecanique.

Limites :
- Mix devises native (cf KNOWN-GAP Performance panel) : ratios valides,
  total absolu mixte.
- 5 fenetres x 1 strategy = N=5. Bootstrap CI pas implementé ici, sample
  size petit. Pour stat solide, etendre window count.
- Pas de cout transaction modeles (les 2 strats sont BAH donc neutre vs
  comparison, mais a documenter pour futures strats avec rebalance).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backtest_buy_and_hold")


def _load_open_positions() -> list[tuple[str, float]]:
    """Lit positions ouvertes (ticker, qty) depuis DB."""
    from shared import storage
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT ticker, qty FROM positions WHERE status='open' AND qty > 0"
        ).fetchall()
    return [(r[0], float(r[1])) for r in rows]


def _strategy_factory_book_weighted(qtys: dict[str, float]):
    """Factory : strategy ponderee par qty (proxy ta repartition actuelle).

    Approximation : on prend les qty actuelles comme weights initiaux, puis
    buy-and-hold (zero rebalance). Sur des periodes longues, le drift de
    poids n'est PAS recalcule (BAH strict).
    """
    import bt
    total_q = sum(qtys.values())
    if total_q == 0:
        raise ValueError("qtys somme = 0")
    weights = {t: q / total_q for t, q in qtys.items()}

    def factory(label: str):
        return bt.Strategy(
            f"book_weighted_{label}",
            [
                bt.algos.RunOnce(),
                bt.algos.SelectAll(),
                bt.algos.WeighSpecified(**weights),
                bt.algos.Rebalance(),
            ],
        )
    return factory


def _strategy_factory_equal_weight():
    """Factory : strategy equal-weight buy-and-hold (baseline mecanique)."""
    import bt

    def factory(label: str):
        return bt.Strategy(
            f"equal_weight_{label}",
            [
                bt.algos.RunOnce(),
                bt.algos.SelectAll(),
                bt.algos.WeighEqually(),
                bt.algos.Rebalance(),
            ],
        )
    return factory


def _format_metric(metric_dict: dict) -> str:
    """Format une metric aggregee pour markdown."""
    n = metric_dict.get("n", 0)
    if n == 0:
        return "—"
    m = metric_dict.get("mean")
    s = metric_dict.get("std", 0.0)
    return f"{m:+.3f} ± {s:.3f} (N={n})"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=4, help="annees historique (default 4)")
    parser.add_argument("--splits", type=int, default=5, help="nombre fenetres WF (default 5)")
    parser.add_argument("--output-dir", default="docs/backtest_audits",
                        help="dossier output markdown")
    args = parser.parse_args()

    from shared.backtest import (
        aggregate_walk_forward,
        build_walk_forward_windows,
        load_yfinance_history,
        run_walk_forward,
    )

    positions = _load_open_positions()
    if not positions:
        log.error("Aucune position ouverte en DB")
        return 1

    tickers = [t for t, _q in positions]
    qtys = dict(positions)
    log.info(f"{len(tickers)} positions ouvertes : {tickers[:5]}...")

    # Periode historique
    end = date.today()
    start = date(end.year - args.years, end.month, end.day)
    log.info(f"Periode {start} -> {end} ({args.years}y)")

    # Walk-forward windows
    try:
        windows = build_walk_forward_windows(
            overall_start=start, overall_end=end,
            n_splits=args.splits, train_years=2,
        )
    except ValueError as e:
        log.error(f"build_walk_forward FAILED : {e}")
        return 1
    log.info(f"{len(windows)} fenetres WF : {[w.label() for w in windows]}")

    # Yfinance batch
    log.info("Fetch yfinance batch (peut prendre 30-60s pour {len(tickers)} tickers)")
    prices = load_yfinance_history(tickers, start=start, end=end)
    if prices.empty:
        log.error("yfinance batch retourne empty")
        return 1
    log.info(f"prices shape : {prices.shape}")
    actual_tickers = list(prices.columns)
    # Filter qtys to tickers qu'on a effectivement
    qtys_filtered = {t: qtys[t] for t in actual_tickers if t in qtys}
    log.info(f"{len(qtys_filtered)} tickers matches yfinance / book")

    # Run 2 strategies
    log.info("Running book_weighted strategy...")
    book_results = run_walk_forward(
        _strategy_factory_book_weighted(qtys_filtered),
        prices, windows,
    )
    log.info(f"book_weighted : {len(book_results)} fenetres OK")

    log.info("Running equal_weight baseline...")
    ew_results = run_walk_forward(
        _strategy_factory_equal_weight(),
        prices, windows,
    )
    log.info(f"equal_weight : {len(ew_results)} fenetres OK")

    book_agg = aggregate_walk_forward(book_results)
    ew_agg = aggregate_walk_forward(ew_results)

    # Output markdown
    output_dir = _REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = output_dir / f"buy_and_hold_{date_str}.md"

    md = f"""# Backtest buy-and-hold book vs equal-weight ({date_str})

**Date audit** : {date_str}
**Periode** : {start} → {end} ({args.years}y)
**Fenetres WF** : {len(windows)} (train_years=2)
**Tickers** : {len(actual_tickers)} ({len(qtys)} en book DB, {len(actual_tickers)} resolus yfinance)
**Tool** : shared/backtest.py (wrapper bt 1.2.0) + shared/portfolio_analytics.py (ffn)

## Comparaison aggreges walk-forward

| Metric | Book weighted (qty proxy) | Equal weight baseline | Delta |
|---|---|---|---|
| Sharpe | {_format_metric(book_agg.get('sharpe', {}))} | {_format_metric(ew_agg.get('sharpe', {}))} | — |
| Sortino | {_format_metric(book_agg.get('sortino', {}))} | {_format_metric(ew_agg.get('sortino', {}))} | — |
| Max DD | {_format_metric(book_agg.get('max_drawdown', {}))} | {_format_metric(ew_agg.get('max_drawdown', {}))} | — |
| Total return | {_format_metric(book_agg.get('total_return', {}))} | {_format_metric(ew_agg.get('total_return', {}))} | — |
| CAGR | {_format_metric(book_agg.get('cagr', {}))} | {_format_metric(ew_agg.get('cagr', {}))} | — |

## Resultats par fenetre

### Book weighted

| Fenetre | Sharpe | Sortino | Max DD | Total return | CAGR | N days |
|---|---|---|---|---|---|---|
"""
    for r in book_results:
        md += (
            f"| {r.window_label} | "
            f"{r.sharpe if r.sharpe is not None else '—':.3f} | "
            f"{r.sortino if r.sortino is not None else '—':.3f} | "
            f"{r.max_drawdown if r.max_drawdown is not None else '—':.3f} | "
            f"{r.total_return if r.total_return is not None else '—':.3f} | "
            f"{r.cagr if r.cagr is not None else '—':.3f} | "
            f"{r.n_days} |\n"
        )

    md += """
### Equal weight

| Fenetre | Sharpe | Sortino | Max DD | Total return | CAGR | N days |
|---|---|---|---|---|---|---|
"""
    for r in ew_results:
        md += (
            f"| {r.window_label} | "
            f"{r.sharpe if r.sharpe is not None else '—':.3f} | "
            f"{r.sortino if r.sortino is not None else '—':.3f} | "
            f"{r.max_drawdown if r.max_drawdown is not None else '—':.3f} | "
            f"{r.total_return if r.total_return is not None else '—':.3f} | "
            f"{r.cagr if r.cagr is not None else '—':.3f} | "
            f"{r.n_days} |\n"
        )

    md += f"""
## Limites

- Mix devises native sur prix (yen + dollar + euro additionnes brutalement).
  Ratios CAGR/Sharpe/Drawdown restent valides relatifs, total absolu pas
  significatif.
- N={len(windows)} fenetres x 1 strategy. Bootstrap CI pas implementé ici,
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
python3 scripts/backtest_buy_and_hold_book.py --years {args.years} --splits {args.splits}
```
"""

    output_path.write_text(md)
    log.info(f"AUDIT ecrit : {output_path}")
    print()
    print(f"=== AUDIT : {output_path} ===")
    print(f"book_weighted Sharpe : {_format_metric(book_agg.get('sharpe', {}))}")
    print(f"equal_weight Sharpe  : {_format_metric(ew_agg.get('sharpe', {}))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
