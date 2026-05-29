"""Sprint 20.b — Daily risk signal monitor.

Scan signals table pour pattern matching avec les surveillance_signals
declarees dans risk_watch.json. Update current_status (monitoring -> at_risk
-> triggered) + notify Telegram sur transition.

Approche hybride :
  1. SQL filter : narrow aux signaux mentionnant tickers/keywords pertinents
  2. Haiku eval : interprete le corpus filtre vs le surveillance_signal context
  3. Persist current_status + last_checked_at directement dans risk_watch.json

Pas une opinion bot, une evaluation de pattern. Si signaux disent
"Hyperscaler capex revision -10% 2026", -> capex_hyperscaler.current_status
passe a "at_risk" automatiquement.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from shared import llm, notify, storage

log = logging.getLogger(__name__)


_RISK_WATCH_PATH = Path("scripts/risk_watch.json")

# Keywords par surveillance_signal id (SQL filter heuristique)
_KEYWORDS_BY_SIGNAL = {
    "capex_hyperscaler": {
        "tickers": ["MSFT", "META", "GOOGL", "AMZN"],
        "keywords": ["capex", "capital expenditure", "guidance", "spending", "cloud", "infrastructure"],
    },
    "asml_bookings": {
        "tickers": ["ASML"],
        "keywords": ["bookings", "orders", "backlog", "EUV", "high-NA", "litho"],
    },
    "tsm_monthly_rev": {
        "tickers": ["TSM", "TSMC"],
        "keywords": ["monthly", "revenue", "utilization", "N3", "N2", "wafer", "foundry"],
    },
    "hbm_pricing": {
        "tickers": ["MU", "Micron", "SK Hynix", "000660", "Samsung"],
        "keywords": ["HBM", "memory pricing", "DRAM", "Blackwell", "AI memory"],
    },
    "vix_credit": {
        "tickers": [],
        "keywords": ["VIX", "volatility", "IG spreads", "credit spreads", "risk-off", "duration"],
    },
    "wafer_pricing": {
        "tickers": ["4063", "Shin-Etsu", "Sumco"],
        "keywords": ["wafer pricing", "silicon", "300mm", "ASP", "wafer demand"],
    },
}


def _fetch_signals_for_surveillance(surveillance_id: str, lookback_days: int = 14) -> list[dict]:
    """SQL filter : signals matchant tickers + keywords du surveillance signal."""
    keys = _KEYWORDS_BY_SIGNAL.get(surveillance_id)
    if not keys:
        return []
    cutoff = f"datetime('now', '-{int(lookback_days)} day')"
    ticker_conds = " OR ".join(f"s.entities LIKE '%{tk}%'" for tk in keys["tickers"]) if keys["tickers"] else "0"
    kw_conds = " OR ".join(
        f"s.title LIKE '%{kw}%' OR s.summary LIKE '%{kw}%'" for kw in keys["keywords"]
    ) if keys["keywords"] else "0"
    where = f"s.timestamp >= {cutoff} AND ({ticker_conds} OR {kw_conds}) AND s.score >= 4"
    try:
        with storage.db() as cx:
            rows = cx.execute(
                f"SELECT s.id, s.timestamp, s.title, s.summary, s.score, "
                f"COALESCE(s.impact_magnitude, 0), src.name AS source "
                f"FROM signals s LEFT JOIN sources src ON s.source_id = src.id "
                f"WHERE {where} ORDER BY s.score DESC LIMIT 20"
            ).fetchall()
        cols = ["id", "timestamp", "title", "summary", "score", "impact", "source"]
        return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        log.warning(f"fetch_signals_for_surveillance {surveillance_id} failed: {e}")
        return []


_EVAL_PROMPT = """Tu evalues l'etat d'un signal de surveillance d'un risque
investisseur.

SIGNAL DE SURVEILLANCE :
  ID : {sig_id}
  Label : {label}
  Trigger : {trigger}
  Weight : {weight}

SIGNAUX RECENTS LIES (14 derniers jours) :
{signals_block}

TACHE : determine le status du signal de surveillance maintenant :
  - "monitoring" : pas de pattern alarmant dans les signaux recents
  - "at_risk"    : signaux suggerent debut de pattern declenchant (mais pas
                   encore confirme)
  - "triggered"  : pattern explicitement declenche (e.g. capex revision
                   baissiere annoncee, ASML miss bookings publique)

Reponds UNIQUEMENT en JSON :
{{
  "status": "monitoring|at_risk|triggered",
  "confidence": <0-100>,
  "reason": "1 phrase factuelle citant signal_id si pertinent",
  "evidence_signal_ids": [123, 456] | []
}}

Sois STRICT : "triggered" requiert evidence concrete dans les signaux.
"at_risk" requiert un debut de pattern, pas juste un sentiment.
"""


def evaluate_one_signal(surveillance_signal: dict) -> dict:
    """LLM Haiku evaluate one surveillance signal vs recent signals corpus."""
    sig_id = surveillance_signal.get("id")
    signals = _fetch_signals_for_surveillance(sig_id, lookback_days=14)
    if not signals:
        return {
            "status": "monitoring",
            "confidence": 50,
            "reason": "aucun signal recent matchant",
            "evidence_signal_ids": [],
        }
    signals_block = "\n".join(
        f"  - signal_{s['id']} [{(s['timestamp'] or '')[:10]}] score={s['score']} "
        f"impact={s['impact']:.0f}/5 src={s['source'] or '?'}: {(s['title'] or '')[:140]}"
        for s in signals[:15]
    )
    prompt = _EVAL_PROMPT.format(
        sig_id=sig_id,
        label=surveillance_signal.get("label", "?"),
        trigger=surveillance_signal.get("trigger", "?"),
        weight=surveillance_signal.get("weight", "?"),
        signals_block=signals_block,
    )
    try:
        result = llm.call_json(prompt, tier="extract", max_tokens=300)
        if isinstance(result, dict) and result.get("status") in ("monitoring", "at_risk", "triggered"):
            return result
    except Exception as e:
        log.warning(f"evaluate_one_signal {sig_id} failed: {e}")
    return {
        "status": "monitoring",
        "confidence": 30,
        "reason": "evaluation LLM failed",
        "evidence_signal_ids": [],
    }


def check_all_risks() -> dict:
    """Iterate all risks x all surveillance_signals, update statuses + notify."""
    if not _RISK_WATCH_PATH.exists():
        log.info("risk_watch.json absent, skip")
        return {"error": "no_risk_watch"}
    try:
        data = json.loads(_RISK_WATCH_PATH.read_text())
    except Exception as e:
        log.error(f"risk_watch.json parse failed: {e}")
        return {"error": str(e)}

    out = {"n_signals_evaluated": 0, "transitions": [], "current_statuses": {}}
    for risk in data.get("risks") or []:
        for sig in risk.get("surveillance_signals") or []:
            prev_status = sig.get("current_status", "monitoring")
            result = evaluate_one_signal(sig)
            new_status = result.get("status", "monitoring")
            sig["current_status"] = new_status
            sig["last_evaluated_at"] = datetime.now(UTC).isoformat()
            sig["last_eval_reason"] = result.get("reason", "")
            sig["last_eval_confidence"] = result.get("confidence", 0)
            sig["last_eval_evidence_ids"] = result.get("evidence_signal_ids", [])
            out["n_signals_evaluated"] += 1
            out["current_statuses"][sig.get("id", "?")] = new_status

            # Notify on transition to at_risk or triggered
            if new_status != prev_status and new_status in ("at_risk", "triggered"):
                msg = (
                    f"{'⚡' if new_status == 'at_risk' else '⚠️'} "
                    f"RISQUE {risk.get('name', '?')} — Signal {sig.get('label', '?')} "
                    f"passe {prev_status} → {new_status}\n\n"
                    f"Raison : {result.get('reason', '')}\n"
                    f"Confidence : {result.get('confidence', '?')}/100"
                )
                try:
                    notify.send_text(msg)
                except Exception as e:
                    log.warning(f"risk transition notify failed: {e}")
                out["transitions"].append({
                    "risk": risk.get("name"),
                    "signal": sig.get("id"),
                    "from": prev_status,
                    "to": new_status,
                })

    try:
        _RISK_WATCH_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        log.error(f"risk_watch.json write failed: {e}")
        return {"error": f"write_failed: {e}"}

    log.info(
        f"risk_signal_monitor : {out['n_signals_evaluated']} signaux evalues, "
        f"{len(out['transitions'])} transitions"
    )
    return out
