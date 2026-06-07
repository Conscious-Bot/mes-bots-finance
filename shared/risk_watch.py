"""Loader config/risk_watch.yaml + merge avec DB live state.

Phase 1.5 stage 2 absorption_roadmap. Doctrine L17 LESSONS :
- DECLARATIF : config/risk_watch.yaml (user-edited, Pydantic-validated)
- LIVE STATE : table risk_signal_evaluations (cron-written via shared/storage)

Le loader ici :
1. Lit le YAML
2. Valide via Pydantic RiskWatchConfig (extra=forbid catche drift)
3. Optionnellement merge avec latest evaluations DB pour render

API publique :
- `load_risk_watch()` -> dict valide (declaratif uniquement)
- `load_risk_watch_with_live_state()` -> dict hydrate avec current_status
  par signal (pour render.py)
- `clear_cache()` -> reset cache (tests)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_YAML_PATH = _REPO_ROOT / "config" / "risk_watch.yaml"
_JSON_FALLBACK_PATH = _REPO_ROOT / "scripts" / "risk_watch.json"
_CACHE: dict | None = None


def load_risk_watch() -> dict | None:
    """Charge le YAML declaratif + valide via Pydantic.

    Returns:
        Dict en forme JSON legacy (keys: _meta, risks), avec by_alias=True
        pour preserver `_meta`. None si fichier absent ET fallback JSON absent.

    Fallback : si le YAML est invalide ou absent, retombe sur l'ancien
    scripts/risk_watch.json (period transitoire). Log warning explicite."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    if _YAML_PATH.exists():
        try:
            import yaml

            from intelligence.risk_watch_schema import RiskWatchConfig
            raw = yaml.safe_load(_YAML_PATH.read_text())
            cfg = RiskWatchConfig.model_validate(raw)
            _CACHE = cfg.model_dump(by_alias=True, mode="json")
            return _CACHE
        except Exception as e:
            log.warning(
                f"risk_watch.yaml invalide ({type(e).__name__}: {e}). "
                "Fallback JSON legacy. cf L17 LESSONS."
            )

    # Fallback JSON (transitoire post-migration)
    if _JSON_FALLBACK_PATH.exists():
        try:
            _CACHE = json.loads(_JSON_FALLBACK_PATH.read_text())
            log.info(
                "risk_watch loaded from legacy JSON fallback "
                "(scripts/risk_watch.json). Migrate to config/risk_watch.yaml."
            )
            return _CACHE
        except Exception as e:
            log.error(f"risk_watch.json parse failed: {e}")
            return None

    return None


def load_risk_watch_with_live_state() -> dict | None:
    """Charge le declaratif + hydrate chaque signal avec current_status DB.

    Pour chaque surveillance_signal dans chaque risk, ajoute les cles :
    - current_status (str, default 'monitoring' si jamais evalue)
    - last_evaluated_at (ISO timestamp ou None)
    - last_eval_reason (str ou None)
    - last_eval_confidence (int 0-100 ou None)
    - last_eval_evidence_ids (list[int] ou [])

    Compat retro avec ancien format JSON melange. Render.py consomme ce
    dict comme avant Phase 1.5 stage 2 : pas de change downstream.

    Returns:
        Dict hydrate ou None si declaratif absent.
    """
    cfg = load_risk_watch()
    if cfg is None:
        return None

    # Charge tout latest en un query
    try:
        from shared.storage import get_all_latest_risk_signal_evaluations
        live_state = get_all_latest_risk_signal_evaluations()
    except Exception as e:
        log.warning(f"get_all_latest_risk_signal_evaluations failed: {e}")
        live_state = {}

    # Merge en place dans une copie pour eviter de muter le cache
    import copy
    hydrated = copy.deepcopy(cfg)
    for risk in hydrated.get("risks") or []:
        risk_id = risk.get("id")
        for sig in risk.get("surveillance_signals") or []:
            sig_id = sig.get("id")
            key = (risk_id, sig_id)
            eval_row = live_state.get(key)
            if eval_row:
                sig["current_status"] = eval_row["status"]
                sig["last_evaluated_at"] = eval_row["evaluated_at"]
                sig["last_eval_reason"] = eval_row.get("reason") or ""
                sig["last_eval_confidence"] = eval_row.get("confidence")
                try:
                    ids_str = eval_row.get("evidence_ids_json") or "[]"
                    sig["last_eval_evidence_ids"] = json.loads(ids_str)
                except Exception:
                    sig["last_eval_evidence_ids"] = []
            else:
                # Jamais evalue : defaults safe
                sig["current_status"] = "monitoring"
                sig["last_evaluated_at"] = None
                sig["last_eval_reason"] = ""
                sig["last_eval_confidence"] = None
                sig["last_eval_evidence_ids"] = []
    return hydrated


def clear_cache() -> None:
    """Force reload au prochain acces. Utile en tests + apres edit YAML."""
    global _CACHE
    _CACHE = None


def get_declarative_signal(
    risk_id: str, signal_id: str
) -> dict[str, Any] | None:
    """Helper : retourne les champs DECLARATIFS d'un signal donne (id, label,
    weight, trigger, tickers_to_watch, threshold, data_source).

    Returns None si risk_id ou signal_id inconnus."""
    cfg = load_risk_watch()
    if cfg is None:
        return None
    for risk in cfg.get("risks") or []:
        if risk.get("id") != risk_id:
            continue
        for sig in risk.get("surveillance_signals") or []:
            if sig.get("id") == signal_id:
                return dict(sig)
    return None
