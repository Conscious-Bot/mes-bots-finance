"""Backtest wrapper deterministe -- pmorissette/bt 1.2.0 (audit 07/06 nuit).

Source : pmorissette/bt MIT 2.9k stars, built on top of ffn (deja wired
dans shared/portfolio_analytics).

Doctrine USAGE STRICT (anti-L14 #4) :
- bt sert a VALIDER nos regles deterministes existantes (lock_in_detector,
  over_cap_monitor, kill_criteria_monitor) sur historique walk-forward.
- bt NE SERT PAS a "decouvrir la meilleure strategie" en grid search
  multi-params -- ca c'est exactement L14 anti-pattern #4 (TradingAgents /
  FinRL "5 agents -> pick best" deja rejete).

Pattern walk-forward (L16 splits temporels strictes) :
- Splits dates definis AVANT le backtest (cf config/calibration.yaml
  temporal_splits)
- 1 config FIGEE testee sur 5 fenetres
- Resultats agreges + bootstrap CI sur Sharpe / max_dd
- Doc resultat versionne dans docs/backtest_audits/

API publique :
- load_yfinance_history(tickers, start, end) -> pd.DataFrame prices
- run_walk_forward(strategy_factory, prices, splits) -> list[BacktestResult]
- aggregate_walk_forward(results) -> dict (mean/std per metric)

ALPHA stage du repo bt : on use avec rigueur. Tests verrouilles les
invariants principaux pour catch les regressions.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)


def _ensure_bt() -> Any:
    """Lazy import bt avec error clair si manquant."""
    try:
        import bt
        return bt
    except ImportError as e:
        raise RuntimeError(
            "bt requis pour shared.backtest. "
            "pip install bt>=1.2.0 (cf requirements.txt). "
            f"Erreur originale : {e}"
        ) from e


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    """1 fenetre walk-forward : (train_start, train_end, test_start, test_end)."""
    train_start: date
    train_end: date
    test_start: date
    test_end: date

    def label(self) -> str:
        return f"WF_{self.test_start.year}_{self.test_start.month:02d}"


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Resultat d'un backtest sur 1 fenetre."""
    window_label: str
    strategy_name: str
    sharpe: float | None
    sortino: float | None
    max_drawdown: float | None
    total_return: float | None
    cagr: float | None
    n_days: int


def load_yfinance_history(
    tickers: list[str],
    start: str | date,
    end: str | date,
    auto_adjust: bool = True,
) -> pd.DataFrame:
    """Charge prix daily yfinance batch pour la fenetre [start, end].

    Args:
        tickers : liste de symboles yfinance (suffix .PA/.T/.KS supportes).
        start, end : ISO 'YYYY-MM-DD' ou date.
        auto_adjust : applique splits + dividendes (default True, recommande
          pour backtest car les prix bruts ne tiennent pas compte des splits).

    Returns:
        DataFrame indexe par date, colonnes = tickers, valeurs = close.
        Tickers qui fail au fetch sont silencieusement droppes (logged).
    """
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError("yfinance manquant") from e

    df = yf.download(
        tickers=" ".join(tickers) if isinstance(tickers, list) else tickers,
        start=str(start),
        end=str(end),
        interval="1d",
        auto_adjust=auto_adjust,
        progress=False,
        threads=True,
    )
    if df is None or df.empty:
        return pd.DataFrame()

    # df multi-index si len(tickers) > 1
    if isinstance(df.columns, pd.MultiIndex):
        close = df["Close"] if "Close" in df.columns.get_level_values(0) else df
    else:
        if "Close" in df.columns:
            close = df[["Close"]].rename(columns={"Close": tickers[0]})
        else:
            close = df

    # Forward fill puis drop rows entierement NaN
    close = close.ffill().dropna(how="all")
    return close


def build_walk_forward_windows(
    overall_start: date,
    overall_end: date,
    n_splits: int = 5,
    train_years: int = 2,
) -> list[WalkForwardWindow]:
    """Construit n_splits fenetres walk-forward. Chaque fenetre :
    train = train_years annees avant le test, test = sub-period entre splits.

    Args:
        overall_start, overall_end : dates ISO.
        n_splits : nombre de fenetres (default 5).
        train_years : annees de train (default 2).

    Returns:
        Liste de WalkForwardWindow ordonnees chronologiquement.

    Doctrine L16 : les fenetres sont DETERMINISTES, derivees du calendar.
    Pas de tuning de cette decoupe -- 1 config figee per audit.
    """
    from dateutil.relativedelta import relativedelta

    total_days = (overall_end - overall_start).days
    if total_days < (train_years * 365 + 90):
        raise ValueError(
            f"Periode trop courte pour {n_splits} splits + {train_years}y train "
            f"({total_days}j disponibles)"
        )

    # Test windows = decoupe equi-time du reste
    test_period_start = overall_start + relativedelta(years=train_years)
    test_total_days = (overall_end - test_period_start).days
    test_window_days = test_total_days // n_splits

    windows = []
    for i in range(n_splits):
        test_start = test_period_start + pd.Timedelta(days=i * test_window_days)
        test_end = test_period_start + pd.Timedelta(days=(i + 1) * test_window_days)
        train_start = test_start - relativedelta(years=train_years)
        train_end = test_start - pd.Timedelta(days=1)
        windows.append(WalkForwardWindow(
            train_start=train_start.date() if hasattr(train_start, "date") else train_start,
            train_end=train_end.date() if hasattr(train_end, "date") else train_end,
            test_start=test_start.date() if hasattr(test_start, "date") else test_start,
            test_end=test_end.date() if hasattr(test_end, "date") else test_end,
        ))
    return windows


def run_walk_forward(
    strategy_factory: Callable[[str], Any],
    prices: pd.DataFrame,
    windows: list[WalkForwardWindow],
) -> list[BacktestResult]:
    """Lance la strategy sur chaque fenetre walk-forward.

    Args:
        strategy_factory : Callable(window_label) -> bt.Strategy. Reconstruit
          une strategie pour chaque fenetre (etat propre).
        prices : DataFrame prix daily.
        windows : list de WalkForwardWindow.

    Returns:
        Liste de BacktestResult, 1 par fenetre. Echec d'une fenetre = log
        warning + skip (les autres continuent).

    Doctrine : ZERO tuning entre fenetres. Strategy factory utilise des
    params figes en advance (passes via closure).
    """
    bt_mod = _ensure_bt()
    out = []
    for w in windows:
        try:
            # Slice prices to test window
            mask = (prices.index >= pd.Timestamp(w.test_start)) & (
                prices.index <= pd.Timestamp(w.test_end)
            )
            window_prices = prices.loc[mask].dropna(how="all")
            if len(window_prices) < 30:
                log.warning(f"WF {w.label()} : seulement {len(window_prices)}j, skip")
                continue

            strategy = strategy_factory(w.label())
            backtest = bt_mod.Backtest(strategy, window_prices)
            result = bt_mod.run(backtest)

            # Extract stats
            stats = result.stats
            sname = strategy.name
            out.append(BacktestResult(
                window_label=w.label(),
                strategy_name=sname,
                sharpe=_safe_stat(stats, "daily_sharpe", sname),
                sortino=_safe_stat(stats, "daily_sortino", sname),
                max_drawdown=_safe_stat(stats, "max_drawdown", sname),
                total_return=_safe_stat(stats, "total_return", sname),
                cagr=_safe_stat(stats, "cagr", sname),
                n_days=len(window_prices),
            ))
        except Exception as e:
            log.warning(f"WF {w.label()} failed: {type(e).__name__}: {e}")
            continue
    return out


def _safe_stat(stats: pd.DataFrame, key: str, col: str) -> float | None:
    """Helper : extrait stat numerique avec fallback None safe."""
    try:
        val = stats.loc[key][col]
        if pd.isna(val):
            return None
        return float(val)
    except Exception:
        return None


def aggregate_walk_forward(results: list[BacktestResult]) -> dict[str, dict[str, float]]:
    """Agrege les resultats walk-forward : mean/std/min/max par metric.

    Returns:
        dict {metric_name: {mean, std, min, max, n}}.
        N = nombre de fenetres avec metric non-None.

    Doctrine L9 : seul cet aggregate avec mean ET std est interpretable.
    Une seule fenetre = pas un backtest valide.
    """
    if not results:
        return {}

    import numpy as np
    metrics = ("sharpe", "sortino", "max_drawdown", "total_return", "cagr")
    out: dict[str, dict[str, float]] = {}
    for m in metrics:
        vals = [getattr(r, m) for r in results if getattr(r, m) is not None]
        if not vals:
            out[m] = {"n": 0}
            continue
        arr = np.array(vals)
        out[m] = {
            "mean": float(arr.mean()),
            "std": float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
            "min": float(arr.min()),
            "max": float(arr.max()),
            "n": len(vals),
        }
    return out
