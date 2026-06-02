"""recalib_map -- carte de recalibration des probas brutes du scorer V2.

Strategie user 31/05/2026 point #3a : "apprends comment tes probas brutes
mappent la realite (Platt / isotonic) et corrige-les. Si tes 0,70 resolvent
a 0,60, tu appliques la correction. Le geste classique qui ameliore un
forecaster."

Architecture :
- Fit : a partir de predictions resolues (non-neutral, non-v0) avec
  probability_at_creation + outcome connus, fitte une CalibrationMap
  (isotonic ou Platt) qui mappe raw_prob -> calibrated_prob.
- Apply : sur une nouvelle proba brute du scorer, retourne la version
  corrigee. Si pas assez de data pour fitter (< MIN_N_FIT), retourne raw.
- Refresh : trigger par accumulation (pas calendrier). Refit a chaque
  nouvelle resolution batch (cron weekly via calibration_audit job).

Activation : MIN_N_FIT predictions resolues post-v0. Avant ce seuil :
get_calibrated_prob retourne raw_prob unchanged (cold-start safe).

Integration : appele depuis intelligence/learning.py:resolve_due_predictions
APRES le score V2 mais AVANT le store en DB (correction prospective). Ou
depuis le dashboard pour montrer raw vs calibrated cote a cote. Pas branche
au flux principal en J0 (scaffolding), s'activera quand N >= 30.

Discipline (CONVENTIONS.md "Discipline statistique") :
- Refus de fitter si n < MIN_N_FIT
- Refus de retourner calibrated si raw hors [0.5, 1.0] apres normalisation
  bullish/bearish (cf calibration_audit._normalize_prob)
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import numpy as np

log = logging.getLogger(__name__)

MIN_N_FIT = 30  # idem MIN_N_TOTAL calibration_audit.py
DEFAULT_METHOD: Literal["isotonic", "platt"] = "isotonic"


@dataclass
class CalibrationMap:
    """Carte de recalibration fittee. Wrap un modele sklearn + metadata audit."""

    model: Any  # sklearn IsotonicRegression ou LogisticRegression
    method: Literal["isotonic", "platt"]
    fitted_at: datetime
    n_fit: int
    methodology_version_filter: str  # quels v0/v1/... ont alimente le fit

    def correct(self, raw_prob: float) -> float:
        """Applique la correction. Retourne raw_prob si modele non-fittable.
        Clamp [0.001, 0.999] pour eviter degenerescence."""
        if raw_prob is None:
            return raw_prob
        x = np.array([[raw_prob]])
        if self.method == "isotonic":
            corrected = float(self.model.predict([raw_prob])[0])
        else:  # platt = logistic
            corrected = float(self.model.predict_proba(x)[0, 1])
        return max(0.001, min(0.999, corrected))


def fit_calibration_map(
    cx: sqlite3.Connection,
    method: Literal["isotonic", "platt"] = DEFAULT_METHOD,
    version_filter: str = "v1",
) -> CalibrationMap | None:
    """Fit une CalibrationMap depuis predictions resolues non-neutral non-v0.

    Args:
        cx : connexion sqlite3
        method : 'isotonic' (recommande, monotone, non-parametric) ou 'platt'
                 (logistic regression, parametrique, lisse mais peut violer monotonie)
        version_filter : default 'v1' (cf migration 0021), evolue avec methodo

    Returns:
        CalibrationMap si n >= MIN_N_FIT, sinon None (cold-start safe).
    """
    rows = cx.execute(
        """
        SELECT probability_at_creation AS prob, outcome
        FROM predictions
        WHERE resolved_at IS NOT NULL
          AND outcome IN ('correct', 'incorrect')
          AND probability_at_creation IS NOT NULL
          AND methodology_version = ?
        """,
        (version_filter,),
    ).fetchall()
    n = len(rows)
    if n < MIN_N_FIT:
        log.info(f"recalib_map.fit : n={n} < MIN_N_FIT={MIN_N_FIT}, skip (cold start)")
        return None

    X = np.array([r[0] for r in rows]).reshape(-1, 1)
    y = np.array([1 if r[1] == "correct" else 0 for r in rows])

    if method == "isotonic":
        from sklearn.isotonic import IsotonicRegression

        model = IsotonicRegression(out_of_bounds="clip")
        model.fit(X.ravel(), y)
    else:
        from sklearn.linear_model import LogisticRegression

        model = LogisticRegression(C=1.0)
        model.fit(X, y)

    return CalibrationMap(
        model=model,
        method=method,
        fitted_at=datetime.now(UTC),
        n_fit=n,
        methodology_version_filter=version_filter,
    )


def get_calibrated_prob(
    cx: sqlite3.Connection,
    raw_prob: float,
    method: Literal["isotonic", "platt"] = DEFAULT_METHOD,
) -> float:
    """Helper one-shot : fit (si data suffisante) + correct. Retourne raw_prob
    si insufficient data. Pas optimal pour appels frequents (refit a chaque
    call), use fit_calibration_map + cache externe pour usage production."""
    cmap = fit_calibration_map(cx, method=method)
    if cmap is None:
        return raw_prob
    return cmap.correct(raw_prob)
