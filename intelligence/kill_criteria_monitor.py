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


_PROMPT = """Tu evalues si les kill-criteria d'une these sont declenches, a risque, ou dormants.

THESE :
  - Ticker : {ticker}
  - Conviction : c{conviction}
  - Entry price : {entry_price}
  - Stop price : {stop_price}
  - Target full : {target_full}
  - Opened : {opened_at} (age : {age_days} jours)
  - Last reviewed : {last_reviewed} (delai : {days_since_review} jours)
  - Direction : {direction}

ETAT ACTUEL :
  - Current price : {current_price}
  - P&L vs entry : {pnl_pct:+.1f}%
  - Marge avant stop : {margin_to_stop_pct:+.1f}% (negatif = sous le stop)
  - Marge vers target : {margin_to_target_pct:+.1f}%

KILL-CRITERIA (invalidation_triggers definis par l'user a la creation) :
{triggers_block}

SIGNAUX RECENTS (30j, materialite ≥4/8) :
{signals_block}

══════════════════════ TACHE ══════════════════════

Pour CHAQUE kill-criterion liste, evalue :
  - status : "triggered" (declenche concretement aujourd'hui)
             "at_risk" (proche du declenchement OU signal d'alerte present)
             "dormant" (pas de signe d'invalidation)
  - reason : 1 phrase factuelle citant un nombre ou un signal_id

REGLES STRICTES :
- "triggered" = soit prix concret franchi (stop touche), soit signal concret
  (e.g. "TSMC capex miss publique"). Pas de speculation.
- "at_risk" = prix dans les 5% du stop OU signal d'alerte score>=5 sur le
  ticker OU age > horizon stipule sans atteindre target.
- "dormant" = par defaut.

Le STATUS GLOBAL de la these = pire des kill-criteria :
  any triggered -> triggered
  any at_risk -> at_risk
  sinon -> dormant

Reponds UNIQUEMENT en JSON :
{{
  "triggers_evaluated": [
    {{"trigger": "...", "status": "dormant|at_risk|triggered", "reason": "..."}}
  ],
  "global_status": "dormant|at_risk|triggered",
  "dominant_reason": "1 phrase qui resume le pire kill-criterion ou pourquoi tout est dormant",
  "evidence_quote": "1 fait concret cite (current_price=X, margin=Y%, signal_295)",
  "confidence": <0-100>
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
    # Notify on transition X -> triggered
    if new_status == "triggered" and (not prev or prev.get("status") != "triggered"):
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
    return result, aid


def check_all_active_theses() -> dict:
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT id, ticker, conviction, direction, opened_at, last_reviewed, "
            "entry_price, target_partial, target_full, stop_price, invalidation_triggers "
            "FROM theses WHERE status='active'"
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
