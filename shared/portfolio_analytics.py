"""Portfolio analytics deterministe -- wrapper ffn (Phase post-audit 07/06).

Source : pmorissette/ffn 1.1.5 (MIT, 2.6k stars, pandas-native, deterministe).
Audit 07/06 nuit : 9/10 utilite PRESAGE, couvre ~85% du gap Heimdall Performance
panel. Cf docs/LESSONS.md L14 anti-patterns -- ffn passe propre (analytics pure,
zero LLM, zero ML predictive, zero RL).

Doctrine :
- TOUTES les fonctions sont deterministes sur input historique. Pas de
  prediction (anti-doctrine #1 PRESAGE : "discipline mecanisee pas alpha
  predictif"). On mesure le passe, on ne prevoit pas le futur.
- pandas in / pandas out (ou dict pour metriques aggregees). Pas de Pydantic
  wrapper -- ces fonctions servent la couche presentation, pas le ledger.
- rf annual = annualized risk-free rate scalar (ex 0.025 pour 2.5%).
  Annualization factor = 252 (jours de bourse) par defaut.

Couverture (cf audit) :
- Equity curve : compute_equity_curve()
- Drawdown : compute_drawdown_series() + compute_drawdown_events()
- Perf metrics aggregees : compute_perf_metrics() -> dict (CAGR, total_return,
  Sharpe, Sortino, Calmar, max_dd, volatility_annual, best_day, worst_day)
- Rolling vol : compute_rolling_volatility()
- vs benchmark : compute_information_ratio()
- VaR / CVaR : compute_value_at_risk() / compute_conditional_var()

Lecteurs probables :
- dashboard/render.py Performance & regime panel (Heimdall upgrade post J-day)
- /audit Telegram handler enrichi (CAGR + Sharpe ligne)
- scripts d'analyse one-off

Lecteurs NON-attendus :
- intelligence/ (decision-making) -- ces fonctions sont retrospectives, ne
  doivent pas alimenter de decision predictive
- intelligence/signal_scorer_v2 -- garder Brier ledger orthogonal
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ffn est lazy-imported : eviter de bloquer le boot du bot si ffn install fail
# en envt particulier (ex Hetzner ARM sans wheel ffn).


def _ensure_ffn() -> Any:
    """Lazy import ffn avec error message clair si manquant."""
    try:
        import ffn
        return ffn
    except ImportError as e:
        raise RuntimeError(
            "ffn requis pour shared.portfolio_analytics. "
            "pip install ffn>=1.1.5 (cf requirements.txt). "
            f"Erreur originale : {e}"
        ) from e


# === Equity curve ==========================================================


def compute_equity_curve(prices: pd.Series, base: float = 100.0) -> pd.Series:
    """Rebase une serie de prix sur valeur initiale `base`.

    Args:
        prices : serie de prix indexee par date (croissant).
        base : valeur initiale (default 100).

    Returns:
        Serie rebased : prices[0] -> base, prices[t] -> base * prices[t]/prices[0].
        Preserve l'index original et la longueur de prices.

    Raises:
        ValueError si prices vide ou contient NaN au debut (impossible de
        rebaser sur point indefini).

    Note : ffn.core.to_price_index requiere des returns (pas prices) + recompose
    via cumprod, ce qui perd le premier point + traite differemment les NaN.
    On fait du rebase direct ici pour preserver la signature pandas-friendly.
    """
    if prices.empty:
        raise ValueError("prices empty -- impossible de calculer equity curve")
    if pd.isna(prices.iloc[0]):
        raise ValueError("prices[0] est NaN -- rebase impossible")
    return prices / prices.iloc[0] * base


# === Drawdown ===============================================================


def compute_drawdown_series(prices: pd.Series) -> pd.Series:
    """Serie de drawdown running (% sous le pic precedent).

    DD = (price[t] - running_max[t]) / running_max[t]. Toujours <= 0.
    Returns 0 quand on est sur un nouveau pic.
    """
    if prices.empty:
        raise ValueError("prices empty")
    ffn_mod = _ensure_ffn()
    return ffn_mod.core.to_drawdown_series(prices)


def compute_drawdown_events(prices: pd.Series) -> pd.DataFrame | None:
    """Catalog des drawdown events (start, end, duration, depth).

    Returns:
        DataFrame avec colonnes (start, end, Length, drawdown), ou None si
        aucun event detectable (serie monotone croissante, pas de DD).
    """
    if prices.empty:
        raise ValueError("prices empty")
    ffn_mod = _ensure_ffn()
    dd_series = ffn_mod.core.to_drawdown_series(prices)
    return ffn_mod.core.drawdown_details(dd_series)


# === Metriques aggregees ===================================================


def compute_perf_metrics(
    prices: pd.Series, rf_annual: float = 0.0
) -> dict[str, float | None]:
    """Bloc complet de metriques performance d'une serie de prix.

    Args:
        prices : serie de prix daily.
        rf_annual : risk-free rate annualise (ex 0.025 pour 2.5%).

    Returns:
        dict avec :
        - cagr (compound annual growth)
        - total_return (cumulative)
        - max_drawdown (negative)
        - volatility_annual (daily vol annualisee, sqrt(252))
        - sharpe (daily Sharpe annualise)
        - sortino (downside vol only)
        - calmar (CAGR / |max_dd|)
        - best_day, worst_day (return single best/worst)

    None pour les metriques non calculables (serie trop courte).
    """
    if prices.empty or len(prices) < 2:
        return {
            "cagr": None, "total_return": None, "max_drawdown": None,
            "volatility_annual": None, "sharpe": None, "sortino": None,
            "calmar": None, "best_day": None, "worst_day": None,
        }
    ffn_mod = _ensure_ffn()
    try:
        stats = ffn_mod.core.calc_perf_stats(prices, risk_free_rate=rf_annual)
        return {
            "cagr": float(stats.cagr) if stats.cagr is not None else None,
            "total_return": float(stats.total_return) if stats.total_return is not None else None,
            "max_drawdown": float(stats.max_drawdown) if stats.max_drawdown is not None else None,
            "volatility_annual": float(stats.daily_vol) if stats.daily_vol is not None else None,
            "sharpe": float(stats.daily_sharpe) if stats.daily_sharpe is not None else None,
            "sortino": float(stats.daily_sortino) if stats.daily_sortino is not None else None,
            "calmar": float(stats.calmar) if stats.calmar is not None else None,
            "best_day": float(stats.best_day) if stats.best_day is not None else None,
            "worst_day": float(stats.worst_day) if stats.worst_day is not None else None,
        }
    except Exception as e:
        log.warning(f"compute_perf_metrics failed : {type(e).__name__}: {e}")
        return dict.fromkeys(("cagr", "total_return", "max_drawdown", "volatility_annual", "sharpe", "sortino", "calmar", "best_day", "worst_day"))


# === Rolling volatility =====================================================


def compute_rolling_volatility(
    returns: pd.Series, window: int = 20, annualize: bool = True
) -> pd.Series:
    """Volatilite rolling sur fenetre `window` jours.

    Args:
        returns : serie de returns simples (pas log).
        window : fenetre rolling en jours (default 20 = ~1 mois bourse).
        annualize : multiplie par sqrt(252) si True.

    Returns:
        Serie de vol rolling, NaN sur les `window-1` premiers points.
    """
    if returns.empty:
        raise ValueError("returns empty")
    if window <= 0:
        raise ValueError(f"window doit etre > 0, got {window}")
    factor = np.sqrt(252) if annualize else 1.0
    return returns.rolling(window=window).std() * factor


# === Information ratio vs benchmark =========================================


def compute_information_ratio(
    returns: pd.Series, benchmark_returns: pd.Series
) -> float | None:
    """IR = mean(excess returns) / std(excess returns), annualise sqrt(252).

    excess = returns - benchmark_returns.

    Args:
        returns : portfolio returns.
        benchmark_returns : benchmark returns (meme frequence + alignment date).

    Returns:
        Information ratio annualise, None si std excess == 0 ou series vides.
    """
    if returns.empty or benchmark_returns.empty:
        return None
    aligned_p, aligned_b = returns.align(benchmark_returns, join="inner")
    if len(aligned_p) < 2:
        return None
    excess = aligned_p - aligned_b
    std = excess.std()
    if std == 0 or pd.isna(std):
        return None
    return float(excess.mean() / std * np.sqrt(252))


# === Value at Risk + Conditional VaR ========================================


def compute_value_at_risk(returns: pd.Series, alpha: float = 0.05) -> float | None:
    """Historical VaR au niveau (1-alpha). Default alpha=0.05 -> VaR 95%.

    VaR = quantile alpha des returns (negatif typically).

    Returns:
        VaR negative (perte potentielle), None si returns < 2 points.
    """
    if returns.empty or len(returns) < 2:
        return None
    if not 0 < alpha < 1:
        raise ValueError(f"alpha doit etre dans (0, 1), got {alpha}")
    q = returns.quantile(alpha)
    return float(q) if not pd.isna(q) else None


def compute_conditional_var(returns: pd.Series, alpha: float = 0.05) -> float | None:
    """Conditional VaR (= Expected Shortfall) au niveau (1-alpha).

    CVaR = mean(returns | returns <= VaR_alpha). Toujours <= VaR (perte plus
    severe conditionnellement au depassement du seuil).

    Returns:
        CVaR negative, None si pas de returns sous le seuil VaR.
    """
    if returns.empty or len(returns) < 2:
        return None
    if not 0 < alpha < 1:
        raise ValueError(f"alpha doit etre dans (0, 1), got {alpha}")
    var_q = returns.quantile(alpha)
    tail = returns[returns <= var_q]
    if tail.empty:
        return None
    return float(tail.mean())
