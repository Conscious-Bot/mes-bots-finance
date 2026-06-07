"""Surface 2 lock_in -- detection winner sold, version spec 02/06/2026.

Biais #1 de PRESAGE (vendre les gagnants trop tot), raison d'etre de
l'instrument. ADR-010 §2 ; spec finale user 02/06/2026.

Invariants (style Fincept BacktestEngine.h, doctrine Phase 0 07/06)
------------------------------------------------------------------
- Bias model : pas de look-ahead. classify_lock_in() ne consulte JAMAIS
  les prix futurs (px_90j). Le futur n'est lu qu'a la resolution +90j
  par la machinerie bias_events, jamais a la classification T0.
- Currency invariant : delta_signed est calcule en EUR (avg_cost EUR
  canonical per ADR 005). px_90j fetched via _cached_price_eur, jamais
  native, pour eviter pollution FX (cf [[currency-native-invariant]]).
- Threat model : protege contre la sur-vente prematuree de winners
  conviction haute. NE protege PAS contre : (a) achats fomo (canal
  separe), (b) holds-too-long de losers (kill_criteria_monitor), (c)
  liquidite forcee (separate concern).
- Failure mode : si LLM down ou prices stale, classify_lock_in() reste
  fonctionnel (calcul deterministe pur). Resolution +90j seule peut
  echouer silencieusement si prices unavailable -> retry via cron.
- N requis = 20 candidats resolus pour ajustement data-driven des seuils.
  En dessous : priors figes ci-dessous, revision manuelle uniquement.

Architecture
------------
- Hook dans shared.positions.add_sell apres cx.commit() (cf LESSONS L7).
- Pure fonction `classify_lock_in(sale)` -> candidat ou None (sans DB,
  testable property-based).
- `detect_winner_sell()` collecte le sale dict (lit theses + overcap
  state) puis appelle classify_lock_in, puis wire bias_event si candidat.
- Resolution canonique +90j via machinerie bias_events existante.
- delta_signed = (px_90j - px_vente) * parts_vendues, en EUR.
  Negatif = le prix a monte apres la vente = cout lock_in.
  Positif = le prix a baisse apres la vente = exit sage.

Gates (4 + 1 garde) -- ALL must pass for candidate
--------------------------------------------------
1. Status these == 'active' (invalidee/stale -> out)
2. Gain realise > 0 (c'est un gagnant)
3. Gain realise < 50% de la cible_conviction (axe timing prematuration) :
     c5 cible +70%  -> flag si pnl < 35%
     c4 cible +60%  -> flag si pnl < 30%
     c3 cible +50%  -> flag si pnl < 25%
     c2 cible +40%  -> flag si pnl < 20%
     c1 cible +30%  -> flag si pnl < 15% (mais ignored via gate 4)
4. Magnitude vendue >= seuil degressif (axe exit-vs-trim) :
     c5 >= 25% de la position
     c4 >= 35%
     c3 >= 50%
     c2 >= 75%
     c1 -> IGNORED (trim sur c1 = pas un lock_in significatif)
5. Garde over-cap : exclu si la coupe ramene une ligne over-cap vers cap
   (rightsize != lock_in, ADR 009). Par defaut conservateur : si la ligne
   etait over-cap avant la vente, on EXCLUE (priorite faux-negatif <
   faux-positif).

Auto-calibration des seuils
---------------------------
N >= 20 candidats resolus requis pour considerer un ajustement
data-driven des seuils. Jusque-la : priors ci-dessus, revision manuelle.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

# Cibles pnl% par conviction (la these "vise" cette progression vs entry).
# Gate timing flag si pnl_realise < 50% de la cible (premature halfway).
TARGET_PNL_BY_CONV: dict[int, float] = {
    5: 0.70,
    4: 0.60,
    3: 0.50,
    2: 0.40,
    1: 0.30,
}

# Magnitude vendue minimum pour declarer un "exit" vs "trim" (dgressive).
# c1 = None : tout trim sur c1 est ignore (pas un signal significatif).
MAGNITUDE_THRESHOLD_BY_CONV: dict[int, float | None] = {
    5: 0.25,
    4: 0.35,
    3: 0.50,
    2: 0.75,
    1: None,
}

_HORIZON_DAYS = 90  # spec : resolution canonique +90j
_BIAS = "lock_in"
_REF = "rule:winner_sell"

# Knob pour auto-calibration future : pas d'auto avant N candidats resolus.
_AUTO_CALIB_MIN_N = 20


def _read_thesis(ticker: str) -> dict[str, Any] | None:
    """Lit la these (active OU autre status). Retourne dict ou None si pas
    de these. La spec exige these active pour candidat ; ce helper expose
    le status pour que classify_lock_in() puisse filtrer."""
    from shared.storage import DB_PATH

    cx = sqlite3.connect(DB_PATH)
    cx.row_factory = sqlite3.Row
    try:
        row = cx.execute(
            "SELECT conviction, status, target_partial, target_full, "
            "       opened_at, entry_price "
            "FROM theses WHERE ticker=? "
            "ORDER BY id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
    finally:
        cx.close()
    if not row:
        return None
    return {
        "conviction": row["conviction"],
        "status": row["status"],
        "target_partial": row["target_partial"],
        "target_full": row["target_full"],
        "opened_at": row["opened_at"],
        "entry_price": row["entry_price"],
    }


def _read_overcap_state(ticker: str) -> str:
    """Wrap defensif autour de over_cap_monitor._prev_status_for_overcap.
    Retourne 'over' / 'dormant' / 'unknown' si erreur. La garde a moins
    qu'over est conservatrice : on suppose dormant par defaut (sinon
    'unknown' -> classify decide selon politique)."""
    try:
        from intelligence.over_cap_monitor import _prev_status_for_overcap
        return _prev_status_for_overcap(ticker)
    except Exception as e:
        log.info(f"lock_in_detector overcap_state ticker={ticker} error={e}")
        return "unknown"


def _compute_time_progress(opened_at: str | None) -> float | None:
    """days_held / HORIZON_DAYS. None si opened_at non-parsable."""
    if not opened_at:
        return None
    try:
        opened = datetime.fromisoformat(str(opened_at).replace("Z", "+00:00"))
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=UTC)
        days_held = (datetime.now(UTC) - opened).days
        return round(days_held / _HORIZON_DAYS, 4)
    except (ValueError, TypeError):
        return None


def classify_lock_in(sale: dict[str, Any]) -> dict[str, Any] | None:
    """Pure fonction (sans DB) qui applique les 4 gates + garde over-cap.

    Args:
        sale: dict avec cles requises :
            - ticker (str)
            - qty_sold (float > 0)
            - sold_price_native (float > 0)
            - qty_before (float > 0)
            - avg_cost (float > 0)
            - thesis: dict ou None
                {conviction, status, target_partial, target_full,
                 opened_at, entry_price}
            - overcap_state: 'over' | 'dormant' | 'unknown'

    Returns:
        Dict candidate (avec reason='candidate', dimensions, gates_passed)
        SI tous les gates passent. None sinon (avec reason loggee).

    Logique exposee pour property-based testing -- ne touche pas la DB.
    """
    ticker = str(sale.get("ticker") or "").upper()
    qty_sold = float(sale.get("qty_sold") or 0)
    sold_price = float(sale.get("sold_price_native") or 0)
    qty_before = float(sale.get("qty_before") or 0)
    avg_cost = float(sale.get("avg_cost") or 0)
    thesis = sale.get("thesis") or None
    overcap = sale.get("overcap_state") or "unknown"

    # Pre-conditions arithmetiques
    if not ticker or qty_sold <= 0 or sold_price <= 0 or qty_before <= 0 or avg_cost <= 0:
        return None  # invalid_args
    if qty_sold > qty_before:
        return None  # bug caller : tu peux pas vendre plus que tu n'as

    # Gate 1 : these active
    if not thesis:
        return None  # no_thesis -- IGNORED (pas la peine de creer un bias_event)
    if thesis.get("status") != "active":
        return None  # thesis_inactive

    conv = thesis.get("conviction")
    if conv is None or not isinstance(conv, int) or conv not in TARGET_PNL_BY_CONV:
        return None  # conviction_invalid

    # Gate 2 : gain > 0 (winner)
    pnl_pct = (sold_price / avg_cost) - 1
    if pnl_pct <= 0:
        return None  # not_winner

    # Gate 2b : floor canonique pnl >= 15% (CLAUDE.md spec lock_in v2.c.6).
    # Sans ce floor, toute vente prematuree micro-gain (ex 2%) est flag,
    # bruit demesure. 15% = "vraiment un winner sold pre-target".
    # Epsilon 1e-6 pour gerer precision IEEE 754 (ex 115/100-1 = 0.14999...).
    if pnl_pct < 0.15 - 1e-6:
        return None  # below_pnl_floor (gain trop faible pour qualifier de lock_in)

    # Gate 3 : gain < 50% de la cible_conviction (axe timing)
    target_pnl = TARGET_PNL_BY_CONV[conv]
    target_halfway = 0.5 * target_pnl
    if pnl_pct >= target_halfway:
        return None  # pnl_above_halfway (la these a deja bien progresse)

    # Gate 4 : magnitude vendue >= seuil degressif (axe exit-vs-trim)
    mag_threshold = MAGNITUDE_THRESHOLD_BY_CONV.get(conv)
    if mag_threshold is None:
        return None  # ignored_conviction (c1 ignored)
    magnitude = qty_sold / qty_before
    if magnitude < mag_threshold:
        return None  # magnitude_below_threshold (c'est juste un trim)

    # Garde 5 : over-cap rightsize (ADR 009)
    if overcap == "over":
        return None  # overcap_rightsize (exclu, c'est de la discipline)

    # Candidat ! Compute dimensions enrichies
    pnl_progress = round(pnl_pct / target_pnl, 4) if target_pnl > 0 else None
    time_progress = _compute_time_progress(thesis.get("opened_at"))

    return {
        "reason": "candidate",
        "ticker": ticker,
        "pnl_pct": round(pnl_pct, 4),
        "target_pnl_pct": target_pnl,
        "target_halfway": round(target_halfway, 4),
        "magnitude_pct": round(magnitude, 4),
        "magnitude_threshold": mag_threshold,
        "conviction": conv,
        "overcap_state": overcap,
        "dimensions": {
            # 4 dimensions canonical pour analyse data-driven post-N=20
            "pnl_pct_at_sell": round(pnl_pct, 4),
            "conviction_at_sell": conv,
            "pnl_pct_progress": pnl_progress,
            "time_progress": time_progress,
        },
    }


def _link_position_event(bias_event_id: int, position_event_id: int) -> None:
    """Update bias_events.position_event_id post-INSERT pour audit FK."""
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
    position_id: int,  # noqa: ARG001  reserve pour futur audit
    ticker: str,
    qty_sold: float,
    sold_price_native: float,
    qty_before: float,
    avg_cost: float,
) -> dict[str, Any] | None:
    """Hook appele depuis shared.positions.add_sell APRES cx.commit().

    Toute exception capturee en interne -- ne casse jamais l'enregistrement
    de la vente (L7).
    """
    ticker = ticker.upper()
    log.info(
        f"lock_in_detector ENTERED ticker={ticker} qty_sold={qty_sold} "
        f"sold_price={sold_price_native} avg_cost={avg_cost}"
    )

    # Read thesis + overcap state (DB)
    thesis = _read_thesis(ticker)
    overcap = _read_overcap_state(ticker)

    # Build sale dict puis classify
    sale = {
        "ticker": ticker,
        "qty_sold": qty_sold,
        "sold_price_native": sold_price_native,
        "qty_before": qty_before,
        "avg_cost": avg_cost,
        "thesis": thesis,
        "overcap_state": overcap,
    }
    candidate = classify_lock_in(sale)
    if not candidate:
        log.info(
            f"lock_in_detector SKIP ticker={ticker} no_candidate "
            f"thesis_status={thesis.get('status') if thesis else 'no_thesis'} "
            f"conv={thesis.get('conviction') if thesis else None} "
            f"overcap={overcap}"
        )
        return None

    # Anchor price EUR au moment de la vente
    from shared.prices import get_current_price_in_eur

    anchor_eur = get_current_price_in_eur(ticker)
    if not anchor_eur or anchor_eur <= 0:
        log.warning(f"lock_in_detector {ticker}: anchor_eur unavailable, skip")
        return None

    # Trouve le dernier position_event sell pour FK
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

    # wire_bias_trigger ouvre le candidat. initial_qty = qty_sold (spec :
    # delta_signed est calcule sur les parts vendues, pas sur la position
    # entiere). discipline_said.action='hold' (la discipline aurait tenu
    # les parts vendues a horizon +90j).
    from intelligence.bias_events import wire_bias_trigger

    ref = f"{_REF}:pe{position_event_id}" if position_event_id else _REF
    extra_cf = {
        **candidate["dimensions"],
        "surface": "surface_2_winner_sell",
        "sold_price_native": sold_price_native,
        "avg_cost_native": avg_cost,
        "qty_sold": qty_sold,
        "qty_before": qty_before,
        "target_pnl_pct": candidate["target_pnl_pct"],
        "magnitude_pct": candidate["magnitude_pct"],
        "overcap_state": candidate["overcap_state"],
    }
    stats = wire_bias_trigger([{
        "ticker": ticker, "bias": _BIAS,
        "discipline_said": {"action": "hold", "ref": ref},
        "horizon_days": _HORIZON_DAYS,
        "anchor_price_eur": float(anchor_eur),
        "initial_qty": qty_sold,  # spec : sur les parts vendues
        "discipline_expected_delta": 0.0,
        "source": "auto_detected",
        "note": json.dumps(extra_cf, sort_keys=True),
    }])

    if stats.get("opened") != 1:
        log.info(
            f"lock_in_detector SKIP wire_stats ticker={ticker} stats={stats}"
        )
        return None

    # Recupere bias_event_id pour FK
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

    log.info(
        f"lock_in_detector OPENED ticker={ticker} bias_event_id={bias_event_id} "
        f"pnl_pct={candidate['pnl_pct']:.4f} conv={candidate['conviction']} "
        f"magnitude={candidate['magnitude_pct']:.4f} horizon={_HORIZON_DAYS}j"
    )
    return {"bias_event_id": bias_event_id, "candidate": candidate}
