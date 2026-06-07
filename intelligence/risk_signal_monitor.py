"""Sprint 20.b — Daily risk signal monitor (Phase 1.5 stage 2 refactor).

Scan signals table pour pattern matching avec les surveillance_signals
declarees dans config/risk_watch.yaml. Persiste l'evaluation dans la table
SQLite risk_signal_evaluations (append-only), notify Telegram sur transition.

Refactor 07/06 (doctrine L17 LESSONS) :
  - AVANT : lit + ecrit scripts/risk_watch.json (declaratif + live state melange)
  - APRES : lit config/risk_watch.yaml (declaratif via Pydantic-valide
    shared/risk_watch.load_risk_watch) + ecrit table DB
    (shared/storage.insert_risk_signal_evaluation)

Approche hybride :
  1. SQL filter : narrow aux signaux mentionnant tickers/keywords pertinents
  2. Haiku eval : interprete le corpus filtre vs le surveillance_signal context
  3. Persist evaluation dans table risk_signal_evaluations (append-only)
  4. Notify Telegram sur transition status

Pas une opinion bot, une evaluation de pattern. Si signaux disent
"Hyperscaler capex revision -10% 2026", -> capex_hyperscaler.status
passe a "at_risk" dans la table append-only.
"""

from __future__ import annotations

import json
import logging

from shared import llm, notify, storage

log = logging.getLogger(__name__)

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
    # Sprint 20.c — leading indicators corporate
    "insider_selling_cluster": {
        "tickers": [],  # special-cased : query insider_snapshots directly
        "keywords": ["insider sell", "insider selling", "Form 4", "10b5-1", "executive sale"],
    },
    "order_intake_softening": {
        "tickers": ["TSM", "ASML", "AMD", "AVGO", "MU", "ALAB", "COHR"],
        "keywords": [
            "order intake", "bookings decline", "lead time", "soft demand",
            "order book", "backlog decline", "demand softening",
        ],
    },
    "inventory_buildup": {
        "tickers": [],
        "keywords": [
            "inventory buildup", "DIO", "days inventory", "channel stuffing",
            "destocking", "channel inventory", "inventory correction",
        ],
    },
    "earnings_revisions": {
        "tickers": ["TSM", "ASML", "AMD", "AVGO", "MU", "ALAB"],
        "keywords": [
            "estimates revised", "estimates cut", "downward revision",
            "consensus cut", "analyst downgrade", "guidance lowered",
        ],
    },
}


def _fetch_insider_snapshots_for_surveillance() -> list[dict]:
    """Sprint 20.c — query insider_snapshots directement (pas via signals).

    Returns recent net insider activity sur tickers strategiques. Si net_m < -50
    sur un ticker, c'est un signal cluster smart money out.
    """
    try:
        tickers = (
            "'TSM','ASML','AMD','AVGO','MU','ALAB','COHR','ENTG','KLAC',"
            "'SNOW','GOOGL','AMZN','TSLA','TSMC'"
        )
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT ticker, snapshot_date, net_m, n_sells, n_buys, "
                "total_sells_m, total_buys_m "
                "FROM insider_snapshots "
                "WHERE snapshot_date >= date('now', '-30 day') "
                f"AND ticker IN ({tickers}) "
                "ORDER BY snapshot_date DESC, net_m ASC"
            ).fetchall()
        cols = ["ticker", "snapshot_date", "net_m", "n_sells", "n_buys",
                "total_sells_m", "total_buys_m"]
        # Take most recent per ticker
        seen = set()
        out = []
        for r in rows:
            d = dict(zip(cols, r, strict=False))
            if d["ticker"] in seen:
                continue
            seen.add(d["ticker"])
            out.append(d)
        return out
    except Exception as e:
        log.warning(f"insider_snapshots fetch failed: {e}")
        return []


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


def _evaluate_insider_cluster() -> dict:
    """Special case : evalue insider_selling_cluster via table insider_snapshots."""
    insiders = _fetch_insider_snapshots_for_surveillance()
    if not insiders:
        return {
            "status": "monitoring",
            "confidence": 50,
            "reason": "aucune donnee insider recente",
            "evidence_signal_ids": [],
        }
    # Heuristic : count tickers avec net_m < -50 (insider net selling > $50M sur 30j)
    big_sellers = [d for d in insiders if (d.get("net_m") or 0) < -50]
    moderate_sellers = [d for d in insiders if -50 <= (d.get("net_m") or 0) < -10]
    if len(big_sellers) >= 2:
        names = [f"{d['ticker']} ({d['net_m']:.0f}M$)" for d in big_sellers[:5]]
        return {
            "status": "triggered",
            "confidence": 85,
            "reason": (
                f"Cluster insider selling > 50M$/30j sur {len(big_sellers)} tickers "
                f"strategiques : {', '.join(names)}. Smart money out concret."
            ),
            "evidence_signal_ids": [],
        }
    if len(big_sellers) == 1:
        d = big_sellers[0]
        return {
            "status": "at_risk",
            "confidence": 72,
            "reason": (
                f"{d['ticker']} : net insider sells {d['net_m']:.0f}M$/30j "
                f"({d['n_sells']} sellers, {d['n_buys']} buyers). Solo mais materiel."
            ),
            "evidence_signal_ids": [],
        }
    if len(moderate_sellers) >= 3:
        names = [f"{d['ticker']} ({d['net_m']:.0f}M$)" for d in moderate_sellers[:5]]
        return {
            "status": "at_risk",
            "confidence": 60,
            "reason": f"Multi-ticker insider net selling -10/-50M$ : {', '.join(names)}",
            "evidence_signal_ids": [],
        }
    return {
        "status": "monitoring",
        "confidence": 70,
        "reason": "Activite insider normale, pas de cluster de selling significatif",
        "evidence_signal_ids": [],
    }


def evaluate_one_signal(surveillance_signal: dict) -> dict:
    """LLM Haiku evaluate one surveillance signal vs recent signals corpus.

    Sprint 20.c : insider_selling_cluster utilise une eval deterministe sur
    insider_snapshots table (pas via signals + LLM).
    """
    sig_id = str(surveillance_signal.get("id") or "")
    # Special case : insider cluster = eval deterministe (pas LLM)
    if sig_id == "insider_selling_cluster":
        return _evaluate_insider_cluster()

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
    """Iterate all risks x all surveillance_signals.

    Lit declaratif YAML (shared.risk_watch.load_risk_watch_with_live_state pour
    avoir prev_status depuis DB), evalue chaque signal via Haiku, append nouvelle
    evaluation en DB (risk_signal_evaluations), notify sur transition.

    Plus de write-back JSON (L17 doctrine)."""
    from typing import Any

    from shared.risk_watch import load_risk_watch_with_live_state

    data = load_risk_watch_with_live_state()
    if data is None:
        log.info("risk_watch absent (YAML + JSON fallback), skip")
        return {"error": "no_risk_watch"}

    out: dict[str, Any] = {
        "n_signals_evaluated": 0,
        "transitions": [],
        "current_statuses": {},
    }
    for risk in data.get("risks") or []:
        risk_id = risk.get("id") or "?"
        for sig in risk.get("surveillance_signals") or []:
            sig_id = sig.get("id") or "?"
            prev_status = sig.get("current_status", "monitoring")
            result = evaluate_one_signal(sig)
            new_status = result.get("status", "monitoring")
            transition = "changed" if new_status != prev_status else "no_change"

            # Persist en DB (append-only, plus de write-back JSON)
            evidence_ids = result.get("evidence_signal_ids", []) or []
            try:
                storage.insert_risk_signal_evaluation(
                    risk_id=risk_id,
                    signal_id=sig_id,
                    status=new_status,
                    reason=result.get("reason") or None,
                    confidence=result.get("confidence"),
                    evidence_ids_json=json.dumps(evidence_ids),
                    transition=transition,
                )
            except Exception as e:
                log.warning(
                    f"insert_risk_signal_evaluation failed risk={risk_id} "
                    f"sig={sig_id}: {e}"
                )

            out["n_signals_evaluated"] += 1
            out["current_statuses"][sig_id] = new_status

            # Notify on transition to at_risk or triggered
            if transition == "changed" and new_status in ("at_risk", "triggered"):
                msg = (
                    f"{'⚡' if new_status == 'at_risk' else '⚠️'} "
                    f"RISQUE {risk.get('name', '?')} — Signal "
                    f"{sig.get('label', '?')} passe {prev_status} → {new_status}\n\n"
                    f"Raison : {result.get('reason', '')}\n"
                    f"Confidence : {result.get('confidence', '?')}/100"
                )
                try:
                    notify.send_text(msg)
                except Exception as e:
                    log.warning(f"risk transition notify failed: {e}")
                out["transitions"].append({
                    "risk": risk.get("name"),
                    "signal": sig_id,
                    "from": prev_status,
                    "to": new_status,
                })

    log.info(
        f"risk_signal_monitor : {out['n_signals_evaluated']} signaux evalues, "
        f"{len(out['transitions'])} transitions persistees en DB"
    )
    return out
