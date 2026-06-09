"""LIVING GRAPH W0 — concept_index + fork detection minimal.

Cf SPEC_LIVING_GRAPH.md §2 architecture V0 + §3.3 auto-cohérence.

Le geste qui mécanise L29 (corriger calcul ≠ vérifier diffusion) :
plusieurs producteurs publient la même grandeur sémantique via
register_concept(concept_key, value, source, ticker). Au regen-end,
detect_forks() retourne tout tuple (concept, ticker, bucket) où ≥ 2
valeurs divergent au-delà de la tolérance ε du concept.

V0 = register_concept + detect_forks SEULS.
PAS datum_log/trace_parents (différé V1+, cf SPEC §3/§4).
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from shared import storage

log = logging.getLogger(__name__)

_CONCEPT_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "config" / "concept_keys.yaml"
_REGISTRY_CACHE: dict[str, dict[str, Any]] | None = None


def _load_registry() -> dict[str, dict[str, Any]]:
    """Charge config/concept_keys.yaml. Cache mémoire (1 read par process)."""
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None:
        return _REGISTRY_CACHE
    try:
        with open(_CONCEPT_REGISTRY_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _REGISTRY_CACHE = data.get("concepts", {}) or {}
    except Exception as e:
        log.warning("concept_keys.yaml read fail (%s) — empty registry, fork-detection no-op", e)
        _REGISTRY_CACHE = {}
    return _REGISTRY_CACHE


def _default_bucket(asof: str | None, granularity: str = "day") -> str:
    """Bucket temporel depuis asof (ISO) ou now() si None. Granularité 'day'|'hour'."""
    if asof:
        try:
            dt = datetime.fromisoformat(asof.replace("Z", "+00:00"))
        except Exception:
            dt = datetime.now(UTC)
    else:
        dt = datetime.now(UTC)
    if granularity == "hour":
        return dt.strftime("%Y-%m-%dT%H")
    return dt.strftime("%Y-%m-%d")


def register_concept(
    concept_key: str,
    value: float,
    source: str,
    ticker: str | None = None,
    asof: str | None = None,
    op: str | None = None,
    degraded: bool = False,
    confidence: float = 1.0,
) -> None:
    """Lie une valeur+source à un concept sémantique dans concept_index.

    UPSERT idempotent via PK (concept_key, ticker, asof_bucket, source) :
    re-publier la même valeur même source dans la même bucket = no-op gratuite.
    Deux sources distinctes même bucket = deux rows = candidat fork.

    Silent-miss L7 si DB down — ne casse pas le producteur appelant.
    """
    registry = _load_registry()
    cfg = registry.get(concept_key, {})
    granularity = cfg.get("asof_bucket", "day")
    bucket = _default_bucket(asof, granularity)
    tk = ticker or ""

    try:
        with storage.db() as cx:
            cx.execute("""
                INSERT INTO concept_index
                (concept_key, ticker, asof_bucket, source, value, op, degraded, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(concept_key, ticker, asof_bucket, source) DO UPDATE SET
                    value = excluded.value,
                    op = excluded.op,
                    degraded = excluded.degraded,
                    confidence = excluded.confidence,
                    logged_at = datetime('now')
            """, (concept_key, tk, bucket, source, float(value), op,
                  1 if degraded else 0, float(confidence)))
            cx.commit()
    except Exception as e:
        log.warning("register_concept(%s, %s, src=%s) DB fail (silent-miss L7) : %s",
                    concept_key, tk, source, e)


def detect_forks(asof_bucket: str | None = None) -> list[dict[str, Any]]:
    """Scan concept_index pour la bucket donnée. Retourne forks détectés.

    Fork = ≥ 2 valeurs distinctes pour un tuple (concept, ticker, bucket)
    qui divergent au-delà de la tolérance ε du concept (config/concept_keys.yaml).

    Sans bucket = aujourd'hui (jour ISO UTC).

    Return : [{concept_key, ticker, bucket, max_div, candidates: [{value, source, op}]}].
    """
    if asof_bucket is None:
        asof_bucket = date.today().isoformat()
    registry = _load_registry()
    forks: list[dict[str, Any]] = []

    try:
        with storage.db() as cx:
            # Récupère tuples (concept, ticker, bucket) qui ont ≥ 2 rows
            tuples_rows = cx.execute("""
                SELECT concept_key, ticker, asof_bucket, COUNT(*) AS n
                FROM concept_index
                WHERE asof_bucket = ?
                GROUP BY concept_key, ticker, asof_bucket
                HAVING COUNT(*) >= 2
            """, (asof_bucket,)).fetchall()

            for row in tuples_rows:
                concept_key = row["concept_key"]
                ticker = row["ticker"]
                bucket = row["asof_bucket"]
                candidates_rows = cx.execute("""
                    SELECT value, source, op
                    FROM concept_index
                    WHERE concept_key = ? AND ticker = ? AND asof_bucket = ?
                    ORDER BY source
                """, (concept_key, ticker, bucket)).fetchall()
                candidates = [
                    {"value": float(r["value"]), "source": r["source"], "op": r["op"]}
                    for r in candidates_rows
                ]
                # Compute max divergence relative
                values = [c["value"] for c in candidates]
                if not values:
                    continue
                v_ref = values[0]
                if v_ref == 0:
                    # Edge case : on compare |a-b| absolu si ref=0
                    max_div = max(abs(v - v_ref) for v in values)
                    max_div_rel = max_div  # absolute as rel proxy
                else:
                    max_div_rel = max(abs(v - v_ref) / abs(v_ref) for v in values)

                # Tolérance ε du concept (default 0.001 si concept inconnu — fail strict)
                cfg = registry.get(concept_key, {})
                eps = float(cfg.get("epsilon_rel", 0.001))
                if max_div_rel > eps:
                    forks.append({
                        "concept_key": concept_key,
                        "ticker": ticker if ticker else None,
                        "bucket": bucket,
                        "max_div_rel": max_div_rel,
                        "epsilon_rel": eps,
                        "candidates": candidates,
                    })
    except Exception as e:
        log.warning("detect_forks(%s) DB fail (silent-miss L7) : %s", asof_bucket, e)
        return []
    return forks
