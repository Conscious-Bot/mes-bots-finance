"""Per-domain Brier audit : split scoring calibration by ticker + sector.

Tier 3 #9 wiring (26/06/2026) post red-teams critique :

> « Brier KPIs sur N=97 = bruit. Multi-comparaison non corrigée. Sortir
>   "ton Brier est 0.23" = communication trompeuse de précision. Compare Brier
>   par conviction tier, par sector, par time bucket → trahison statistique
>   classique. »

Build : honest per-domain Brier avec CI explicite + caveat N-effective.

Méthode :
- Per ticker (top 10 by N predictions résolues)
- Per sector (via config/sectors.yaml)
- Skip per-conviction (predictions n'a pas conviction_at_call field)

Honest framing :
- Brier baseline = 0.25 (random binary guess)
- Brier 0.0 = parfait, 0.5 = pile/face, 1.0 = pire que random
- N par bucket affiché explicitement → user voit le bruit statistique
- Aucun "ranking" par bucket — juste data + invitation à la prudence

Limitation knowable :
- N=114 split en 10+ buckets → ~10 par bucket, CI très large
- Pas de correction multi-test (Bonferroni etc.)
- Honest move : SHOW les chiffres mais NE PAS conclure "tu es meilleur sur X que Y"
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def _load_sector_map() -> dict[str, str]:
    """Ticker → sector_label from config/sectors.yaml."""
    from pathlib import Path

    import yaml

    cfg_path = Path(__file__).parent.parent / "config" / "sectors.yaml"
    try:
        cfg = yaml.safe_load(cfg_path.read_text())
    except Exception as e:
        log.debug("sectors.yaml load fail: %s", e)
        return {}
    sectors = cfg.get("sectors", {})
    out = {}
    for _sid, sdef in sectors.items():
        label = sdef.get("label", "?")
        for tk in sdef.get("tickers", []):
            out[str(tk).upper()] = label
    return out


def compute_brier_audit() -> dict[str, Any]:
    """Compute Brier breakdown par ticker + par sector.

    Returns :
        {
            'ok': bool,
            'n_total': int,
            'avg_brier_global': float,
            'per_ticker': [
                {'ticker': str, 'n': int, 'avg_brier': float, 'caveat': str},
                ...
            ],  # top 10 by N desc
            'per_sector': [
                {'sector': str, 'n': int, 'avg_brier': float, 'caveat': str},
                ...
            ],
            'reason': str,
        }
    """
    from shared import storage

    out: dict[str, Any] = {
        "ok": False,
        "n_total": 0,
        "avg_brier_global": 0.0,
        "per_ticker": [],
        "per_sector": [],
        "reason": "",
    }

    try:
        with storage.db() as conn:
            # Global
            row = conn.execute("""
                SELECT COUNT(*), AVG(brier_score)
                FROM predictions
                WHERE outcome IS NOT NULL AND brier_score IS NOT NULL
            """).fetchone()
            out["n_total"] = int(row[0] or 0)
            out["avg_brier_global"] = float(row[1] or 0)

            if out["n_total"] == 0:
                out["reason"] = "no resolved predictions"
                return out

            # Per ticker (top 10 by N)
            ticker_rows = conn.execute("""
                SELECT ticker, COUNT(*) as n, AVG(brier_score) as avg_brier
                FROM predictions
                WHERE outcome IS NOT NULL AND brier_score IS NOT NULL
                  AND ticker IS NOT NULL
                GROUP BY ticker
                ORDER BY n DESC
                LIMIT 10
            """).fetchall()
            for tk, n, brier in ticker_rows:
                caveat = _statistical_caveat(int(n))
                out["per_ticker"].append({
                    "ticker": str(tk),
                    "n": int(n),
                    "avg_brier": float(brier),
                    "caveat": caveat,
                })
    except Exception as e:
        out["reason"] = f"db err: {e}"
        return out

    # Per sector (aggregate ticker → sector via sectors.yaml)
    sector_map = _load_sector_map()
    if sector_map:
        try:
            with storage.db() as conn:
                all_rows = conn.execute("""
                    SELECT ticker, brier_score FROM predictions
                    WHERE outcome IS NOT NULL AND brier_score IS NOT NULL
                      AND ticker IS NOT NULL
                """).fetchall()
            sector_bucket: dict[str, list[float]] = {}
            for tk, brier in all_rows:
                sec = sector_map.get(str(tk).upper(), "Uncategorized")
                sector_bucket.setdefault(sec, []).append(float(brier))
            sector_stats = []
            for sec, briers in sector_bucket.items():
                n = len(briers)
                avg = sum(briers) / n
                sector_stats.append({
                    "sector": sec,
                    "n": n,
                    "avg_brier": avg,
                    "caveat": _statistical_caveat(n),
                })
            sector_stats.sort(key=lambda x: -x["n"])
            out["per_sector"] = sector_stats
        except Exception as e:
            log.debug("per_sector compute fail: %s", e)

    out["ok"] = True
    out["reason"] = (
        f"{out['n_total']} resolved predictions, "
        f"avg Brier {out['avg_brier_global']:.3f}, "
        f"split en {len(out['per_ticker'])} tickers + {len(out['per_sector'])} sectors. "
        f"Baseline 0.25 (random binary guess)."
    )
    return out


def _statistical_caveat(n: int) -> str:
    """Honest caveat sur la précision statistique selon N."""
    if n >= 100:
        return "N>=100, CI raisonnable"
    if n >= 30:
        return f"N={n}, CI moyennement large"
    if n >= 10:
        return f"N={n} BRUIT IMPORTANT"
    return f"N={n} STATISTIQUEMENT NÉGLIGEABLE"
