"""Calibration audit du scorer V2 -- reliability diagram + Wilson CI par bucket.

Vigilance #4 (post tennis-bot audit harvest 31/05/2026) :
"Quand le scorer dit 70%, ca realise reellement a 70% ?"

Discipline applicable : voir CONVENTIONS.md section "Discipline statistique pour mesures
de track-record" (5 regles obligatoires : dedup, Wilson CI, bootstrap CI, distinguer
metrique-mesure vs business, reporting 7-items).

Cron wire : bot/jobs/periodic.weekly_calibration_audit_job (dimanche 22h),
push Telegram si transition status notable (INSUFFICIENT_DATA -> verdict, OK -> WARN, etc).

Dashboard surface : dashboard/render.py _calibration_progress_panel() dans Bloc 4 vigie.

S'active automatiquement quand on a >= MIN_N_TOTAL predictions resolved non-neutral.
Trigger = DATA, pas DATE : pas de calendrier arbitraire, juste accumulation cohorte.

Logique :
- Query predictions WHERE resolved_at IS NOT NULL AND brier_score IS NOT NULL
  (= neutrals exclus, cf math_helpers.brier_for et CONVENTIONS regle dedup)
- Normalise probability_at_creation a [0.5, 1.0] selon direction
  (direction='long' -> prob direct ; 'short' -> 1-prob)
- Bucket [0.5-0.6, 0.6-0.7, ..., 0.9-1.0]
- WR observed = count(correct) / count(correct + incorrect) par bucket
- Wilson CI 95% par bucket
- Verdict : OK / OVERCONFIDENT / UNDERCONFIDENT / INSUFFICIENT_DATA

Discipline post-Bailey-LdP (cf CONVENTIONS section "Discipline statistique") :
- Refus de conclure si n < MIN_N_PER_BUCKET (10) par bucket -> "n insuffisant"
- Refus de verdict global si total resolved < MIN_N_TOTAL (30)
- Wilson CI obligatoire (jamais point estimate seule)

Pattern : aligne v2_vigilance.py (status dict OK/WARN/ALERT, cron-friendly).

Origine : adapte de tennis-bot calibration_audit.py (audit 30-31/05/2026).
"""

from __future__ import annotations

import logging
import math
from typing import Any

log = logging.getLogger(__name__)

# Seuils discipline
MIN_N_TOTAL = 30           # < 30 resolved (non-neutral) -> INSUFFICIENT_DATA global
MIN_N_PER_BUCKET = 10      # < 10 par bucket -> "n insuffisant" pour ce bucket
MAX_CALIBRATION_GAP = 0.10  # gap > 10pp dans 2+ buckets = ALERT
WARN_CALIBRATION_GAP = 0.05  # gap > 5pp dans 1+ bucket = WARN

# Buckets de probability normalisee
BUCKETS = [
    (0.50, 0.60), (0.60, 0.70), (0.70, 0.80),
    (0.80, 0.90), (0.90, 1.01),  # 1.01 inclut prob=1.0
]


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval 95% pour proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def _normalize_prob(prob: float | None, direction: str) -> float | None:
    """Normalize probability to conviction strength in [0.5, 1.0].

    Table predictions stocke 'direction' = SENTIMENT du signal (cf CONVENTIONS section 2 :
    "Sentiment signal : bullish | bearish | neutral"), pas direction position
    (long/short/watch qui s'applique aux theses, pas aux predictions/signaux).

    - direction='bullish' -> prob directement (signal predit hausse, fort si prob haute)
    - direction='bearish' -> 1-prob (signal predit baisse, fort si prob basse)
    - direction='neutral' / 'watch' / autre -> None (pas une prediction directionnelle)
    """
    if prob is None:
        return None
    if direction == "bullish":
        return prob if prob >= 0.5 else None
    if direction == "bearish":
        flipped = 1.0 - prob
        return flipped if flipped >= 0.5 else None
    return None


def _get_resolved_predictions(cx, days: int | None = None) -> list[dict]:
    """Recupere predictions resolved avec brier_score non-NULL (neutrals exclus).

    Args:
        cx: sqlite3 connection
        days: optionnel, limite aux N derniers jours (depuis resolved_at). None = toutes.
    """
    if days is not None:
        sql = (
            "SELECT id, ticker, direction, probability_at_creation, outcome, "
            "brier_score, resolved_at "
            "FROM predictions "
            "WHERE resolved_at IS NOT NULL "
            "AND brier_score IS NOT NULL "
            "AND probability_at_creation IS NOT NULL "
            "AND methodology_version != 'v0' "
            "AND resolved_at >= datetime('now', ?) "
            "ORDER BY resolved_at DESC"
        )
        rows = cx.execute(sql, (f"-{days} days",)).fetchall()
    else:
        sql = (
            "SELECT id, ticker, direction, probability_at_creation, outcome, "
            "brier_score, resolved_at "
            "FROM predictions "
            "WHERE resolved_at IS NOT NULL "
            "AND brier_score IS NOT NULL "
            "AND probability_at_creation IS NOT NULL "
            "AND methodology_version != 'v0' "
            "ORDER BY resolved_at DESC"
        )
        rows = cx.execute(sql).fetchall()
    return [dict(r) for r in rows]


def compute_brier_by_source(cx, days: int = 180) -> list[dict[str, Any]]:
    """#72 LOOP -- Disaggregation Brier par signal source (rolling window).

    Permet d'identifier les sources qui sous-performent en calibration
    et les retirer/downweight. Sans cette desagregation, le Brier moyen
    global masque les ecarts.

    Returns list de dicts (par source name) :
      - source_name (str)
      - n_resolved (int) : predictions resolved non-neutral via cette source
      - brier_avg (float)
      - brier_ic95_low, brier_ic95_high (Wilson sur l'accuracy underlying)
      - accuracy (float) : % correct (helper)
      - status : 'OK' (brier <= 0.20), 'WARN' (<= 0.25), 'ALERT' (> 0.25),
                'INSUFFICIENT_DATA' (n < 5)

    Trie par n_resolved DESC. Sources avec n=0 sur la fenetre sont omises.

    Note : un Brier eleve sur une source bien-calibree peut etre du a un
    signal-to-noise faible. La metrique est diagnostique, pas autoritaire
    -- a contextualiser avec evidence_strength dans scoring_trace_json.
    """
    rows = cx.execute(
        """SELECT
              COALESCE(s.name, '?') AS source_name,
              p.brier_score, p.outcome
           FROM predictions p
           LEFT JOIN signals sig ON sig.id = p.signal_id
           LEFT JOIN sources s ON s.id = sig.source_id
           WHERE p.resolved_at IS NOT NULL
             AND p.brier_score IS NOT NULL
             AND p.probability_at_creation IS NOT NULL
             AND p.methodology_version != 'v0'
             AND p.outcome IN ('correct', 'incorrect')
             AND p.resolved_at >= datetime('now', ?)
           ORDER BY p.resolved_at DESC""",
        (f"-{days} days",),
    ).fetchall()

    by_src: dict[str, list[tuple[float, str]]] = {}
    for r in rows:
        # Tuple access -- row_factory-agnostic
        name = r[0] if not isinstance(r, dict) else r["source_name"]
        brier = r[1] if not isinstance(r, dict) else r["brier_score"]
        outcome = r[2] if not isinstance(r, dict) else r["outcome"]
        by_src.setdefault(name, []).append((float(brier), str(outcome)))

    out: list[dict[str, Any]] = []
    for src_name, items in by_src.items():
        n = len(items)
        if n == 0:
            continue
        brier_avg = sum(b for b, _ in items) / n
        n_correct = sum(1 for _, o in items if o == "correct")
        accuracy = n_correct / n
        # Wilson 95 sur accuracy
        if n >= 1:
            z = 1.96
            denom = 1 + z * z / n
            center = (n_correct + z * z / 2) / n / denom
            half = z * math.sqrt(accuracy * (1 - accuracy) / n + z * z / (4 * n * n)) / denom
            ic_lo = max(0.0, center - half)
            ic_hi = min(1.0, center + half)
        else:
            ic_lo, ic_hi = 0.0, 1.0

        if n < 5:
            status = "INSUFFICIENT_DATA"
        elif brier_avg <= 0.20:
            status = "OK"
        elif brier_avg <= 0.25:
            status = "WARN"
        else:
            status = "ALERT"

        out.append({
            "source_name": src_name,
            "n_resolved": n,
            "brier_avg": round(brier_avg, 4),
            "accuracy": round(accuracy, 3),
            "brier_ic95_low": round(ic_lo, 3),
            "brier_ic95_high": round(ic_hi, 3),
            "status": status,
        })

    out.sort(key=lambda d: -d["n_resolved"])
    return out


def recalibrate_source_credibility(
    cx,
    days: int = 180,
    min_n: int = 10,
    learning_rate: float = 0.3,
    floor: float = 0.30,
    ceiling: float = 0.95,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """#76 LOOP -- Recal credibility par source via Brier empirique.

    Cron mensuel (1er du mois). Pour chaque source avec n>=min_n
    resolutions sur la fenetre :
      target_credibility = 1 - brier_avg, clipped [floor, ceiling]
      new_credibility = old + learning_rate * (target - old)

    learning_rate=0.3 = moyenne ponderee glissante stable (pas de jump
    violent) -- pattern recommande pour scoring dynamique.

    Args:
        cx: connexion sqlite3
        days: fenetre rolling pour Brier (default 180j)
        min_n: minimum resolutions pour considerer la source (default 10)
        learning_rate: poids du nouveau signal (0.3 = 30% bouge,
                       70% inertie)
        floor: credibility minimum (eviter signal mort)
        ceiling: credibility maximum (eviter overconfidence)
        dry_run: si True, calcule sans appliquer (audit)

    Returns:
        Liste de dicts par source recalibree :
            {source_name, n_resolved, brier_avg, old_cred, new_cred,
             delta, applied (bool)}
        Sources avec n<min_n sont retournees aussi avec
        applied=False + new_cred=old_cred.

    Sans recal automatique, les sources se degradent silently. Boucle
    learning = mesure -> ajustement -> mesure.
    """
    brier_per_src = compute_brier_by_source(cx, days=days)

    out: list[dict[str, Any]] = []
    for s in brier_per_src:
        name = s["source_name"]
        n = s["n_resolved"]
        brier_avg = s["brier_avg"]

        old_row = cx.execute(
            "SELECT credibility FROM sources WHERE name=?", (name,)
        ).fetchone()
        old_cred = float(old_row[0]) if old_row and old_row[0] is not None else 0.5

        if n < min_n:
            out.append({
                "source_name": name,
                "n_resolved": n,
                "brier_avg": brier_avg,
                "old_cred": old_cred,
                "new_cred": old_cred,
                "delta": 0.0,
                "applied": False,
                "reason": f"n<{min_n}",
            })
            continue

        target_cred = max(floor, min(ceiling, 1.0 - brier_avg))
        new_cred = old_cred + learning_rate * (target_cred - old_cred)
        new_cred = max(floor, min(ceiling, new_cred))
        delta = new_cred - old_cred

        applied = False
        if not dry_run and abs(delta) >= 0.001:
            cx.execute(
                "UPDATE sources SET credibility=? WHERE name=?",
                (round(new_cred, 4), name),
            )
            cx.commit()
            applied = True
            log.info(
                f"recal credibility {name}: {old_cred:.3f} -> {new_cred:.3f} "
                f"(brier={brier_avg:.3f}, n={n})"
            )

        out.append({
            "source_name": name,
            "n_resolved": n,
            "brier_avg": brier_avg,
            "old_cred": round(old_cred, 4),
            "new_cred": round(new_cred, 4),
            "delta": round(delta, 4),
            "applied": applied,
            "reason": "dry_run" if dry_run else "ok",
        })

    return out


def check_scorer_calibration(cx, days: int | None = None) -> dict[str, Any]:
    """Reliability diagram + verdict scorer V2 calibration.

    Returns dict avec:
        - name : "scorer_calibration"
        - status : OK / WARN / ALERT / INSUFFICIENT_DATA
        - n_total : nb predictions analysees (post-dedup neutrals)
        - buckets : liste de dicts par bucket {range, n, wr_obs, wr_lo, wr_hi, pred_mean, gap_pp, verdict}
        - avg_brier : Brier score moyen
        - message : verdict humain pour Telegram / dashboard
        - days : fenetre temporelle (None = all)
    """
    preds = _get_resolved_predictions(cx, days=days)

    # Normalize + bucket-assign
    normalized = []
    for p in preds:
        norm_prob = _normalize_prob(p["probability_at_creation"], p["direction"])
        if norm_prob is None:
            continue  # skip watch ou prob non-directionnelle
        # outcome correct si signal va dans sens predit
        # direction='long' + outcome='correct' = TRUE
        # direction='short' + outcome='correct' = TRUE (le short etait correct)
        is_correct = p["outcome"] == "correct"
        normalized.append({
            "ticker": p["ticker"],
            "norm_prob": norm_prob,
            "is_correct": is_correct,
            "brier": p["brier_score"],
        })

    n_total = len(normalized)
    if n_total < MIN_N_TOTAL:
        return {
            "name": "scorer_calibration",
            "status": "INSUFFICIENT_DATA",
            "n_total": n_total, "days": days, "buckets": [], "avg_brier": None,
            "message": (
                f"Calibration audit : n={n_total} predictions resolved non-neutral "
                f"(<{MIN_N_TOTAL} requis). Trigger = accumulation, pas date. "
                f"S'active automatiquement des que seuil atteint."
            ),
        }

    # Bucket aggregation
    bucket_stats = []
    n_buckets_with_data = 0
    n_buckets_overconf = 0  # bucket ou pred >> obs
    n_buckets_underconf = 0  # bucket ou pred << obs
    max_gap = 0.0
    for lo, hi in BUCKETS:
        in_bucket = [n for n in normalized if lo <= n["norm_prob"] < hi]
        n_b = len(in_bucket)
        if n_b == 0:
            bucket_stats.append({
                "range_lo": lo, "range_hi": hi, "n": 0,
                "wr_obs": None, "wr_lo": None, "wr_hi": None,
                "pred_mean": None, "gap_pp": None, "verdict": "empty",
            })
            continue
        k_correct = sum(1 for n in in_bucket if n["is_correct"])
        wr_obs = k_correct / n_b
        pred_mean = sum(n["norm_prob"] for n in in_bucket) / n_b
        wr_lo, wr_hi = _wilson_ci(k_correct, n_b)
        gap = wr_obs - pred_mean  # >0 = underconf (modele rabote), <0 = overconf
        if n_b < MIN_N_PER_BUCKET:
            verdict = "n insuffisant"
        elif gap > WARN_CALIBRATION_GAP:
            verdict = "UNDERCONFIDENT"
            n_buckets_underconf += 1
        elif gap < -WARN_CALIBRATION_GAP:
            verdict = "OVERCONFIDENT"
            n_buckets_overconf += 1
        else:
            verdict = "OK"
            n_buckets_with_data += 1
        bucket_stats.append({
            "range_lo": lo, "range_hi": hi, "n": n_b,
            "wr_obs": round(wr_obs, 3), "wr_lo": round(wr_lo, 3), "wr_hi": round(wr_hi, 3),
            "pred_mean": round(pred_mean, 3), "gap_pp": round(gap * 100, 1),
            "verdict": verdict,
        })
        if abs(gap) > max_gap:
            max_gap = abs(gap)

    # Status global
    avg_brier = sum(n["brier"] for n in normalized) / n_total
    if n_buckets_overconf + n_buckets_underconf >= 2 or max_gap > MAX_CALIBRATION_GAP:
        status = "ALERT"
        msg = (
            f"Calibration audit ALERT : {n_buckets_overconf} bucket(s) OVERCONFIDENT + "
            f"{n_buckets_underconf} UNDERCONFIDENT (n={n_total}, days={days}). "
            f"Max gap={max_gap*100:.1f}pp. Avg Brier={avg_brier:.4f}. "
            f"Action : reduire Kelly fraction OU recalibrer probas isotonic (post-hoc)."
        )
    elif n_buckets_overconf + n_buckets_underconf >= 1:
        status = "WARN"
        msg = (
            f"Calibration audit WARN : signal de drift (n={n_total}, days={days}). "
            f"Max gap={max_gap*100:.1f}pp. Avg Brier={avg_brier:.4f}. "
            f"Verifier prochain batch."
        )
    else:
        status = "OK"
        msg = (
            f"Calibration audit OK : scorer V2 calibre (n={n_total}, days={days}). "
            f"Max gap={max_gap*100:.1f}pp. Avg Brier={avg_brier:.4f}."
        )

    return {
        "name": "scorer_calibration", "status": status, "n_total": n_total, "days": days,
        "buckets": bucket_stats, "avg_brier": round(avg_brier, 4),
        "n_buckets_overconfident": n_buckets_overconf,
        "n_buckets_underconfident": n_buckets_underconf,
        "max_gap_pp": round(max_gap * 100, 1),
        "message": msg,
    }


if __name__ == "__main__":
    # Manual invocation : python3 -m intelligence.calibration_audit
    import sqlite3

    from shared.storage import DB_PATH

    cx = sqlite3.connect(DB_PATH)
    cx.row_factory = sqlite3.Row
    result = check_scorer_calibration(cx)
    print(f"=== {result['name']} : {result['status']} ===")
    print(f"  N total : {result['n_total']}")
    if result["status"] != "INSUFFICIENT_DATA":
        print(f"  Avg Brier : {result['avg_brier']}")
        print(f"  Max gap : {result['max_gap_pp']}pp")
        print(f"\n  {'Bucket':<12} {'n':>4} {'WR_obs':>8} {'WR_CI95':>17} {'Pred':>7} {'Gap':>8} {'Verdict':<18}")
        print(f"  {'-'*12} {'-'*4} {'-'*8} {'-'*17} {'-'*7} {'-'*8} {'-'*18}")
        for b in result["buckets"]:
            if b["n"] == 0:
                continue
            ci = f"[{b['wr_lo']*100:.0f}%-{b['wr_hi']*100:.0f}%]"
            print(
                f"  {b['range_lo']:.2f}-{b['range_hi']:.2f}  {b['n']:>4} "
                f"{b['wr_obs']*100:>7.1f}% {ci:>17} "
                f"{b['pred_mean']*100:>6.1f}% {b['gap_pp']:>+7.1f}pp {b['verdict']:<18}"
            )
    print(f"\n{result['message']}")
    cx.close()
