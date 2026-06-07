"""Thesis health metrics -- mentor heuristiques en mode METRIQUE (vs GATE).

Distinct de `intelligence/thesis_creation_gates.py` :
- gates : evaluation au moment de creation thèse (refuse / warn la creation)
- metrics : observation continue de l'etat du book / des theses existantes

Mentors mecanises ici (post-batch 07/06 nuit) :

- **M7 Druckenmiller cut-fast** : metric `thesis_invalidation_speed_days` =
  jours entre kill_criteria_trigger et thesis close. Bias chronique si > 30j.

- **M10 Taleb barbell** : metric `barbell_score` = (% book c5) + (% book c1
  ballast). Reflete la doctrine "extremes ou rien" (vs concentration moyenne
  diluant signal et ballast).

- **M14 Jhunjhunwala conviction_age** : metric `conviction_age_days` =
  jours depuis last_revisit_at (fallback opened_at). Alerte si > 120j --
  conviction qui vieillit sans re-justification = drift silencieux.

Doctrine commune avec gates (L14 anti-pattern #1) : pas de persona LLM,
heuristique deterministe lookup DB. Lecteurs : dashboard render.py + /audit
Telegram + scripts d'analyse one-off.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


# === Constantes ============================================================

# M7 Druckenmiller : seuil "rapide" pour fermeture post-trigger
DRUCKENMILLER_FAST_DAYS = 30  # > 30j entre trigger et exit = lent
DRUCKENMILLER_VERY_SLOW_DAYS = 90

# M10 Taleb barbell : barbell_score = % c5 + % c1_ballast
# Target indicatif : >= 60% (au moins moitie en extremes vs milieu mou)
TALEB_BARBELL_HEALTHY_PCT = 60.0

# M14 Jhunjhunwala : seuil staleness conviction
JHUNJHUNWALA_STALE_DAYS = 120


@dataclass(frozen=True, slots=True)
class HealthMetric:
    """Resultat metric. status = 'healthy' / 'warn' / 'stale' / 'unknown'."""
    metric_name: str
    value: float | None  # None si non calculable
    status: str
    message: str


# === M7 Druckenmiller cut-fast ============================================


def compute_m7_invalidation_speed_days() -> HealthMetric:
    """Median jours entre kill_criteria_trigger et thesis close.

    Lit theses fermees post-2026-01-01 (limite cycle). Pour chaque these
    fermee, calcule (closed_at - kill_criteria_triggered_at) en jours.
    Median = robuste vs outliers.

    Returns:
        HealthMetric. status :
        - 'healthy' si median < 30j
        - 'warn' si 30j-90j
        - 'slow' si > 90j (bias Druckenmiller : tu mets trop longtemps)
        - 'unknown' si pas assez de donnees (< 3 theses fermees avec trigger)
    """
    try:
        from shared import storage
        with storage.db() as cx:
            rows = cx.execute("""
                SELECT
                    julianday(closed_at) - julianday(kill_criteria_triggered_at) AS days_to_exit
                FROM theses
                WHERE status='closed'
                  AND closed_at IS NOT NULL
                  AND kill_criteria_triggered_at IS NOT NULL
                  AND closed_at >= '2026-01-01'
                ORDER BY days_to_exit
            """).fetchall()
    except Exception as e:
        log.warning(f"compute_m7_invalidation_speed_days failed: {e}")
        return HealthMetric(
            metric_name="M7_druckenmiller_cut_speed", value=None,
            status="unknown",
            message=f"erreur DB ({type(e).__name__}: {e})",
        )

    days_list = [float(r[0]) for r in rows if r[0] is not None and r[0] >= 0]
    if len(days_list) < 3:
        return HealthMetric(
            metric_name="M7_druckenmiller_cut_speed", value=None,
            status="unknown",
            message=f"N={len(days_list)} < 3 -- pas assez de theses fermees avec trigger",
        )
    median = days_list[len(days_list) // 2]
    if median < DRUCKENMILLER_FAST_DAYS:
        return HealthMetric(
            metric_name="M7_druckenmiller_cut_speed", value=median,
            status="healthy",
            message=f"median {median:.0f}j (N={len(days_list)}) -- discipline Druckenmiller OK",
        )
    if median < DRUCKENMILLER_VERY_SLOW_DAYS:
        return HealthMetric(
            metric_name="M7_druckenmiller_cut_speed", value=median,
            status="warn",
            message=(
                f"median {median:.0f}j (N={len(days_list)}) -- "
                "Druckenmiller : tu cuts pas assez fast post-trigger"
            ),
        )
    return HealthMetric(
        metric_name="M7_druckenmiller_cut_speed", value=median,
        status="slow",
        message=(
            f"median {median:.0f}j (N={len(days_list)}) -- BIAS Druckenmiller "
            "majeur : tu mets trop longtemps a fermer theses cassees"
        ),
    )


# === M10 Taleb barbell =====================================================


def compute_m10_barbell_score() -> HealthMetric:
    """% book en c5 (conviction max) + % book en c1 (ballast).

    Pattern Taleb : "concentrate where conviction extreme + decorrele the
    rest". Le milieu mou (c2/c3/c4 sans ballast) dilue signal et ballast.

    Returns:
        HealthMetric. value = score 0-100. status :
        - 'healthy' si score >= 60 (vraie barbell)
        - 'warn' si 40-60 (milieu encore trop gros)
        - 'mou' si < 40 (zero barbell, tout au milieu)
    """
    try:
        from shared import storage
        with storage.db() as cx:
            # Read positions ouvertes avec leur conviction (jointure theses)
            rows = cx.execute("""
                SELECT
                    p.ticker,
                    p.qty * COALESCE(p.avg_cost_eur, 0) AS pos_eur,
                    t.conviction
                FROM positions p
                LEFT JOIN theses t ON t.ticker = p.ticker AND t.status='active'
                WHERE p.status='open' AND p.qty > 0
            """).fetchall()
    except Exception as e:
        log.warning(f"compute_m10_barbell_score failed: {e}")
        return HealthMetric(
            metric_name="M10_taleb_barbell", value=None,
            status="unknown",
            message=f"erreur DB ({type(e).__name__}: {e})",
        )

    total = sum(float(r[1]) for r in rows)
    if total <= 0:
        return HealthMetric(
            metric_name="M10_taleb_barbell", value=None,
            status="unknown",
            message="book vide ou cost_basis 0",
        )

    c5_eur = sum(float(r[1]) for r in rows if r[2] == 5)
    c1_eur = sum(float(r[1]) for r in rows if r[2] == 1)
    pct_c5 = c5_eur / total * 100
    pct_c1 = c1_eur / total * 100
    barbell = pct_c5 + pct_c1

    if barbell >= TALEB_BARBELL_HEALTHY_PCT:
        return HealthMetric(
            metric_name="M10_taleb_barbell", value=barbell,
            status="healthy",
            message=(
                f"barbell {barbell:.1f}% = c5 {pct_c5:.1f}% + c1 {pct_c1:.1f}% "
                f">= {TALEB_BARBELL_HEALTHY_PCT}% (Taleb compat)"
            ),
        )
    if barbell >= 40.0:
        return HealthMetric(
            metric_name="M10_taleb_barbell", value=barbell,
            status="warn",
            message=(
                f"barbell {barbell:.1f}% = c5 {pct_c5:.1f}% + c1 {pct_c1:.1f}% "
                f"-- milieu mou (c2/c3/c4) > 60%, dilue signal+ballast"
            ),
        )
    return HealthMetric(
        metric_name="M10_taleb_barbell", value=barbell,
        status="mou",
        message=(
            f"barbell {barbell:.1f}% = c5 {pct_c5:.1f}% + c1 {pct_c1:.1f}% "
            "-- zero barbell, tout au milieu. Catch Taleb : 'concentrate or "
            "decorrelate, never both half-way'."
        ),
    )


# === M14 Jhunjhunwala conviction_age ======================================


def compute_m14_conviction_age_days(ticker: str | None = None) -> list[HealthMetric]:
    """Jours depuis last_revisit_at par these active.

    Si ticker None : retourne metric par these active.
    Si ticker donne : retourne metric unique pour ce ticker.

    Pour chaque these : age = days_since(last_revisit_at OR opened_at).
    Status :
    - 'healthy' si age < 60j
    - 'warn' si 60-120j
    - 'stale' si > 120j (Jhunjhunwala : revisit forcé)
    """
    try:
        from shared import storage
        with storage.db() as cx:
            sql = """
                SELECT
                    ticker, conviction, opened_at, last_revisit_at,
                    CAST(julianday('now') -
                         julianday(COALESCE(last_revisit_at, opened_at)) AS INTEGER) AS age_days
                FROM theses
                WHERE status='active'
            """
            params: tuple = ()
            if ticker:
                sql += " AND ticker = ?"
                params = (ticker,)
            sql += " ORDER BY age_days DESC"
            rows = cx.execute(sql, params).fetchall()
    except Exception as e:
        log.warning(f"compute_m14_conviction_age failed: {e}")
        return [HealthMetric(
            metric_name="M14_jhunjhunwala_age", value=None,
            status="unknown",
            message=f"erreur DB ({type(e).__name__}: {e})",
        )]

    if not rows:
        return [HealthMetric(
            metric_name="M14_jhunjhunwala_age", value=None,
            status="unknown",
            message="aucune these active",
        )]

    out = []
    for r in rows:
        tk, conv, _opened, _revisit, age = r
        age_d = float(age) if age is not None else 0.0
        if age_d < 60:
            status = "healthy"
            msg = f"{tk} c{conv} : revisit il y a {int(age_d)}j"
        elif age_d < JHUNJHUNWALA_STALE_DAYS:
            status = "warn"
            msg = f"{tk} c{conv} : revisit il y a {int(age_d)}j (>60j, planifie)"
        else:
            status = "stale"
            msg = (
                f"{tk} c{conv} : revisit il y a {int(age_d)}j > "
                f"{JHUNJHUNWALA_STALE_DAYS}j. Catch Jhunjhunwala : conviction "
                "qui vieillit sans re-justification = drift silencieux."
            )
        out.append(HealthMetric(
            metric_name="M14_jhunjhunwala_age", value=age_d,
            status=status, message=msg,
        ))
    return out


# === Aggregator ============================================================


def run_health_metrics() -> dict[str, HealthMetric | list[HealthMetric]]:
    """Lance tous les health metrics. Returns dict pour consommation
    dashboard / /audit Telegram."""
    return {
        "M7_druckenmiller_cut_speed": compute_m7_invalidation_speed_days(),
        "M10_taleb_barbell": compute_m10_barbell_score(),
        "M14_jhunjhunwala_age": compute_m14_conviction_age_days(),
    }
