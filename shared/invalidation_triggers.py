"""Mécanisme cross-référencement invalidation_triggers ↔ sentinelles résolues.

Doctrine #150 Couche 2 partielle (mécanisme léger 16/06/2026) : les
`theses.invalidation_triggers` (JSON array of strings) référencent souvent des
codes sentinelles ("S6", "S10", etc.). Quand une sentinelle résout dans
`predictions` (origin='manual', resolved_at IS NOT NULL), les triggers
correspondants sont mécaniquement déclenchés.

**Approche read-only computed** : pas de nouvelle table, pas de mutation
JSON. La source de vérité = predictions table. Cette fonction joine on-the-fly.

**Cas d'usage** :
- Dashboard card rendering : afficher 🔴 (fired) vs ○ (pending) par trigger
- Audit-trace : "quels triggers ont fired et quand"
- Décision support : "le trigger structurel de telle thèse est-il déclenché ?"

Cf [[chantier-150]] full register Couche 2/3 gated, ce helper est le minimum
viable pour exploiter la cohérence sentinelle↔trigger sans architectural debt.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from shared import storage

# Regex : codes sentinelle de la forme "S{N}" où N = 1-99
# Évite faux positifs sur "S&P", "STM", etc. via word boundary + digit follow.
_SENTINEL_CODE_RE = re.compile(r"\b(S\d{1,2})\b")


def parse_sentinel_codes(text: str) -> list[str]:
    """Extrait tous les codes sentinelle ("S6", "S10", ...) d'un texte trigger.

    Exemples :
    - "S10 dual-sourcing TPU..." → ["S10"]
    - "Wafer ASP down >10%." → [] (pas de code)
    - "S2 (sentinelle) — Hyperscaler" → ["S2"]
    """
    if not text:
        return []
    return _SENTINEL_CODE_RE.findall(text)


def get_resolved_sentinels_by_code() -> dict[str, dict[str, Any]]:
    """Retourne mapping code → résolution depuis predictions table.

    Filtre : origin='manual' AND resolved_at IS NOT NULL.
    Le code est extrait de `source_metadata_json.code` (posé par
    `scripts/seed_sentinels_*.py`).

    Returns dict[code → {prediction_id, outcome, resolved_at, brier_score,
    probability_at_creation, claim_text}].
    """
    out: dict[str, dict[str, Any]] = {}
    try:
        with storage.db() as cx:
            # storage.db() already sets row_factory = sqlite3.Row
            rows = cx.execute(
                f"""
                SELECT id, outcome, resolved_at, brier_score, probability_at_creation,
                       source_metadata_json
                FROM predictions
                WHERE origin = 'manual' AND resolved_at IS NOT NULL
                  AND {storage.canonical_predictions_filter()}
                """
            ).fetchall()
    except Exception:
        return {}

    for r in rows:
        meta_raw = r["source_metadata_json"]
        if not meta_raw:
            continue
        try:
            meta = json.loads(meta_raw)
        except (ValueError, TypeError):
            continue
        code = meta.get("code")
        if not code:
            continue
        out[code] = {
            "prediction_id": r["id"],
            "outcome": r["outcome"],
            "resolved_at": r["resolved_at"],
            "brier_score": r["brier_score"],
            "probability_at_creation": r["probability_at_creation"],
            "claim_text": meta.get("claim_text", ""),
        }
    return out


@lru_cache(maxsize=1)
def get_trigger_status_per_thesis() -> dict[str, list[dict[str, Any]]]:
    """Pour chaque thèse active, retourne le statut de chaque trigger.

    Returns dict[ticker → list[{text, codes, fired, fired_at, outcome, evidence}]]

    `fired` = True si AU MOINS UN code dans le trigger texte matche une sentinelle
    résolue (peu importe outcome). `outcome` = celui de la sentinelle matchante
    (si plusieurs codes matchent, on prend la PREMIÈRE résolue).
    """
    resolved_by_code = get_resolved_sentinels_by_code()
    out: dict[str, list[dict[str, Any]]] = {}

    try:
        with storage.db() as cx:
            # storage.db() already sets row_factory = sqlite3.Row
            rows = cx.execute(
                "SELECT ticker, invalidation_triggers FROM theses WHERE status='active'"
            ).fetchall()
    except Exception:
        return {}

    for r in rows:
        ticker = r["ticker"]
        raw = r["invalidation_triggers"]
        if not raw:
            out[ticker] = []
            continue
        try:
            triggers_list = json.loads(raw)
        except (ValueError, TypeError):
            out[ticker] = []
            continue
        if not isinstance(triggers_list, list):
            out[ticker] = []
            continue

        statuses = []
        for trig in triggers_list:
            text = trig if isinstance(trig, str) else str(trig)
            codes = parse_sentinel_codes(text)
            fired_match: dict[str, Any] | None = None
            for code in codes:
                if code in resolved_by_code:
                    fired_match = {"code": code, **resolved_by_code[code]}
                    break  # première résolue prend la priorité
            statuses.append({
                "text": text,
                "codes": codes,
                "fired": fired_match is not None,
                "fired_at": fired_match["resolved_at"] if fired_match else None,
                "outcome": fired_match["outcome"] if fired_match else None,
                "matched_code": fired_match["code"] if fired_match else None,
                "prediction_id": fired_match["prediction_id"] if fired_match else None,
            })
        out[ticker] = statuses

    return out


def count_fired_triggers() -> dict[str, int]:
    """Pour chaque ticker, retourne le nb de triggers fired.

    Use case : dashboard summary "X tickers ont au moins 1 trigger fired".
    """
    statuses = get_trigger_status_per_thesis()
    return {tk: sum(1 for s in lst if s["fired"]) for tk, lst in statuses.items()}
