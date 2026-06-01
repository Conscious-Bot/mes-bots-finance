"""Pile 2.1 v2.c.6 -- Surface 2 lock_in : detection winner sold.

Biais #1 de PRESAGE (vendre les gagnants trop tot), raison d'etre de
l'instrument. ADR-010 §2 prevoyait Surface 2 ; livre 01/06/2026.

Architecture :
- Hook dans shared.positions.add_sell apres cx.commit() (cf LESSONS L7).
- Si gate v1 satisfait (pnl_pct >= 0.15 AND conviction_at_sell >= 3),
  ouvre un candidat bias_event via wire_bias_trigger.
- Resolution canonique a +30j (delta_signed_eur immutable, scoring).
- Backfill cron weekly enrichit observations[] avec +60j, +90j
  (cf bias_events.backfill_resolved_observations -- architecture B3
  user 01/06 Q3).

Gate v1 (user Q2 : ship simple + log dimensions pour v2 data-driven) :
  pnl_pct >= 0.15  AND  conviction_at_sell >= 3
  AND ticker UPPERCASE et qty/price > 0

4 dimensions logguees dans counterfactual_json pour analyse v2 post-90j :
  pnl_pct_at_sell, conviction_at_sell (CONTEMPORAINE, pas at-creation),
  pnl_pct_progress (= pnl_pct / thesis_target_pnl_pct si disponible),
  time_progress (= days_held / horizon_days si disponible).

V2 predicat data-driven (post 20-30 candidats resolus) :
  pnl_pct_progress < 0.6  AND  time_progress < 0.5  (relatif au target/horizon
  de la these, pas absolu sur pnl_pct).

Bypass paths hors-scope (documentes user 01/06 Q1) :
  - scripts/import_positions_legacy.py : backfill ponctuel, ignore
  - scripts/refresh_positions_2026_05_23.py : refresh account/status, ignore
  - shared/sql_observability.py : UPDATE qty audit, ignore
  Ces chemins ne passent PAS par positions.add_sell donc le hook ne fire pas.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

_GATE_PNL_PCT_MIN = 0.15
_GATE_CONVICTION_MIN = 3
_HORIZON_DAYS = 30
_BIAS = "lock_in"
_REF = "rule:winner_sell"


def _read_thesis_conviction_and_horizon(ticker: str) -> tuple[int | None, dict[str, Any]]:
    """Lit conviction CONTEMPORAINE (post-revisits) + targets/horizon de la these
    active. Retourne (conviction, extra) ou (None, {}) si pas de these."""
    from shared.storage import DB_PATH

    cx = sqlite3.connect(DB_PATH)
    cx.row_factory = sqlite3.Row
    try:
        row = cx.execute(
            "SELECT conviction, target_partial, target_full, opened_at, "
            "       entry_price "
            "FROM theses WHERE ticker=? AND status='active' "
            "ORDER BY id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
    finally:
        cx.close()
    if not row:
        return None, {}
    extra = {
        "target_partial": row["target_partial"],
        "target_full": row["target_full"],
        "opened_at": row["opened_at"],
        "entry_price": row["entry_price"],
    }
    return row["conviction"], extra


def _compute_dimensions(
    pnl_pct: float,
    conviction: int,
    thesis_extra: dict[str, Any],
    sold_price_native: float,
) -> dict[str, Any]:
    """Calcule les 4 dimensions logguees pour v2 data-driven.

    pnl_pct_progress et time_progress retournent None si donnee these
    manquante -- preserve l'information "non-calculable" sans faux 0.
    """
    dims: dict[str, Any] = {
        "pnl_pct_at_sell": round(pnl_pct, 4),
        "conviction_at_sell": conviction,
        "pnl_pct_progress": None,
        "time_progress": None,
    }
    entry = thesis_extra.get("entry_price")
    target_full = thesis_extra.get("target_full")
    if entry and target_full and entry > 0:
        target_pnl_pct = (target_full / entry) - 1
        if target_pnl_pct > 0:
            dims["pnl_pct_progress"] = round(pnl_pct / target_pnl_pct, 4)
    opened_at = thesis_extra.get("opened_at")
    if opened_at:
        try:
            opened = datetime.fromisoformat(str(opened_at).replace("Z", "+00:00"))
            if opened.tzinfo is None:
                opened = opened.replace(tzinfo=UTC)
            now = datetime.now(UTC)
            days_held = (now - opened).days
            if _HORIZON_DAYS > 0:
                dims["time_progress"] = round(days_held / _HORIZON_DAYS, 4)
        except (ValueError, TypeError):
            pass
    return dims


def _link_position_event(bias_event_id: int, position_event_id: int) -> None:
    """Update bias_events.position_event_id post-INSERT pour audit-trail FK
    (migration 0025). Wrap en try/except pour L7 : silent miss si echoue."""
    from shared.storage import DB_PATH

    cx = sqlite3.connect(DB_PATH)
    try:
        cx.execute(
            "UPDATE bias_events SET position_event_id=? WHERE id=?",
            (position_event_id, bias_event_id),
        )
        cx.commit()
    finally:
        cx.close()


def detect_winner_sell(
    *,
    position_id: int,
    ticker: str,
    qty_sold: float,
    sold_price_native: float,
    qty_before: float,
    avg_cost: float,
) -> dict[str, Any] | None:
    """Hook appele depuis shared.positions.add_sell APRES cx.commit() (L7).

    Si gate v1 satisfait, ouvre un candidat bias_event lock_in via
    wire_bias_trigger. Lie le bias_event au position_events row (le dernier
    insert event_type='sell' pour cette position).

    Returns:
        dict {bias_event_id, dimensions} si candidat ouvert, None sinon.
        Aucune exception ne traverse vers le caller (catch interne par hook).
    """
    ticker = ticker.upper()
    if avg_cost <= 0 or sold_price_native <= 0 or qty_sold <= 0 or qty_before <= 0:
        return None

    pnl_pct = (sold_price_native / avg_cost) - 1
    # Epsilon float : (115/100 - 1) donne 0.14999999999999991, rejette 15% exact
    if pnl_pct < _GATE_PNL_PCT_MIN - 1e-9:
        return None  # pas un winner (gate pnl)

    conviction, thesis_extra = _read_thesis_conviction_and_horizon(ticker)
    if conviction is None or conviction < _GATE_CONVICTION_MIN:
        return None  # these trash ou pas de these active (gate conviction)

    dims = _compute_dimensions(pnl_pct, conviction, thesis_extra, sold_price_native)

    # Anchor price EUR au moment de la vente
    from shared.prices import get_current_price_in_eur

    anchor_eur = get_current_price_in_eur(ticker)
    if not anchor_eur or anchor_eur <= 0:
        log.warning(f"lock_in_detector {ticker}: anchor_eur unavailable, skip")
        return None

    # Trouve le dernier position_event sell pour ce ticker (FK pour audit)
    from shared.storage import DB_PATH

    cx = sqlite3.connect(DB_PATH)
    try:
        row = cx.execute(
            "SELECT id FROM position_events WHERE ticker=? AND event_type='sell' "
            "ORDER BY id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        position_event_id = int(row[0]) if row else None
    finally:
        cx.close()

    # wire_bias_trigger ouvre le candidat (idempotence sur cle ticker+bias+
    # action+ref ; si meme vente loggee 2x, kept). Note pratique : sur lock_in,
    # le user peut faire plusieurs ventes successives sur le meme winner --
    # chacune doit ouvrir son candidat. Le ref includes position_event_id
    # pour distinguer.
    from intelligence.bias_events import wire_bias_trigger

    ref = f"{_REF}:pe{position_event_id}" if position_event_id else _REF
    extra_cf = {
        # 4 dimensions pour v2 data-driven (user Q2)
        **dims,
        # Surface origine
        "surface": "surface_2_winner_sell",
        "sold_price_native": sold_price_native,
        "avg_cost_native": avg_cost,
        "qty_sold": qty_sold,
    }
    stats = wire_bias_trigger([{
        "ticker": ticker, "bias": _BIAS,
        "discipline_said": {"action": "hold", "ref": ref},
        "horizon_days": _HORIZON_DAYS,
        "anchor_price_eur": float(anchor_eur),
        "initial_qty": qty_before,  # ce que la discipline aurait tenu
        "discipline_expected_delta": 0.0,  # discipline = hold winner
        "source": "auto_detected",
        "note": json.dumps(extra_cf, sort_keys=True),
    }])

    if stats.get("opened") != 1:
        # Idempotence kept ou error -- pas de nouveau lien FK a poser
        return None

    # Recupere bias_event_id pour lier FK
    cx2 = sqlite3.connect(DB_PATH)
    try:
        row2 = cx2.execute(
            "SELECT id FROM bias_events WHERE status='open' AND ticker=? "
            "AND bias=? ORDER BY id DESC LIMIT 1",
            (ticker, _BIAS),
        ).fetchone()
    finally:
        cx2.close()

    bias_event_id = int(row2[0]) if row2 else None
    if bias_event_id and position_event_id:
        _link_position_event(bias_event_id, position_event_id)

    return {"bias_event_id": bias_event_id, "dimensions": dims}
