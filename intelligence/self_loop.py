"""PRESAGE Boucle-de-soi V0.

Decision -> ancre contrefactuelle figee -> mesure J+30 -> biais quantifie
-> re-injecte dans le prochain prompt.

Distinction critique avec la boucle-marche (predictions/outcomes/Brier) :
- Boucle-marche : "ma these etait-elle juste ?" -> calibration -> commoditisable
- Boucle-de-soi : "ma discipline a-t-elle aide ou nui ?" -> correction biais
  -> UNIQUE a l'utilisateur, base de l'asset Path 6

V0 scope :
- horizon J+30 seulement (V1 ajoute 60/90/180)
- contrefactuel = "hold strict" (V1 ajoute rotate_to_X)
- CLI exposition (panneau dashboard V1+)
- Re-injection via prompt copilot quand sell-winner detecte

API publique :
- record_anchor(decision_id, ticker, decision_type, ...) : appele depuis
  chat_intent.py AVANT positions_mod.add_sell/add_buy
- resolve_due_anchors(horizon_days=30) : appele par cron daily
- measure_bias(bias_name, horizon_days) : exposition de la mesure
- bias_context_for_prompt(ticker, decision_type) : injecte dans le copilot prompt
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from shared import storage

log = logging.getLogger(__name__)


# ─────────────────────── RECORD : ancre figee ──────────────────────────────


def record_anchor(
    *,
    decision_id: int,
    ticker: str,
    decision_type: str,
    qty_before: float,
    price_at_decision: float | None = None,
    price_at_decision_eur: float | None = None,
    currency: str | None = None,
    thesis_id: int | None = None,
    conviction_at_t0: int | None = None,
    bias_hypothesis: list[str] | None = None,
    reasoning: str | None = None,
    counterfactual_branch: str = "hold",
) -> int | None:
    """Capture l'ancre contrefactuelle AVANT execution de la decision.

    Appele depuis chat_intent.py et bot/handlers/positions.py au moment du
    /sell, /scale_in, /buy. PAS apres -- sinon c'est de la rationalisation
    ex-post.

    Returns: decision_counterfactual.id si insert reussi, None si erreur.
    """
    try:
        with storage.db() as cx:
            cur = cx.execute(
                "INSERT INTO decision_counterfactual ("
                "  decision_id, ticker, decision_type, counterfactual_branch,"
                "  anchor_price_native, anchor_price_eur, anchor_qty_before,"
                "  anchor_currency, anchor_thesis_id, anchor_conviction,"
                "  bias_hypothesis_json, reasoning_at_decision"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    decision_id, ticker.upper(), decision_type, counterfactual_branch,
                    price_at_decision, price_at_decision_eur, qty_before,
                    currency, thesis_id, conviction_at_t0,
                    json.dumps(bias_hypothesis or [], ensure_ascii=False),
                    (reasoning or "")[:1000],
                ),
            )
            cx.commit()
            return cur.lastrowid
    except Exception as e:
        log.warning(f"record_anchor {ticker} decision {decision_id} failed: {e}")
        return None


# ─────────────────────── RESOLVE : J+N outcome ─────────────────────────────


def resolve_due_anchors(horizon_days: int = 30) -> dict:
    """Resout les ancres dont T+horizon est passe ET pas encore resolu.

    Pour chaque ancre :
      - fetch prix actuel via shared.prices.get_current_price
      - actual_value_eur = qty actuelle (post-decision) * prix_T+N
      - counterfactual_value_eur = anchor_qty_before * prix_T+N
      - delta_eur = actual - counterfactual
      - verdict : beneficial / neutral / harmful

    Append-only : 1 ligne par (decision_counterfactual_id, horizon_days).
    Re-runs idempotent (UNIQUE index empeche les doublons).

    Returns: {resolved: int, skipped: int, errors: int, details: [...]}.
    """
    from shared import positions as positions_mod, prices

    cutoff_iso = (datetime.now(UTC) - timedelta(days=horizon_days)).isoformat()
    out: dict[str, Any] = {"resolved": 0, "skipped": 0, "errors": 0, "details": []}

    with storage.db() as cx:
        # Ancres dont T+N est passe ET pas encore resolu pour cet horizon
        rows = cx.execute(
            "SELECT dcf.id, dcf.ticker, dcf.decision_type, dcf.decided_at, "
            "       dcf.anchor_price_eur, dcf.anchor_qty_before, dcf.anchor_currency "
            "FROM decision_counterfactual dcf "
            "WHERE dcf.decided_at <= ? "
            "  AND NOT EXISTS ("
            "      SELECT 1 FROM counterfactual_resolution cfr "
            "      WHERE cfr.decision_counterfactual_id = dcf.id "
            "        AND cfr.horizon_days = ?"
            "  )",
            (cutoff_iso, horizon_days),
        ).fetchall()

    if not rows:
        return out

    for r in rows:
        dcf_id, ticker, dtype, _decided_at, _anchor_price_eur, anchor_qty_before, _currency = r
        try:
            # Prix actuel a T+N (effectivement = aujourd'hui pour la 1ere resolution)
            cur_native = prices.get_current_price(ticker)
            if cur_native is None or cur_native != cur_native:
                out["skipped"] += 1
                out["details"].append({"dcf_id": dcf_id, "ticker": ticker, "reason": "no_price"})
                continue
            # Convert to EUR via gateway canonique shared.prices.
            # Migration Lane 2 #5 : élimine dépendance intelligence/→dashboard.render.
            from shared.prices import get_current_price_in_eur
            cur_eur = get_current_price_in_eur(ticker) or cur_native

            # Qty actuelle (post-decision)
            pos = positions_mod.get_position(ticker)
            current_qty = (pos.get("qty") if pos else 0) or 0

            # Valeurs
            actual_value_eur = current_qty * cur_eur
            counterfactual_value_eur = (anchor_qty_before or 0) * cur_eur
            delta_eur = actual_value_eur - counterfactual_value_eur

            # delta_pct : relatif au capital decisionne (= la difference de qty * anchor_price)
            # OU plus simple : relatif a la counterfactual_value
            if counterfactual_value_eur > 0:
                delta_pct = delta_eur / counterfactual_value_eur * 100
            else:
                delta_pct = 0.0

            # Verdict (seuils +/-2% delta_pct)
            if delta_pct > 2.0:
                verdict = "decision_beneficial"
            elif delta_pct < -2.0:
                verdict = "decision_harmful"
            else:
                verdict = "decision_neutral"

            with storage.db() as cx:
                cx.execute(
                    "INSERT INTO counterfactual_resolution ("
                    "  decision_counterfactual_id, ticker, horizon_days,"
                    "  price_at_horizon_native, price_at_horizon_eur,"
                    "  actual_value_eur, counterfactual_value_eur,"
                    "  delta_eur, delta_pct, verdict"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        dcf_id, ticker, horizon_days,
                        cur_native, cur_eur,
                        round(actual_value_eur, 2), round(counterfactual_value_eur, 2),
                        round(delta_eur, 2), round(delta_pct, 2), verdict,
                    ),
                )
                cx.commit()
            out["resolved"] += 1
            out["details"].append({
                "dcf_id": dcf_id, "ticker": ticker, "decision_type": dtype,
                "delta_eur": round(delta_eur, 0), "delta_pct": round(delta_pct, 1),
                "verdict": verdict,
            })
        except Exception as e:
            out["errors"] += 1
            log.warning(f"resolve dcf {dcf_id} {ticker} failed: {e}")
            out["details"].append({"dcf_id": dcf_id, "ticker": ticker, "error": str(e)[:100]})

    return out


# ─────────────────────── MEASURE : biais quantifie ─────────────────────────


_BIAS_PREDICATES: dict[str, dict[str, Any]] = {
    "vend_winners_trop_tot": {
        "decision_types": ("partial_exit", "full_exit"),
        "min_pnl_pct_at_decision": 10.0,  # winner = en gain >10%
        "description": "Sells de positions en gain >10% (biais #1 documente)",
    },
    "pas_vendre_crypto_top": {
        "decision_types": ("no_action_flag",),
        "tickers_filter": ("BTC", "ETH", "MSTR", "COIN", "IBIT"),  # proxy crypto
        "description": "Non-actions sur crypto en peak (biais #2 documente)",
    },
}


def measure_bias(
    bias_name: str = "vend_winners_trop_tot",
    horizon_days: int = 30,
) -> dict:
    """Quantifie le cout/benefice cumule d'un biais documente.

    Retourne :
      n_decisions          : decisions correspondant au predicat du biais
      n_with_resolution    : celles deja resolues a horizon_days
      n_decision_harmful   : la decision a sous-performe le contrefactuel
      n_decision_beneficial: la decision a sur-performe le contrefactuel
      avg_delta_pct        : delta moyen (signe : negatif = biais costly)
      cumulative_delta_eur : somme EUR (negatif = perte d'opportunite)
      statistical_significance: "wide" (n<10) | "tentative" (10-30) | "robust" (>30)
    """
    pred = _BIAS_PREDICATES.get(bias_name)
    if not pred:
        return {"error": f"unknown bias: {bias_name}"}

    types = pred["decision_types"]
    placeholders = ",".join("?" * len(types))

    with storage.db() as cx:
        # Toutes les decisions correspondant au predicat
        # Filtre 2 catégories de pollution append-only :
        # - VOIDED : trades fantomes corriges (cf decisions.reasoning '[VOIDED ')
        # - TEST_* : tickers synthetiques generes par tests e2e self_loop_v0
        #   (200+ rows polluees au 05/06/2026, vu via scripts/bias_ledger.py).
        #   Source-direct fix : on filtre query-time car la table cf est
        #   append-only par trigger -- impossible de delete les rows tests.
        test_filter = "AND dcf.ticker NOT LIKE 'TEST_%' AND dcf.ticker NOT LIKE 'test%'"
        all_rows = cx.execute(
            f"""SELECT dcf.id FROM decision_counterfactual dcf
                LEFT JOIN decisions d ON d.id = dcf.decision_id
                WHERE dcf.decision_type IN ({placeholders})
                  AND (d.reasoning IS NULL OR d.reasoning NOT LIKE '[VOIDED %')
                  {test_filter}""",
            types,
        ).fetchall()
        n_decisions = len(all_rows)

        # Celles resolues a horizon_days (meme filter VOIDED + TEST)
        resolved = cx.execute(
            f"""
            SELECT cfr.delta_eur, cfr.delta_pct, cfr.verdict
            FROM counterfactual_resolution cfr
            JOIN decision_counterfactual dcf ON dcf.id = cfr.decision_counterfactual_id
            LEFT JOIN decisions d ON d.id = dcf.decision_id
            WHERE dcf.decision_type IN ({placeholders})
              AND cfr.horizon_days = ?
              AND (d.reasoning IS NULL OR d.reasoning NOT LIKE '[VOIDED %')
              {test_filter}
            """,
            (*types, horizon_days),
        ).fetchall()

    n_with_resolution = len(resolved)
    if n_with_resolution == 0:
        sig = "wide"
        return {
            "bias_name": bias_name,
            "description": pred["description"],
            "horizon_days": horizon_days,
            "n_decisions": n_decisions,
            "n_with_resolution": 0,
            "avg_delta_pct": None,
            "cumulative_delta_eur": 0.0,
            "statistical_significance": sig,
            "verdict_distribution": {"harmful": 0, "neutral": 0, "beneficial": 0},
        }

    deltas_pct = [r[1] for r in resolved]
    deltas_eur = [r[0] for r in resolved]
    verdicts = [r[2] for r in resolved]

    avg = sum(deltas_pct) / len(deltas_pct)
    cumul = sum(deltas_eur)
    sig = "robust" if n_with_resolution > 30 else ("tentative" if n_with_resolution >= 10 else "wide")

    return {
        "bias_name": bias_name,
        "description": pred["description"],
        "horizon_days": horizon_days,
        "n_decisions": n_decisions,
        "n_with_resolution": n_with_resolution,
        "avg_delta_pct": round(avg, 2),
        "median_delta_pct": round(sorted(deltas_pct)[len(deltas_pct) // 2], 2),
        "cumulative_delta_eur": round(cumul, 2),
        "statistical_significance": sig,
        "verdict_distribution": {
            "harmful": sum(1 for v in verdicts if v == "decision_harmful"),
            "neutral": sum(1 for v in verdicts if v == "decision_neutral"),
            "beneficial": sum(1 for v in verdicts if v == "decision_beneficial"),
        },
    }


# ─────────────────────── INJECTION : prompt context ────────────────────────


def bias_context_for_prompt(
    ticker: str,  # noqa: ARG001  -- kept for V1 (per-ticker bias context)
    decision_type: str,
    current_pnl_pct: float | None = None,
    held_days: int | None = None,
) -> str:
    """Genere le bloc texte a injecter dans le prompt LLM pre-trade.

    Retourne "" si pas de biais pertinent OU mesure pas significative.

    Logique v0 :
    - decision_type sell + current_pnl > +10% + held > 14j -> winner sell
    - On regarde measure_bias("vend_winners_trop_tot") J+30
    - Si n_with_resolution >= 3 (seuil bas v0 pour boucler vite) et delta moyen
      negatif, on injecte le chiffre.
    """
    if decision_type not in ("partial_exit", "full_exit"):
        return ""
    if current_pnl_pct is None or current_pnl_pct < 10.0:
        return ""
    if held_days is not None and held_days < 14:
        return ""

    m = measure_bias("vend_winners_trop_tot", horizon_days=30)
    n = m.get("n_with_resolution", 0)
    if n < 3:
        # Pas assez de signal pour boucler -- on ne pollue pas le prompt
        return ""
    avg = m.get("avg_delta_pct")
    if avg is None or avg >= 0:
        # Le biais ne se manifeste pas (ou se manifeste a l'envers) -- on ne ment pas
        return ""

    cumul = m.get("cumulative_delta_eur", 0)
    sig = m.get("statistical_significance", "wide")
    sig_label = {"wide": "[signal tentative]", "tentative": "[signal robuste 10+]", "robust": "[signal fort 30+]"}[sig]

    return (
        f"BIAIS HISTORIQUE A SIGNALER {sig_label}\n"
        f"Sur les {n} dernieres fois ou tu as vendu un winner (>10% gain, "
        f"held >14j), le HOLD aurait sur-performe de {-avg:.1f}% en moyenne "
        f"a J+30 (cout cumule estime {cumul:+,.0f}€).\n"
        f"Demande explicitement : 'ma raison vend > raison hold ?' "
        f"avant de proceder."
    )


# ─────────────────────── CLI ───────────────────────────────────────────────


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "measure"

    if cmd == "resolve":
        horizon = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        result = resolve_due_anchors(horizon_days=horizon)
        print(f"resolve J+{horizon} : {result['resolved']} resolved, "
              f"{result['skipped']} skipped, {result['errors']} errors")
        for d in result["details"][:10]:
            print(f"  {d}")
    elif cmd == "measure":
        bias = sys.argv[2] if len(sys.argv) > 2 else "vend_winners_trop_tot"
        horizon = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        m = measure_bias(bias, horizon)
        print(json.dumps(m, indent=2, ensure_ascii=False))
    elif cmd == "context":
        # Test inject
        tk = sys.argv[2] if len(sys.argv) > 2 else "AMD"
        ctx = bias_context_for_prompt(tk, "partial_exit", current_pnl_pct=50.0, held_days=60)
        print(ctx if ctx else "(no context injected -- threshold not met)")
    else:
        print("Usage:")
        print("  python3 -m intelligence.self_loop measure [bias_name] [horizon_days]")
        print("  python3 -m intelligence.self_loop resolve [horizon_days]")
        print("  python3 -m intelligence.self_loop context [ticker]")
