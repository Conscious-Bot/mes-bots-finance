"""Macro inputs interface : lit YAML + fetch + z-score signé + freshness.

C'est l'INTERFACE entre le monde external (FRED/yfinance) et l'engine
PARTAGÉ (divergence_engine.py). L'engine ne consomme que ResolvedInput.

V0 walking skeleton : UN seul input wired (HY_OAS via FRED ou fixture).
Les autres inputs viennent au fur et à mesure de C7 (calibration) -- chaque
input ajouté augmente le contrat empiriquement vérifié.

Architecture canonique :
- resolve_macro_inputs(cfg, fixture_path=None) : entry point.
- _resolve_<NAME>(spec, fixture_path) : un par input declared dans YAML.
- Sign-theory appliquée ici (z_signed = z * sign_mult) -- le YAML est
  source unique du signe figé.
- Freshness : max_age_days from YAML.
- z-score : (val - mean) / std vs historique full du fetched range.
"""

from __future__ import annotations

import json
import logging
import statistics
from datetime import UTC, datetime
from pathlib import Path

from intelligence.divergence_schema import ResolvedInput

log = logging.getLogger(__name__)


def _sign_mult(sign_theory: str) -> int:
    """sign-theory -> multiplicateur pour z_signed.

    Convention : tous les sign-theory dans le YAML pointent vers
    "divergence haute" -- donc z_signed > 0 = vers divergence haute.

    Pour 'negative' (low value -> divergence haute, ex HY_OAS tight) :
        sign_mult = -1 -> z_signed = z * -1
        Si val faible, z<0, z_signed = -z = positif ✓
    Pour 'positive' (high value -> divergence haute, ex crowding élevé) :
        sign_mult = +1 -> z_signed = z * +1
        Si val haute, z>0, z_signed = z = positif ✓
    Pour 'neutral' (rare) :
        sign_mult = 0 -> z_signed = 0 (input contribue rien au signe)
    """
    return {"negative": -1, "positive": 1, "neutral": 0}.get(sign_theory, 0)


def _age_days(asof_iso: str) -> float:
    """Jours depuis l'observation. asof format ISO ou YYYY-MM-DD."""
    try:
        # FRED retourne "2026-06-04" (date only)
        if len(asof_iso) == 10:
            dt = datetime.fromisoformat(asof_iso).replace(tzinfo=UTC)
        else:
            dt = datetime.fromisoformat(asof_iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
        delta = datetime.now(UTC) - dt
        return delta.total_seconds() / 86400.0
    except (ValueError, TypeError):
        return float("inf")  # parse fail -> tres vieux -> stale


def _prior_weight(tier: str, priors: dict) -> float:
    """Weight V0 = prior par tier (S/A/B). Post-calibration -> remplacé par
    skill × orthogonalité × fiabilité × stabilité (CALIBRATION_DOCTRINE §1)."""
    return float(priors.get(tier, 0.0))


def _zscore(value: float, history: list[float]) -> float | None:
    """Standard z-score vs full history. Returns None si stdev=0 ou history vide."""
    if not history or len(history) < 2:
        return None
    mean = statistics.mean(history)
    sd = statistics.stdev(history)
    if sd <= 1e-12:
        return None
    return (value - mean) / sd


def _percentile(value: float, history: list[float]) -> float | None:
    """Percentile rank vs history."""
    if not history:
        return None
    below = sum(1 for v in history if v < value)
    return below / len(history) * 100.0


# ─────────────────────────────────────────────────────────────────────────────
# Resolver per input (one function per name declared in YAML)
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_hy_oas(
    spec: dict, priors: dict, fixture_path: str | Path | None = None,
) -> ResolvedInput | None:
    """HY_OAS = ICE BofA US High Yield Index OAS (bp).

    Source : FRED:BAMLH0A0HYM2.
    Sign theory : 'negative' (tight = complaisance late-cycle = divergence haute).
    Tier S.

    fixture_path : si fourni, lit depuis tests/fixtures/hy_oas_fred_*.json
        au lieu de fetch live. Permet tests deterministes.
    """
    obs = None
    if fixture_path:
        path = Path(fixture_path)
        if not path.exists():
            log.warning(f"HY_OAS fixture missing: {path}")
            return None
        try:
            with path.open() as f:
                data = json.load(f)
            obs = data.get("observations", [])
        except (json.JSONDecodeError, OSError) as e:
            log.warning(f"HY_OAS fixture load failed: {e}")
            return None
    else:
        # Live fetch
        try:
            from shared.macro import _fred_series
            obs = _fred_series("BAMLH0A0HYM2", limit=2500)
        except Exception as e:
            log.warning(f"HY_OAS FRED fetch failed: {e}")
            return None

    if not obs:
        return None

    # Parse valid observations (.value can be "." for missing days in FRED)
    parsed = []
    for o in obs:
        v = o.get("value")
        if v is None or v == "." or v == "":
            continue
        try:
            parsed.append({"date": o["date"], "value": float(v)})
        except (TypeError, ValueError):
            continue
    if not parsed:
        return None

    # FRED retourne typiquement desc (recent first). Latest = parsed[0] si desc,
    # sinon parsed[-1]. Heuristique : compare 2 dates.
    if len(parsed) >= 2 and parsed[0]["date"] > parsed[-1]["date"]:
        latest = parsed[0]
        history = [p["value"] for p in parsed]
    else:
        latest = parsed[-1]
        history = [p["value"] for p in parsed]

    raw_value = latest["value"]
    z = _zscore(raw_value, history)
    if z is None:
        log.warning("HY_OAS: zscore None (history insufficient or zero stdev)")
        return None

    sign_mult = _sign_mult(spec["sign"])
    z_signed = z * sign_mult

    # Freshness check
    age = _age_days(latest["date"])
    max_age = float(spec.get("max_age_days", 7))
    fresh = age <= max_age

    # Delta T-1 (basic : last vs prev)
    delta = None
    if len(parsed) >= 2:
        delta = parsed[0]["value"] - parsed[1]["value"] if parsed[0]["date"] > parsed[-1]["date"] else parsed[-1]["value"] - parsed[-2]["value"]

    pct = _percentile(raw_value, history)
    weight = _prior_weight(spec["tier"], priors)

    return ResolvedInput(
        name=spec["name"],
        bucket="croyance_pricee",
        tier=spec["tier"],
        sign_theory=spec["sign"],
        z_score_signed=z_signed,
        weight=weight,
        asof=latest["date"],
        source=spec["source"],
        fresh=fresh,
        raw_value=raw_value,
        percentile=pct,
        delta=delta,
    )


# Registry : name -> resolver function
_RESOLVERS = {
    "HY_OAS": _resolve_hy_oas,
    # Les autres viennent au fur et a mesure (T10Y2Y_curve, credit_impulse, etc.)
    # Quand un name n'a pas de resolver, resolve_macro_inputs skip avec warning.
}


def resolve_macro_inputs(
    cfg: dict, fixture_path: str | Path | None = None,
) -> list[ResolvedInput]:
    """Resolve tous les inputs macro declares dans config/divergence.yaml.

    Args:
        cfg : dict parse de config/divergence.yaml (yaml.safe_load).
        fixture_path : chemin vers fixture HY_OAS JSON pour tests deterministes.
            Si None, fetch live via FRED.

    Returns:
        list[ResolvedInput] -- skipped silently les inputs sans resolver
        (V0 walking skeleton, on en wire UN seul ; les autres en C7).
    """
    priors = cfg.get("priors", {})
    out: list[ResolvedInput] = []
    for bucket in ("croyance_pricee", "realite_livrable", "phase_reflexive"):
        for spec in cfg.get("inputs", {}).get("macro", {}).get(bucket, []):
            name = spec["name"]
            resolver = _RESOLVERS.get(name)
            if not resolver:
                log.debug(f"macro_inputs: no resolver for {name} (V0 skip, C7 wire)")
                continue
            try:
                resolved = resolver(spec, priors, fixture_path)
                if resolved:
                    out.append(resolved)
            except Exception as e:
                log.warning(f"macro_inputs: {name} resolve failed: {e}")
    return out
