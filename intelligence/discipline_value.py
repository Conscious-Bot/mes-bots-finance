"""Valeur de la discipline (€) — LE compteur bidirectionnel canonique (GLOSSARY).

Chantier #20 (05/07/2026), le chiffre-produit de Path B : « la discipline t'a
rapporté/coûté X € ». GLOSSARY : « Coût du biais / valeur de la discipline —
le compteur bidirectionnel : somme signée des deltas contrefactuels. »

ZÉRO nouvel instrument (doctrine instrumentation-vs-décision) : pure agrégation
de matière déjà résolue + un capteur d'événement minimal (refus de gate digue,
logué dans bot_events — le trade REFUSÉ n'existe pas dans decisions, c'est le
seul trou de couverture).

Composition ANTI-DOUBLE-COMPTAGE :
- `decisions`   : contrefactuels de décisions résolus (counterfactual_resolution,
                  Boucle-de-soi V0). delta_eur = actual − counterfactual →
                  positif = la décision réelle a battu son alternative.
                  C'est le compteur PRINCIPAL.
- `digue_refusals` : achats refusés par la Digue 1 (events digue_buy_refused),
                  valorisés à ≥30j via price_history : refus d'un achat qui
                  aurait perdu = discipline POSITIVE (signe inversé du mouvement).
                  ADDITIF au compteur (pas dans decisions par construction).
- `bias_events` : LENS séparée (lock_in/fomo_greed résolus, bias_track_record).
                  SOUS-ENSEMBLE étiqueté des mêmes décisions → affiché à part,
                  JAMAIS additionné (double comptage sinon).
- `kill_overrides` : issues des overrides kill_switch (correct/failed) — counts
                  qualitatifs (falsification datée), pas encore valorisés €.

Honnêteté L21/L15 : chaque composant porte son N ; total None si rien de résolu ;
aucun zéro fabriqué présenté comme mesure.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from shared import storage

log = logging.getLogger(__name__)

# Mêmes filtres de pollution que self_loop.measure_bias (source des règles :
# VOIDED = trades fantômes corrigés ; TEST_% = fixtures e2e append-only
# impossibles à purger — filtre query-time canonique).
_POLLUTION_FILTER = (
    "AND dcf.ticker NOT LIKE 'TEST_%' AND dcf.ticker NOT LIKE 'test%' "
    "AND (d.reasoning IS NULL OR d.reasoning NOT LIKE '[VOIDED %')"
)

_REFUSAL_HORIZON_DAYS = 30  # aligné sur la résolution canonique +30j (B3)


def _decisions_component() -> dict[str, Any]:
    """Cumul signé des contrefactuels de décisions résolus (compteur principal)."""
    out: dict[str, Any] = {"n_resolved": 0, "cumul_eur": None, "by_type": {}, "by_verdict": {}}
    try:
        with storage.db_ro() as cx:
            rows = cx.execute(
                f"""SELECT dcf.decision_type, cr.verdict, cr.delta_eur
                    FROM counterfactual_resolution cr
                    JOIN decision_counterfactual dcf ON dcf.id = cr.decision_counterfactual_id
                    LEFT JOIN decisions d ON d.id = dcf.decision_id
                    WHERE cr.delta_eur IS NOT NULL {_POLLUTION_FILTER}"""
            ).fetchall()
    except Exception as e:
        log.warning(f"discipline_value decisions read failed: {e}")
        return out
    if not rows:
        return out
    cumul = 0.0
    for dtype, verdict, delta in rows:
        cumul += float(delta)
        t = out["by_type"].setdefault(dtype, {"n": 0, "eur": 0.0})
        t["n"] += 1
        t["eur"] = round(t["eur"] + float(delta), 2)
        v = out["by_verdict"].setdefault(verdict, {"n": 0, "eur": 0.0})
        v["n"] += 1
        v["eur"] = round(v["eur"] + float(delta), 2)
    out["n_resolved"] = len(rows)
    out["cumul_eur"] = round(cumul, 2)
    return out


def _digue_refusals_component() -> dict[str, Any]:
    """Achats refusés par la Digue 1, valorisés à +30j quand le prix existe.

    Convention : la discipline a EMPÊCHÉ l'achat → si le prix a BAISSÉ depuis le
    refus, la discipline a évité une perte → contribution POSITIVE.
    value_eur_refused ≈ qty × price au refus (loggé par le capteur).
    delta = −(px_h30/px_refus − 1) × valeur_refusée.
    """
    out: dict[str, Any] = {"n_events": 0, "n_valued": 0, "cumul_eur": None, "pending": 0}
    try:
        with storage.db_ro() as cx:
            evts = cx.execute(
                "SELECT timestamp, details FROM bot_events "
                "WHERE event_type = 'digue_buy_refused' ORDER BY timestamp"
            ).fetchall()
            out["n_events"] = len(evts)
            if not evts:
                return out
            cumul, n_valued = 0.0, 0
            now = datetime.now(UTC)
            for ts, details in evts:
                try:
                    d = json.loads(details) if isinstance(details, str) else (details or {})
                    tk = d.get("ticker")
                    qty = float(d.get("qty") or 0)
                    px0 = float(d.get("price") or 0)
                    if not tk or qty <= 0 or px0 <= 0:
                        continue
                    t0 = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    if t0.tzinfo is None:
                        t0 = t0.replace(tzinfo=UTC)
                    age = (now - t0).days
                    if age < _REFUSAL_HORIZON_DAYS:
                        out["pending"] += 1
                        continue
                    # prix ~+30j : premier close de price_history après t0+30j
                    h_date = (
                        t0.date().isoformat()
                    )  # borne basse ; on prend le 1er close >= t0+30j
                    row = cx.execute(
                        "SELECT price_native FROM price_history "
                        "WHERE ticker = ? AND substr(asof,1,10) >= date(?, '+30 day') "
                        "ORDER BY asof ASC LIMIT 1",
                        (tk, h_date),
                    ).fetchone()
                    if not row or not row[0]:
                        out["pending"] += 1
                        continue
                    px_h = float(row[0])
                    move_pct = px_h / px0 - 1.0
                    cumul += -move_pct * qty * px0  # baisse évitée = positif
                    n_valued += 1
                except Exception:
                    continue
            out["n_valued"] = n_valued
            out["cumul_eur"] = round(cumul, 2) if n_valued else None
    except Exception as e:
        log.warning(f"discipline_value refusals read failed: {e}")
    return out


def _bias_events_lens() -> dict[str, Any]:
    """Lens biais (lock_in/fomo_greed résolus) — SOUS-ENSEMBLE, jamais additionné."""
    out: dict[str, Any] = {"n_resolved": 0, "cumul_eur": None}
    try:
        from intelligence.bias_track_record import compute_all_bias_track_records

        with storage.db_ro() as cx:
            recs = compute_all_bias_track_records(cx)
        n = sum(int(r.get("n_resolved") or 0) for r in recs)
        out["n_resolved"] = n
        if n:
            out["cumul_eur"] = round(
                sum(float(r.get("total_delta_signed_eur") or 0.0) for r in recs), 2
            )
    except Exception as e:
        log.warning(f"discipline_value bias lens failed: {e}")
    return out


def _kill_overrides_component() -> dict[str, Any]:
    """Issues d'overrides kill_switch (falsification datée) — counts qualitatifs."""
    out: dict[str, Any] = {"override_correct": 0, "override_failed": 0}
    try:
        with storage.db_ro() as cx:
            for status, n in cx.execute(
                "SELECT status, COUNT(*) FROM kill_triggers "
                "WHERE status IN ('override_correct','override_failed') GROUP BY status"
            ).fetchall():
                out[status] = int(n)
    except Exception:
        pass  # table vide/absente = 0 (dormant)
    return out


def discipline_value_summary() -> dict[str, Any]:
    """LE compteur : {total_eur, n_total, components, asof}.

    total_eur = decisions + digue_refusals (additifs, disjoints par construction).
    None si AUCUN composant n'a de résolution (pas de zéro fabriqué — L15).
    bias_events = lens (sous-ensemble), exposée mais PAS dans le total.
    """
    decisions = _decisions_component()
    refusals = _digue_refusals_component()
    bias = _bias_events_lens()
    kill = _kill_overrides_component()

    parts = [c for c in (decisions["cumul_eur"], refusals["cumul_eur"]) if c is not None]
    total = round(sum(parts), 2) if parts else None
    n_total = decisions["n_resolved"] + refusals["n_valued"]
    return {
        "total_eur": total,
        "n_total": n_total,
        "asof": datetime.now(UTC).isoformat(),
        "components": {
            "decisions": decisions,
            "digue_refusals": refusals,
            "bias_events_lens": bias,
            "kill_overrides": kill,
        },
    }


if __name__ == "__main__":
    s = discipline_value_summary()
    d = s["components"]["decisions"]
    total = s["total_eur"]
    total_txt = "—" if total is None else f"{total:+,.0f} €"
    print(f"Valeur de la discipline : {total_txt} (N={s['n_total']})")
    if d["cumul_eur"] is not None:
        print(f"  décisions vs contrefactuel : {d['cumul_eur']:+,.0f} € sur {d['n_resolved']} résolues")
        for t, v in sorted(d["by_type"].items(), key=lambda x: x[1]["eur"]):
            print(f"    {t}: {v['eur']:+,.0f} € (n={v['n']})")
