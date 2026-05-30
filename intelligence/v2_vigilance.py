"""Vigilances V2 -- alarmes automatiques sur les 3 patterns identifies decision log #01.

Sans ces vigilances, les 3 risques signales doivent etre surveilles a la main :
1. Watch-rate distribution dans le temps : si > 50% sur 4 semaines = ancrage par defaut cote refus
2. Distribution prob cohorte directionnelle : si tous calls dans [0.60-0.62] sur 4 mois = mono-bucket demenage
3. Insider clusters detectes : si 0 cluster sur 30j alors que le wire est actif = scheduled_buy_cluster_scan_job casse OU seuil trop strict

Ce module produit un dict de vigilance + status (OK/WARN/ALERT). Le cron weekly
(`bot/jobs/periodic.weekly_v2_vigilance_check_job` a wirer) appelle ce module
et push Telegram si !OK.

V2-source-of-truth : signal_scorer_v2 (cf memoire scorer-v2-canonical).
"""

import logging
from typing import Any

log = logging.getLogger(__name__)

# Seuils -- a re-tuner empiriquement post-aout quand N V2 suffisant
WATCH_RATE_HIGH_THRESHOLD = 0.85   # >85% watch sur 4 semaines = ancrage refus
WATCH_RATE_LOW_THRESHOLD = 0.20    # <20% watch = sur-commitment
PROB_SPREAD_MIN_BUCKETS = 3        # cohorte directionnelle doit etre dans >=3 buckets uniques
PROB_SPREAD_MIN_STD = 0.05         # std deviation cohorte directionnelle min
INSIDER_CLUSTER_DEAD_DAYS = 30     # si 0 cluster detecte sur 30j = job casse / seuil trop strict


def _get_v2_signals_since(cx, days: int) -> list[dict]:
    """V2 signals = source dans (SEC EDGAR 8-K, SEC EDGAR Insider Cluster) qui ont
    genere des predictions. On lit signals + leurs predictions associees."""
    rows = cx.execute(
        """SELECT sig.id sig_id, sig.timestamp, sig.gmail_id, src.name src_name,
                  p.id pred_id, p.direction, p.probability_at_creation
           FROM signals sig
           JOIN sources src ON sig.source_id = src.id
           LEFT JOIN predictions p ON p.signal_id = sig.id
           WHERE src.name IN ('SEC EDGAR 8-K', 'SEC EDGAR Insider Cluster')
             AND sig.timestamp >= datetime('now', ?)
           ORDER BY sig.timestamp DESC""",
        (f'-{days} days',),
    ).fetchall()
    return [dict(r) for r in rows]


def check_watch_rate(cx, days: int = 28) -> dict[str, Any]:
    """Vigilance #1 : watch-rate distribution sur N derniers jours."""
    sigs = _get_v2_signals_since(cx, days)
    n_total = len({s['sig_id'] for s in sigs})  # dedup par signal
    n_with_pred = len({s['sig_id'] for s in sigs if s['pred_id']})
    n_watch = n_total - n_with_pred  # watch = signal sans prediction (V2 a dit watch)

    if n_total == 0:
        return {
            "name": "watch_rate", "status": "INSUFFICIENT_DATA", "days": days,
            "n_total": 0, "n_watch": 0, "watch_rate": None,
            "message": f"Aucun signal V2 sur {days}j -- attendre data."
        }

    watch_rate = n_watch / n_total
    if watch_rate > WATCH_RATE_HIGH_THRESHOLD:
        status = "ALERT"
        msg = (f"Watch rate {watch_rate * 100:.0f}% sur {days}j (n={n_total}). "
               f"Au-dessus seuil {WATCH_RATE_HIGH_THRESHOLD * 100:.0f}% = nouvel ancrage "
               f"par defaut cote refus. V2 refuse tout, sourcing peut-etre encore trop faible.")
    elif watch_rate < WATCH_RATE_LOW_THRESHOLD:
        status = "ALERT"
        msg = (f"Watch rate {watch_rate * 100:.0f}% sur {days}j (n={n_total}). "
               f"En-dessous seuil {WATCH_RATE_LOW_THRESHOLD * 100:.0f}% = sur-commitment, "
               f"V2 force des weak en ledger comme directionnels.")
    else:
        status = "OK"
        msg = f"Watch rate {watch_rate * 100:.0f}% sur {days}j (n={n_total}) -- sain."

    return {
        "name": "watch_rate", "status": status, "days": days,
        "n_total": n_total, "n_watch": n_watch, "watch_rate": round(watch_rate, 3),
        "message": msg
    }


def check_directional_spread(cx, days: int = 120) -> dict[str, Any]:
    """Vigilance #2 : distribution prob cohorte directionnelle sur N derniers jours."""
    import statistics

    sigs = _get_v2_signals_since(cx, days)
    probs = [s['probability_at_creation'] for s in sigs
             if s['pred_id'] and s['probability_at_creation'] is not None]

    if len(probs) < 5:
        return {
            "name": "directional_spread", "status": "INSUFFICIENT_DATA", "days": days,
            "n_directional": len(probs),
            "message": f"Cohorte directionnelle n={len(probs)} sur {days}j -- attendre N>=5."
        }

    unique_buckets = len({round(p, 2) for p in probs})
    std = statistics.stdev(probs) if len(probs) >= 2 else 0
    prob_range = (min(probs), max(probs))

    if unique_buckets < PROB_SPREAD_MIN_BUCKETS:
        status = "ALERT"
        msg = (f"Cohorte directionnelle n={len(probs)} : seulement {unique_buckets} buckets uniques "
               f"sur {days}j (seuil {PROB_SPREAD_MIN_BUCKETS}). Range {prob_range[0]:.2f}-{prob_range[1]:.2f}. "
               f"Mono-bucket demenage encore une fois. Verifier sourcing diversite OU prompt V2 cap.")
    elif std < PROB_SPREAD_MIN_STD:
        status = "WARN"
        msg = (f"Cohorte directionnelle n={len(probs)} : std={std:.3f} sur {days}j "
               f"(seuil {PROB_SPREAD_MIN_STD}). Spread faible. Range {prob_range[0]:.2f}-{prob_range[1]:.2f}.")
    else:
        status = "OK"
        msg = (f"Cohorte directionnelle n={len(probs)} : {unique_buckets} buckets, "
               f"std={std:.3f}, range {prob_range[0]:.2f}-{prob_range[1]:.2f} sur {days}j -- sain.")

    return {
        "name": "directional_spread", "status": status, "days": days,
        "n_directional": len(probs), "unique_buckets": unique_buckets, "std": round(std, 3),
        "range": (round(prob_range[0], 3), round(prob_range[1], 3)),
        "message": msg
    }


def check_insider_clusters_alive(cx, days: int = 30) -> dict[str, Any]:
    """Vigilance #3 : insider_buy_clusters_log doit avoir des entries detectees."""
    n = cx.execute(
        "SELECT COUNT(*) c FROM insider_buy_clusters_log WHERE detected_at >= datetime('now', ?)",
        (f'-{days} days',),
    ).fetchone()['c']

    if n == 0:
        status = "ALERT"
        msg = (f"0 cluster insider detecte sur {days}j. scheduled_buy_cluster_scan_job tourne ? "
               f"Seuil `is_buy_cluster` trop strict ? Debug requis avant que ca pourrisse silencieusement.")
    elif n < 3:
        status = "WARN"
        msg = f"Seulement {n} cluster(s) detecte(s) sur {days}j -- faible. A surveiller."
    else:
        status = "OK"
        msg = f"{n} clusters detectes sur {days}j -- pipeline insider sain."

    return {
        "name": "insider_clusters_alive", "status": status, "days": days,
        "n": n, "message": msg
    }


def run_all_vigilances() -> list[dict[str, Any]]:
    """Run les 3 vigilances + retourne list de results. Cron entry point."""
    from shared import storage

    results = []
    with storage.db() as cx:
        results.append(check_watch_rate(cx))
        results.append(check_directional_spread(cx))
        results.append(check_insider_clusters_alive(cx))
    return results


def format_vigilance_report(results: list[dict[str, Any]]) -> str:
    """Format Telegram message. Skip si tous OK ou INSUFFICIENT_DATA."""
    alerting = [r for r in results if r['status'] in ('ALERT', 'WARN')]
    if not alerting:
        return ""  # pas de push si tout OK
    lines = [f"⚠️ V2 Vigilance ({len(alerting)} alerte(s))"]
    for r in alerting:
        emoji = "🚨" if r['status'] == "ALERT" else "⚡"
        lines.append(f"{emoji} {r['name']} : {r['message']}")
    return "\n".join(lines)
