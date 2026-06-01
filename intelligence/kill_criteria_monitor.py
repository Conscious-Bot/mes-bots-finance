"""Sprint 15 — Kill-criteria monitor.

Pour chaque these active :
  1. Lire invalidation_triggers (JSON) + current state (prix vs stop, age,
     P&L, recent signals score>=4)
  2. LLM Haiku evaluate : status (dormant | at_risk | triggered) + reason
  3. Persist dans kill_criteria_alerts si etat est nouveau ou si transition
  4. Notify Telegram sur transition X → triggered

Boucle d'apprentissage per la critique : "Logge chaque trim/add avec la
these et les criteres qui l'invalideraient (kill-criteria), puis re-score
plus tard. Alerte si un kill-criterion se declenche."
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from shared import llm, notify, storage

log = logging.getLogger(__name__)


_PROMPT = """Tu evalues si une these subit une DEGRADATION FONDAMENTALE VERIFIEE.

Pas d'opinion. Pas de prediction. Juste : est-ce que les fondamentaux du
ticker (revenue / margins / guidance / pricing power / customer concentration
/ reglementaire) montrent une cassure dans les signaux recents ?

THESE :
  - Ticker : {ticker}
  - Conviction : c{conviction}
  - Direction : {direction}
  - Entry / stop / target : {entry_price} / {stop_price} / {target_full}
  - Opened : {opened_at} ({age_days}j)

ETAT FINANCIER OBSERVABLE :
  - Current price : {current_price} | P&L vs entry : {pnl_pct:+.1f}%
  - Marge avant stop : {margin_to_stop_pct:+.1f}%

KILL-CRITERIA DEFINIS PAR L'USER A LA CREATION (LA seule source legitime) :
{triggers_block}

SIGNAUX RECENTS (30j, materialite ≥4/8) :
{signals_block}

══════════════════════ REGLES STRICTES (les violer = bug) ══════════════════════

INTERDIT de flag "at_risk" ou "triggered" sur :
  1. Chute de prix recente (le prix N'EST PAS un signal fundamental)
  2. Age these "jeune" / position recente (l'age N'EST PAS un signal)
  3. Calendrier de revue qui approche ("re-evaluation 30j" = minuteur, pas risque)
  4. "Aucun signal de confirmation" (absence != degradation)
  5. P&L negatif court terme (-5% sur 4j = bruit pas signal)
  6. Note macro non liee specifiquement au ticker
  7. Narratif tisse / chaine speculative (X annoncerait Y donc Z perd)
  8. Score signal 4-6 sans evidence fundamental specifique
  9. "Marge before stop < 20%" si stop pas approche (ce n'est pas le critere)

REQUIS pour flag "at_risk" : signaux montrent un DEBUT DE PATTERN de
degradation FONDAMENTALE VERIFIEE et specifique au ticker :
  - Revenue : declin annonce ou guidance baissier explicite
  - Margins : compression annoncee dans earnings/commentary
  - Guidance : baisse confirmation dans communiquee officielle
  - Pricing power : craquage observe (ex HBM pricing crack confirme)
  - Customer concentration : depart d'un client cle annonce
  - Reglementaire : decision adverse publique
  - Operations : disruption majeure documentee

REQUIS pour flag "triggered" : FAIT FONDAMENTAL avere, pas projection :
  - Guidance officiel baissier publie
  - Earnings miss publie
  - Customer announce departure
  - Regulatory ruling adverse

══════════════════════ DEFAUT : DORMANT ══════════════════════

Un bon moniteur se declenche RAREMENT. Si tu hesites -> dormant. Mieux
sous-flag que cry-wolf (qui pousse l'user a vendre les winners
sur du bruit, alimentant son biais documente #1 vend-trop-tot).

Reponds UNIQUEMENT en JSON :
{{
  "global_status": "dormant|at_risk|triggered",
  "fundamental_basis": "Quelle dimension fundamental est touchee si non-dormant (revenue|margin|guidance|pricing|customer|reglementaire|operations)",
  "evidence_quote": "Citation EXACTE du signal ou earnings/commentary specifique. Pas de paraphrase. signal_X 'TSMC bookings -15% guidance Q2'",
  "evidence_signal_ids": [signal_ids cites] | [],
  "rejection_reasons_applied": [liste des regles INTERDIT auxquelles tu n'as PAS cede : "price_drop_only", "age_only", "calendar_timer", "narrative_chain"...] | [],
  "confidence": <0-100>,
  "dominant_reason": "1 phrase. Si dormant : pourquoi clean. Si at_risk/triggered : quel pattern fondamental."
}}
"""


def _format_triggers(invalidation_triggers: str | list) -> str:
    if isinstance(invalidation_triggers, str):
        try:
            triggers = json.loads(invalidation_triggers)
        except Exception:
            triggers = [invalidation_triggers]
    else:
        triggers = invalidation_triggers or []
    if not triggers:
        return "  (aucun trigger explicite)"
    return "\n".join(f"  - {t}" for t in triggers[:8])


def _fetch_recent_signals(ticker: str) -> str:
    try:
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT id, timestamp, title, score "
                "FROM signals WHERE timestamp >= datetime('now', '-30 day') "
                "AND (entities LIKE ? OR title LIKE ?) "
                "AND score >= 4 ORDER BY timestamp DESC LIMIT 6",
                (f"%{ticker}%", f"%{ticker}%"),
            ).fetchall()
        if not rows:
            return "  (aucun signal materiel)"
        return "\n".join(
            f"  - signal_{r[0]} [{(r[1] or '')[:10]}] score={r[3]}: {(r[2] or '')[:130]}"
            for r in rows
        )
    except Exception:
        return "  (signal fetch failed)"


def _compute_current_state(thesis: dict) -> dict:
    """Get prices + ages."""
    try:
        from dashboard.render import _cached_price_eur

        current = _cached_price_eur(thesis["ticker"]) or 0
    except Exception:
        current = 0
    entry = thesis.get("entry_price") or 0
    stop = thesis.get("stop_price") or 0
    target_full = thesis.get("target_full") or 0
    pnl_pct = ((current - entry) / entry * 100) if entry else 0
    margin_to_stop = ((current - stop) / current * 100) if (current and stop) else 0
    margin_to_target = ((target_full - current) / current * 100) if (current and target_full) else 0
    opened = thesis.get("opened_at", "")
    age_days = 0
    if opened:
        try:
            from intelligence.portfolio_grade import _parse_dt_aware

            dt = _parse_dt_aware(opened)
            if dt:
                age_days = (datetime.now(UTC) - dt).days
        except Exception:
            pass
    last_rev = thesis.get("last_reviewed") or opened
    days_since_review = 0
    if last_rev:
        try:
            from intelligence.portfolio_grade import _parse_dt_aware

            dt = _parse_dt_aware(last_rev)
            if dt:
                days_since_review = (datetime.now(UTC) - dt).days
        except Exception:
            pass
    return {
        "current_price": f"{current:.2f}" if current else "?",
        "pnl_pct": pnl_pct,
        "margin_to_stop_pct": margin_to_stop,
        "margin_to_target_pct": margin_to_target,
        "age_days": age_days,
        "days_since_review": days_since_review,
    }


def check_one_thesis(thesis: dict) -> tuple[dict | None, int | None]:
    """Evaluate one thesis. Returns (result, alert_id) ; persists only if state
    transitioned or first time."""
    ticker = thesis["ticker"]
    triggers_raw = thesis.get("invalidation_triggers")
    if not triggers_raw or triggers_raw == "[]":
        log.info(f"kca {ticker} : no triggers, skip")
        return None, None

    state = _compute_current_state(thesis)
    prompt = _PROMPT.format(
        ticker=ticker,
        conviction=thesis.get("conviction", "?"),
        entry_price=thesis.get("entry_price", "?"),
        stop_price=thesis.get("stop_price", "?"),
        target_full=thesis.get("target_full", "?"),
        direction=thesis.get("direction", "?"),
        opened_at=(thesis.get("opened_at") or "")[:10],
        age_days=state["age_days"],
        last_reviewed=(thesis.get("last_reviewed") or "")[:10],
        days_since_review=state["days_since_review"],
        current_price=state["current_price"],
        pnl_pct=state["pnl_pct"],
        margin_to_stop_pct=state["margin_to_stop_pct"],
        margin_to_target_pct=state["margin_to_target_pct"],
        triggers_block=_format_triggers(triggers_raw),
        signals_block=_fetch_recent_signals(ticker),
    )
    try:
        result = llm.call_json(prompt, tier="extract", max_tokens=900)
    except Exception as e:
        log.warning(f"kca {ticker} LLM failed: {e}")
        return None, None
    if not isinstance(result, dict) or "global_status" not in result:
        return None, None

    new_status = result.get("global_status", "dormant")
    # Persist only if status changed from previous (avoid noise)
    prev = storage.get_latest_kca_per_thesis(thesis["id"])
    if prev and prev.get("status") == new_status and new_status == "dormant":
        # No change & dormant -> skip persistence (still useful for cron heartbeat)
        return result, None
    aid = storage.insert_kill_criteria_alert(
        thesis_id=thesis["id"],
        ticker=ticker,
        status=new_status,
        triggers_evaluated_json=json.dumps(result.get("triggers_evaluated") or [], ensure_ascii=False),
        dominant_reason=(result.get("dominant_reason") or "")[:400],
        evidence_quote=(result.get("evidence_quote") or "")[:300],
        confidence=int(result.get("confidence") or 50),
    )
    # Notify on transition X -> triggered (urgent)
    # Sprint 19 : aussi notify sur transition dormant -> at_risk (pre-alert)
    prev_status = prev.get("status") if prev else None
    if new_status == "triggered" and prev_status != "triggered":
        try:
            msg = (
                f"⚠️ KILL-CRITERION DECLENCHE — {ticker}\n"
                f"{result.get('dominant_reason', '')}\n\n"
                f"Evidence : {result.get('evidence_quote', '')}\n"
                f"Confidence : {result.get('confidence', '?')}/100\n\n"
                f"Action : /exit {ticker} ou /thesis_revisit {ticker}"
            )
            notify.send_text(msg)
            log.info(f"kca {ticker} : transition -> triggered, notified")
        except Exception as e:
            log.warning(f"kca notify failed: {e}")
        # v2.c.5 : wire_bias_trigger sur transition triggered, juste apres
        # notify (l'instant T fidele = quand la reco "sors" est dite a l'user).
        # Bias fomo_greed : resister a sortir une these cassee = tenir un
        # perdant. Ref stable par thesis_id (rule:kill_criteria_t{id}).
        # Fail-safe strict : un bug ici NE CASSE PAS le check ni la notify.
        try:
            from intelligence.bias_events import wire_bias_trigger
            from shared.prices import get_current_price_in_eur
            anchor_eur = get_current_price_in_eur(ticker)
            pos = storage.get_position_by_ticker(ticker)
            initial_qty = float(pos["qty"]) if pos and pos.get("qty") else 0.0
            if anchor_eur and initial_qty > 0:
                wire_bias_trigger([{
                    "ticker": ticker, "bias": "fomo_greed",
                    "discipline_said": {
                        "action": "exit",
                        "ref": f"rule:kill_criteria_t{thesis['id']}",
                    },
                    "horizon_days": 30,
                    "anchor_price_eur": anchor_eur,
                    "initial_qty": initial_qty,
                    "discipline_expected_delta": -initial_qty,  # exit full
                    "thesis_id": thesis["id"],
                    "source": "auto_detected",
                }])
        except Exception as e:
            log.warning(f"kca {ticker} : wire_bias_trigger failed: {e}")
    elif new_status == "at_risk" and prev_status == "dormant":
        # Pre-alert : these passe de dormant a at_risk (signal precoce)
        try:
            msg = (
                f"⚡ A RISQUE — {ticker}\n"
                f"{result.get('dominant_reason', '')}\n\n"
                f"Confidence : {result.get('confidence', '?')}/100 (pas declenche, signal precoce)\n\n"
                f"Action : surveiller, /thesis_revisit {ticker} si signal se renforce"
            )
            notify.send_text(msg)
            log.info(f"kca {ticker} : transition dormant -> at_risk, pre-alert notified")
        except Exception as e:
            log.warning(f"kca pre-alert failed: {e}")
    return result, aid


def check_all_active_theses() -> dict:
    """Check seulement les theses CANONIQUES actives (= ticker en position
    qty>0 status open). Exclut les fantomes / sorties / hors-perimetre."""
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT t.id, t.ticker, t.conviction, t.direction, t.opened_at, "
            "t.last_reviewed, t.entry_price, t.target_partial, t.target_full, "
            "t.stop_price, t.invalidation_triggers "
            "FROM theses t "
            "INNER JOIN positions p ON p.ticker = t.ticker "
            "WHERE t.status='active' AND p.qty > 0 AND p.status='open'"
        ).fetchall()
    cols = ["id", "ticker", "conviction", "direction", "opened_at", "last_reviewed",
            "entry_price", "target_partial", "target_full", "stop_price", "invalidation_triggers"]
    theses = [dict(zip(cols, r, strict=False)) for r in rows]
    out = {"triggered": 0, "at_risk": 0, "dormant": 0, "skipped": 0, "failed": 0}
    for th in theses:
        try:
            res, _ = check_one_thesis(th)
            if not res:
                out["skipped"] += 1
                continue
            out[res.get("global_status", "skipped")] = out.get(res.get("global_status", "skipped"), 0) + 1
        except Exception as e:
            log.warning(f"kca {th['ticker']} crashed: {e}")
            out["failed"] += 1
    return out
