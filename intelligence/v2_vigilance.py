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
    """Vigilance #3 : insider_buy_clusters_log doit avoir des entries detectees.

    Calibration affinee 30/05 (diagnostic iter 17) : un book large-cap AI a peu
    de clusters insider par nature (CEO/CFO d'un Nvidia vendent plus qu'ils
    n'achetent). 0 cluster != job casse necessairement.

    On differencie :
    - 0 cluster + 0 trade insider individuel detecte sur 30j -> ALERT (job casse)
    - 0 cluster + buys individuels existent mais sous seuil -> INFO (normal pour
      le profil book)
    - >= 1 cluster -> OK
    """
    n_clusters = cx.execute(
        "SELECT COUNT(*) c FROM insider_buy_clusters_log WHERE detected_at >= datetime('now', ?)",
        (f'-{days} days',),
    ).fetchone()['c']

    if n_clusters >= 3:
        return {
            "name": "insider_clusters_alive", "status": "OK", "days": days, "n": n_clusters,
            "message": f"{n_clusters} clusters detectes sur {days}j -- pipeline sain.",
        }
    if n_clusters >= 1:
        return {
            "name": "insider_clusters_alive", "status": "OK", "days": days, "n": n_clusters,
            "message": f"{n_clusters} cluster(s) detecte(s) sur {days}j -- pipeline alive.",
        }

    # 0 clusters -- differencier job casse vs univers sans buys
    # On regarde insider_snapshots (refresh quotidien) pour voir si des buys
    # individuels ont ete detectes recemment.
    try:
        any_buys = cx.execute(
            "SELECT COUNT(*) c FROM insider_snapshots WHERE snapshot_date >= date('now', ?) AND n_buys > 0",
            (f'-{days} days',),
        ).fetchone()['c']
    except Exception:
        any_buys = 0

    if any_buys == 0:
        status = "ALERT"
        msg = (f"0 cluster + 0 trade insider buy detecte sur {days}j. "
               f"Le job scheduled_insider_refresh_job tourne ? "
               f"Debug requis avant que ca pourrisse silencieusement.")
    else:
        status = "INFO"
        msg = (f"0 cluster sur {days}j MAIS {any_buys} snapshot(s) avec buys individuels. "
               f"Normal pour book large-cap AI (insider buys clusters rares). "
               f"Pas de bug -- seuils `_classify_buy_cluster` (n>=3 + $1M) sont juste "
               f"strict vs profil book. Si on veut plus de signal : abaisser seuil $.")

    return {
        "name": "insider_clusters_alive", "status": status, "days": days,
        "n": n_clusters, "any_individual_buys": any_buys, "message": msg,
    }


def check_horizon_diversification(cx, days: int = 60) -> dict[str, Any]:
    """W13 sante distribution #4 : horizons doivent etre diversifies, pas
    tous coinces sur 30j hardcode (bug v0 retro). Max-share bucket > 0.70
    = ALERT, > 0.55 = WARN."""
    rows = cx.execute(
        "SELECT horizon_days FROM predictions "
        "WHERE created_at >= datetime('now', ?) "
        "AND methodology_version != 'v0' "
        "AND horizon_days IS NOT NULL",
        (f"-{days} days",),
    ).fetchall()
    n = len(rows)
    if n < 10:
        return {
            "name": "horizon_diversification", "status": "INSUFFICIENT_DATA",
            "days": days, "n": n,
            "message": f"n={n} sur {days}j hors v0 -- besoin >=10 pour conclure.",
        }
    buckets = {"1-7": 0, "8-14": 0, "15-30": 0, "31-60": 0, "61+": 0}
    for r in rows:
        h = r[0] if not isinstance(r, dict) else r["horizon_days"]
        if h <= 7:
            buckets["1-7"] += 1
        elif h <= 14:
            buckets["8-14"] += 1
        elif h <= 30:
            buckets["15-30"] += 1
        elif h <= 60:
            buckets["31-60"] += 1
        else:
            buckets["61+"] += 1
    max_share = max(buckets.values()) / n
    nonempty = sum(1 for v in buckets.values() if v > 0)
    if max_share >= 0.70:
        status, msg = "ALERT", f"horizon mono-bucket ({max_share:.0%} dans 1 bucket /5) sur {n} preds {days}j."
    elif max_share >= 0.55 or nonempty <= 2:
        status, msg = "WARN", f"horizon peu diversifie ({max_share:.0%} max, {nonempty}/5 buckets) sur {n} preds {days}j."
    else:
        status, msg = "OK", f"horizon diversifie ({nonempty}/5 buckets, max {max_share:.0%}) sur {n} preds {days}j."
    return {
        "name": "horizon_diversification", "status": status, "days": days,
        "n": n, "max_share": max_share, "buckets": buckets, "message": msg,
    }


def check_conviction_distribution(cx) -> dict[str, Any]:
    """W13 sante distribution #5 : conviction theses actives doit etre
    etalee, pas concentree sur c5 (gate config 20%). > 35% c5 = WARN,
    > 50% = ALERT."""
    rows = cx.execute(
        "SELECT conviction, COUNT(*) AS n FROM theses WHERE status='active' "
        "GROUP BY conviction"
    ).fetchall()
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in rows:
        c = r[0] if not isinstance(r, dict) else r["conviction"]
        nn = r[1] if not isinstance(r, dict) else r["n"]
        if c in dist:
            dist[c] = int(nn)
    total = sum(dist.values())
    if total < 10:
        return {
            "name": "conviction_distribution", "status": "INSUFFICIENT_DATA",
            "n": total, "dist": dist,
            "message": f"n={total} theses actives -- besoin >=10 pour conclure.",
        }
    c5_share = dist[5] / total
    if c5_share >= 0.50:
        status, msg = "ALERT", f"inflation c5 : {dist[5]}/{total} ({c5_share:.0%}). Gate config = 20%."
    elif c5_share >= 0.35:
        status, msg = "WARN", f"accumulation c5 : {dist[5]}/{total} ({c5_share:.0%}). Gate config = 20%, attention."
    else:
        status, msg = "OK", f"c5={dist[5]} c4={dist[4]} c3={dist[3]} c2={dist[2]} c1={dist[1]} (n={total})"
    return {
        "name": "conviction_distribution", "status": status,
        "n": total, "dist": dist, "c5_share": c5_share, "message": msg,
    }


def check_fx_freshness(max_age_hours: int = 24) -> dict[str, Any]:
    """W13 sante distribution #6 : FX live frais (default 24h). Une pair en
    fallback hardcoded > max_age = ALERT (chiffres EUR drift en silence)."""
    from shared.prices import fx_is_stale, get_fx_rate

    pairs = [("USD", "EUR"), ("JPY", "EUR"), ("KRW", "EUR"), ("HKD", "EUR"), ("GBP", "EUR")]
    max_age_seconds = max_age_hours * 3600
    for f, t in pairs:
        get_fx_rate(f, t)
    stale = [(f, t) for f, t in pairs if fx_is_stale(f, t, max_age_seconds=max_age_seconds)]
    n_stale = len(stale)
    if n_stale == 0:
        return {
            "name": "fx_freshness", "status": "OK",
            "n_pairs": len(pairs), "n_stale": 0, "max_age_hours": max_age_hours,
            "message": f"{len(pairs)}/{len(pairs)} pairs FX live sous {max_age_hours}h.",
        }
    stale_str = ", ".join(f"{f}/{t}" for f, t in stale)
    status = "ALERT" if n_stale >= len(pairs) // 2 else "WARN"
    return {
        "name": "fx_freshness", "status": status,
        "n_pairs": len(pairs), "n_stale": n_stale,
        "stale_pairs": stale, "max_age_hours": max_age_hours,
        "message": f"{n_stale}/{len(pairs)} pairs FX stale > {max_age_hours}h : {stale_str}.",
    }


def run_all_vigilances() -> list[dict[str, Any]]:
    """Run les 6 vigilances + retourne list de results. Cron entry point.
    W13 (31/05) : extension scaffold ops -> sante distribution data."""
    from shared import storage

    results = []
    with storage.db() as cx:
        results.append(check_watch_rate(cx))
        results.append(check_directional_spread(cx))
        results.append(check_insider_clusters_alive(cx))
        results.append(check_horizon_diversification(cx))
        results.append(check_conviction_distribution(cx))
    results.append(check_fx_freshness())
    return results


def format_vigilance_report(results: list[dict[str, Any]]) -> str:
    """Format Telegram message. Skip si tous OK / INFO / INSUFFICIENT_DATA.
    Push uniquement les vrais signaux d'action (ALERT/WARN)."""
    alerting = [r for r in results if r['status'] in ('ALERT', 'WARN')]
    if not alerting:
        return ""  # pas de push si tout OK
    lines = [f"⚠️ V2 Vigilance ({len(alerting)} alerte(s))"]
    for r in alerting:
        emoji = "🚨" if r['status'] == "ALERT" else "⚡"
        lines.append(f"{emoji} {r['name']} : {r['message']}")
    return "\n".join(lines)
