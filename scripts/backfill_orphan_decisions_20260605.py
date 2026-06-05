"""Backfill 05/06/2026 : reconstruit decision_counterfactual manquants + close
SNOW these orpheline.

Contexte : 5 decisions du 03/06 (ids 74-78, GOOGL/SNOW/AMZN/GOOGL/6857.T) etaient
orphelines parce que positions.py log_decision sans call record_anchor (regression
source-direct fixee dans le meme commit). De plus, full_exit SNOW 75 n'avait pas
ferme la these (autre regression source-direct fixee).

Approche : reconstitution honnete des ancres depuis les donnees disponibles
(price_at_decision dans la decision row, qty before via position_events anterieurs,
currency via shared.edgar). Tagged bias_hypothesis_json=["backfill_05_06_orphan"]
pour qu un audit futur sache que c est reconstruction ex-post, pas ancre live.

Forward : positions.py call record_anchor sur chaque log_decision + close these
sur full_exit. Plus de futur orphan.

Doctrine : utiliser ce script UNIQUEMENT pour les 5 ids 74-78. Idempotent : un
2e run ne refait rien (ON CONFLICT IGNORE simule via check SELECT prealable).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("backfill_orphan_05_06")

ORPHAN_DECISION_IDS = [74, 75, 76, 77, 78]
SNOW_THESIS_ID = 53  # full_exit 03/06 mais these restee 'active'


def _qty_before(conn: sqlite3.Connection, ticker: str, decision_at: str, dtype: str) -> float:
    """Reconstitue qty AVANT la decision via somme position_events anterieurs.

    Pour scale_in/full_exit/partial_exit : qty_before = somme buys - somme sells
    strictement AVANT decision_at.

    Fallback (data hole) : si somme <= 0 sur un sell (= position_events manque le
    buy initial, antérieur au logging position_events), on récupère la qty du
    matching sell event au moment exact de la decision. C'est la qty consommée
    par le sell, donc = qty existante avant.
    """
    row = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN event_type='buy' THEN qty ELSE 0 END), 0) - "
        "       COALESCE(SUM(CASE WHEN event_type='sell' THEN qty ELSE 0 END), 0) "
        "AS qty_before "
        "FROM position_events WHERE ticker=? AND timestamp < ?",
        (ticker, decision_at),
    ).fetchone()
    qty = float(row[0] or 0)
    if qty <= 0 and dtype in ("partial_exit", "full_exit"):
        sell_row = conn.execute(
            "SELECT qty FROM position_events "
            "WHERE ticker=? AND event_type='sell' "
            "  AND ABS(strftime('%s', timestamp) - strftime('%s', ?)) < 60 "
            "ORDER BY timestamp DESC LIMIT 1",
            (ticker, decision_at),
        ).fetchone()
        if sell_row and sell_row[0] > 0:
            qty = float(sell_row[0])
    return qty


def _get_currency(ticker: str) -> str | None:
    try:
        from shared import edgar
        if hasattr(edgar, "get_currency_for_ticker"):
            return edgar.get_currency_for_ticker(ticker)
    except Exception:
        pass
    return None


def backfill_one(conn: sqlite3.Connection, decision_id: int) -> bool:
    """Reconstitue 1 counterfactual. Returns True si insere, False si deja existant."""
    existing = conn.execute(
        "SELECT id FROM decision_counterfactual WHERE decision_id=?", (decision_id,)
    ).fetchone()
    if existing:
        log.info(f"decision {decision_id} : counterfactual deja existe (id={existing[0]}), skip")
        return False

    dec = conn.execute(
        "SELECT id, ticker, decision_type, created_at, thesis_id, price_at_decision, reasoning "
        "FROM decisions WHERE id=?",
        (decision_id,),
    ).fetchone()
    if not dec:
        log.warning(f"decision {decision_id} introuvable, skip")
        return False

    _id, ticker, dtype, created_at, thesis_id, price, reasoning = dec
    qty_before = _qty_before(conn, ticker, created_at, dtype)
    currency = _get_currency(ticker)

    branch = "would_have_sold" if dtype == "scale_in" else "hold"
    bias_hyp = ["backfill_05_06_orphan"]
    bf_reasoning = (
        f"[BACKFILL 05/06] Ancre reconstituee ex-post -- positions.py manquait "
        f"record_anchor au moment du trade 03/06. Source fix appliquee meme jour. "
        f"Original reasoning : {(reasoning or '')[:500]}"
    )

    conn.execute(
        "INSERT INTO decision_counterfactual ("
        "  decision_id, ticker, decision_type, decided_at, counterfactual_branch, "
        "  anchor_price_native, anchor_price_eur, anchor_qty_before, "
        "  anchor_currency, anchor_thesis_id, anchor_conviction, "
        "  bias_hypothesis_json, reasoning_at_decision"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            decision_id, ticker, dtype, created_at, branch,
            price, price, qty_before,
            currency, thesis_id, None,
            json.dumps(bias_hyp), bf_reasoning[:1000],
        ),
    )
    log.info(
        f"decision {decision_id} ({ticker} {dtype}) : counterfactual backfille "
        f"(qty_before={qty_before:.3f} price={price} branch={branch})"
    )
    return True


def close_snow_thesis(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT status FROM theses WHERE id=?", (SNOW_THESIS_ID,)
    ).fetchone()
    if not row:
        log.warning(f"these {SNOW_THESIS_ID} introuvable")
        return False
    if row[0] == "concluded":
        log.info(f"these {SNOW_THESIS_ID} SNOW deja concluded, skip")
        return False
    conn.execute(
        "UPDATE theses SET status='concluded', "
        "notes=COALESCE(notes, '') || ' [BACKFILL 05/06] closed retroactivement apres full_exit 03/06' "
        "WHERE id=?",
        (SNOW_THESIS_ID,),
    )
    log.info(f"these {SNOW_THESIS_ID} SNOW : status active -> concluded")
    return True


def main() -> None:
    conn = sqlite3.connect(storage.DB_PATH)
    try:
        log.info(f"DB : {storage.DB_PATH}")
        n_backfilled = 0
        for did in ORPHAN_DECISION_IDS:
            if backfill_one(conn, did):
                n_backfilled += 1
        snow_closed = close_snow_thesis(conn)
        conn.commit()
        log.info(
            f"DONE. Counterfactuals backfilles : {n_backfilled}/{len(ORPHAN_DECISION_IDS)}. "
            f"SNOW these closed : {snow_closed}."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
