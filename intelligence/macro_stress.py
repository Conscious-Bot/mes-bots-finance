"""Macro stress scorer — courbe de crise pondérée par famille, fail-closed.

Source UNIQUE des poids/normalisation : config/presage_macro_stress.yaml.
UN seul calcul traçable : Score = Σ_familles[ w_fam × Σ_indic_valides(w_intra_renorm
× signal) ] borné 0-100. L'état DÉRIVE du score (bandes) — plus de contradiction
"BROKEN affiché / STRESS calculé / P4=0".

Doctrine (cf advisor 27/06) :
- Poids = track record HISTORIQUE multi-régimes, pas l'intensité du jour. Oracles
  (courbe, crédit) lourds ; coïncidents (VIX, FX, momentum) légers.
- FAIL-CLOSED L15 : donnée cassée (hors plausible) ou stale → EXCLUE + drapeau,
  JAMAIS interprétée comme calme. Un faux négatif silencieux détruit la véracité.
- Effet de seuil NON-LINÉAIRE légitime (régime), PAS de prime d'importance (double
  comptage). Au-delà de nonlinear_threshold, la contribution accélère ×1.5.

API :
- load_model() -> dict (validé)
- normalize(v, floor, ceiling) -> float [0,1]
- compute_stress(readings) -> dict  (PURE, testable)
- current_readings() -> dict  (lit debt_signals)
- macro_stress_now() -> dict  (current_readings -> compute_stress)
"""

from __future__ import annotations

import functools
import math
from pathlib import Path
from typing import Any

import yaml

_YAML_PATH = Path(__file__).parent.parent / "config" / "presage_macro_stress.yaml"

# Tolérance de fraîcheur par source (jours). Données marché = quotidien serré ;
# macro lente = mensuel. Au-delà → stale → exclu fail-closed.
_STALE_DAYS = {
    # tier-1 quotidien : 4j. tier-2 hebdo : 10j. tier-3 mensuel : 45j.
    "HY_OAS": 4, "MOVE": 4, "TYX": 4, "VIX": 4, "BTC_drawdown180": 4,
    "Gold": 4, "USDJPY": 4, "DXY": 4,
    "T10Y2Y": 10, "BankReserves": 10, "KRE": 10, "CopperGold": 10,
    "FedBalance_yoy": 45, "CoreCPI": 45, "MfgIP_yoy": 45,
}

# Accélération au-delà du seuil non-linéaire (changement de régime).
_NONLINEAR_ACCEL = 1.5


class MacroStressError(Exception):
    """Spec incohérente ou invariant violé. Jamais de défaut silencieux."""


@functools.lru_cache(maxsize=1)
def load_model() -> dict[str, Any]:
    """Charge + VALIDE la spec (fail-closed). Σ family.weight==100, Σ intra==100."""
    if not _YAML_PATH.exists():
        raise MacroStressError(f"spec absente : {_YAML_PATH}")
    data = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8"))
    fams = data.get("families") or {}
    if not fams:
        raise MacroStressError("aucune famille dans la spec")
    fam_sum = sum(f["weight"] for f in fams.values())
    if fam_sum != 100:
        raise MacroStressError(f"Σ family.weight = {fam_sum} != 100")
    for fname, f in fams.items():
        inds = f.get("indicators") or {}
        if not inds:
            raise MacroStressError(f"famille {fname} sans indicateur")
        isum = sum(i["intra_weight"] for i in inds.values())
        if isum != 100:
            raise MacroStressError(f"famille {fname} : Σ intra_weight = {isum} != 100")
        for iname, ind in inds.items():
            for k in ("stress_floor", "stress_ceiling"):
                if k not in ind:
                    raise MacroStressError(f"{fname}/{iname} : {k} manquant")
    bands = data.get("bands") or {}
    for b in ("stable", "stressed", "fragile", "broken"):
        if b not in bands:
            raise MacroStressError(f"bande {b} manquante")
    return data


def normalize(v: float, floor: float, ceiling: float) -> float:
    """[0,1] : 0 au floor (calme), 1 au ceiling (stress max). floor>ceiling =
    'plus bas = plus de stress' (ex. pente, réserves). Clampé."""
    if ceiling == floor:
        return 0.0
    t = (v - floor) / (ceiling - floor)
    return max(0.0, min(1.0, t))


def _apply_nonlinear(base: float, ind: dict) -> float:
    """Au-delà de nonlinear_threshold (en valeur), la contribution accélère ×1.5
    (changement de régime, pas linéaire). Capé à 1."""
    nlt = ind.get("nonlinear_threshold")
    if nlt is None:
        return base
    nt = normalize(nlt, ind["stress_floor"], ind["stress_ceiling"])
    if base <= nt:
        return base
    return min(1.0, nt + (base - nt) * _NONLINEAR_ACCEL)


def _validity(source: str | None, value: float | None, age_days: float | None,
              ind: dict) -> tuple[bool, str]:
    """Fail-closed : (valide?, raison_exclusion). Donnée cassée/stale/absente =
    EXCLUE, jamais lue comme calme."""
    if source is None:
        return False, "non-wiré"
    if value is None:
        return False, "no-data"
    # NaN/inf : math NE peut PAS être comparé (NaN < x == False) -> faux négatif
    # silencieux si non attrapé EXPLICITEMENT. Cassé, jamais calme.
    if not isinstance(value, (int, float)) or math.isnan(value) or math.isinf(value):
        return False, "cassé (NaN/inf/type)"
    pmin, pmax = ind.get("plausible_min"), ind.get("plausible_max")
    if pmin is not None and value < pmin:
        return False, f"cassé (<{pmin})"
    if pmax is not None and value > pmax:
        return False, f"cassé (>{pmax})"
    tol = _STALE_DAYS.get(source, 30)
    if age_days is not None and age_days > tol:
        return False, f"stale (>{tol}j)"
    return True, ""


def compute_stress(readings: dict[str, tuple[float | None, float | None]]) -> dict:
    """PURE. readings = {source: (value, age_days)}. Retourne la courbe + l'état +
    le détail par famille/indicateur + les exclusions fail-closed."""
    model = load_model()
    fams = model["families"]
    fam_results: list[dict] = []
    excluded: list[dict] = []
    n_valid = n_total = 0

    eff_fam_weight_sum = 0.0
    weighted_accum = 0.0

    for fname, f in fams.items():
        inds = f["indicators"]
        valid_intra: list[tuple[str, float, float]] = []  # (name, intra_w, signal)
        for iname, ind in inds.items():
            n_total += 1
            src = ind.get("source")
            value, age = readings.get(src, (None, None)) if src else (None, None)
            ok, reason = _validity(src, value, age, ind)
            if not ok:
                excluded.append({"family": fname, "indicator": iname,
                                 "source": src, "value": value, "reason": reason})
                continue
            n_valid += 1
            base = normalize(value, ind["stress_floor"], ind["stress_ceiling"])
            signal = _apply_nonlinear(base, ind)
            valid_intra.append((iname, ind["intra_weight"], signal))

        if not valid_intra:
            fam_results.append({"family": fname, "weight": f["weight"],
                                "signal": None, "valid": 0,
                                "n": len(inds), "excluded_all": True})
            continue
        # renormalise les poids intra parmi les indicateurs VALIDES
        iw_sum = sum(w for _, w, _ in valid_intra)
        fam_signal = sum(w / iw_sum * s for _, w, s in valid_intra)
        fam_results.append({"family": fname, "weight": f["weight"],
                            "signal": round(fam_signal, 4), "valid": len(valid_intra),
                            "n": len(inds), "excluded_all": False,
                            "contrib_indics": [
                                {"indicator": n, "intra": w, "signal": round(s, 4)}
                                for n, w, s in valid_intra]})
        eff_fam_weight_sum += f["weight"]
        weighted_accum += f["weight"] * fam_signal

    # courbe 0-100, renormalisée sur les familles ayant ≥1 indicateur valide
    if eff_fam_weight_sum <= 0:
        score = None
    else:
        score = round(weighted_accum / eff_fam_weight_sum * 100, 1)

    state = _state_from_score(score, model["bands"]) if score is not None else "NO-DATA"

    return {
        "score": score,
        "state": state,
        "n_valid": n_valid,
        "n_total": n_total,
        "coverage_pct": round(eff_fam_weight_sum, 0),  # % du poids couvert par données valides
        "families": fam_results,
        "excluded": excluded,
    }


def _state_from_score(score: float, bands: dict) -> str:
    """UN seul état dérivé du score. Pas de chemin parallèle."""
    for label in ("broken", "fragile", "stressed", "stable"):
        lo, hi = bands[label]
        if lo <= score <= hi if label == "broken" else lo <= score < hi:
            return label.upper()
    return "STABLE"


def current_readings() -> dict[str, tuple[float | None, float | None]]:
    """Lit la dernière valeur + âge (jours) par source depuis debt_signals."""
    import datetime as dt

    from shared import storage

    out: dict[str, tuple[float | None, float | None]] = {}
    now = dt.datetime.now(dt.UTC)
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT indicator_name, value, timestamp FROM debt_signals "
            "WHERE id IN (SELECT MAX(id) FROM debt_signals GROUP BY indicator_name)"
        ).fetchall()
    for name, value, ts in rows:
        age = None
        try:
            t = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.UTC)
            age = (now - t).total_seconds() / 86400.0
        except Exception:
            age = float("inf")
        out[name] = (value, age)
    return out


def macro_stress_now() -> dict:
    """Score de crise live : current_readings -> compute_stress."""
    return compute_stress(current_readings())
