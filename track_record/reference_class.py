"""C : base-rate hook (outside view, creve le plafond du petit n).

Spec red-team 07/06 nuit DECISION_QUALITY_ENGINE C.

A n=40 tu ne calibres jamais avec puissance sur ton seul echantillon
(plafond auto-referentiel). Solution structurelle : ancrer chaque these
dans une classe de reference issue de l'univers (Bigdata/daloopa).

Double usage :
1. Prior de shrinkage bayesien dans calibration : ton bucket conviction
   est tire vers la base rate de sa classe quand n est faible.
2. Injection decision-time : "ton fingerprint resout favorablement a X% ;
   ta conviction c4 implique Y% -- l'ecart est ta variant perception,
   est-elle justifiee ?"

Status 07/06 nuit : SCAFFOLD seulement. query_universe_excess_returns =
stub jusqu'a wire daloopa/bigdata maturity. Quand wire mature, plug
l'adapter, la doctrine L15 fail-closed garantit que base_rate None tant
que l'univers retourne pas assez de samples.

Doctrine :
- L15 : si dist.n < MIN_N_BASE_RATE -> return None, jamais base rate bidon
- L16 : fingerprint genere a l'entree, fige avec le reste A0 PIT (pour
  qu'on puisse retro-tester la base rate avec le fingerprint historique)
- L17 : config MIN_N + classes references in config/calibration.yaml
"""

from __future__ import annotations

from dataclasses import dataclass

# === Constantes (TODO : migrer config/calibration.yaml power_gates) ========

MIN_N_BASE_RATE = 40
"""Plancher samples pour qu'une base rate soit utilisable. En dessous,
L15 fail-closed : pas de chiffre fabrique."""


# === Input contracts ======================================================


@dataclass(frozen=True, slots=True)
class FingerprintInput:
    """Vue minimale entree pour fingerprint extraction.

    Sources :
    - entry : depuis thesis_integrity_log (A0 PIT)
    - tearsheet : depuis daloopa/bigdata connecteur (TBD wire)
    """
    ticker: str
    sector: str
    catalyst_kpi_family: str        # 'margin' | 'growth' | 'rerating' | ...
    setup_bucket: str                # 'post_beat' | 'quality_momo' | 'deep_value' | ...
    valuation_percentile: float      # decile EV/EBITDA vs secteur, [0, 1]


@dataclass(frozen=True, slots=True)
class UniverseDistribution:
    """Distribution univers retournee par query_universe_excess_returns.

    Sera popule depuis daloopa/bigdata. Pour l'instant stub.
    """
    n: int                              # nombre observations matching fingerprint
    hit_rate: float                     # P(excess_return > 0) empirique
    mean_excess: float                  # mean excess return
    median_excess: float                # median
    p25_excess: float                   # 25th percentile
    p75_excess: float                   # 75th percentile


# === Core API ============================================================


def fingerprint(fp_input: FingerprintInput) -> dict:
    """Extrait fingerprint canonique pour matching univers.

    Pure : pas d'I/O. Sera appele a l'entree de these + stocke dans
    thesis_integrity_log payload (L16 fige).
    """
    return {
        "sector": fp_input.sector,
        "catalyst_type": fp_input.catalyst_kpi_family,
        "setup": fp_input.setup_bucket,
        # Bucket valuation en quintiles pour matching tolerant
        "valuation_quintile": int(fp_input.valuation_percentile * 5),
    }


def base_rate(fp: dict, horizon_days: int) -> dict | None:
    """Retourne base rate univers pour le fingerprint donne, ou None si
    insuffisant.

    Args:
        fp : output de fingerprint()
        horizon_days : horizon resolution (e.g. 30, 90)

    Returns:
        dict {p_outperform, mean_excess, n, dist_summary} ou None
        si dist.n < MIN_N_BASE_RATE (L15 fail-closed).

    Doctrine L15 : si univers pas assez de samples matching, on N'INVENTE
    PAS de base rate. Le caller (calibration shrinkage / decision-time
    injection) gere None comme "pas d'outside view dispo".
    """
    try:
        dist = query_universe_excess_returns(fp, horizon_days)
    except NotImplementedError:
        # Connecteur Bigdata pas encore wire -- L15 fail-closed
        return None
    except Exception:
        # Tout autre echec : L15 fail-closed plutot que verdict bidon
        return None

    if dist is None or dist.n < MIN_N_BASE_RATE:
        return None

    return {
        "p_outperform": dist.hit_rate,
        "mean_excess": dist.mean_excess,
        "n": dist.n,
        "dist_summary": {
            "p25": dist.p25_excess,
            "median": dist.median_excess,
            "p75": dist.p75_excess,
        },
    }


def query_universe_excess_returns(
    fp: dict, horizon_days: int
) -> UniverseDistribution | None:
    """STUB : query daloopa/bigdata pour distribution excess returns matching fp.

    Quand le connecteur daloopa/bigdata est mature, remplacer ce stub par
    l'adapter reel. Pour l'instant, raise NotImplementedError pour signaler
    clairement que C n'est pas operationnel.

    Doctrine L15 : caller capture NotImplementedError -> return None
    (jamais chiffre fabrique).

    Spec attendue :
    - Query univers historique (Bigdata 30y panel data)
    - Filter par sector + catalyst_type + setup + valuation_quintile match
    - Compute distribution excess returns sur horizon_days post-setup
    - Returns UniverseDistribution avec n + percentiles
    """
    raise NotImplementedError(
        "query_universe_excess_returns: daloopa/bigdata connecteur pas encore "
        "wire (07/06 nuit). Cf track_record/reference_class.py docstring."
    )


# === Bayesian shrinkage helper (pour usage 1 : prior calibration) ========


def shrunk_p(
    observed_p: float,
    observed_n: int,
    base_rate_p: float | None,
    prior_strength: float = 15.0,
) -> float:
    """Estime probabilite avec shrinkage Bayesien vers base_rate.

    p_shrunk = (observed_p * observed_n + base_rate_p * prior_strength) /
               (observed_n + prior_strength)

    Si base_rate_p is None (L15 : pas dispo) -> on retourne observed_p brut
    SANS shrinkage (pas de pull vers chiffre fabrique).

    Args:
        observed_p : P observe sur ton echantillon (e.g. P(c5 surperforme))
        observed_n : N de ton echantillon
        base_rate_p : prior outside view depuis base_rate() ou None
        prior_strength : alpha+beta equivalent (force du pull)

    Returns:
        float in [0, 1] (clamped) : probabilite shrunken
    """
    if base_rate_p is None:
        return max(0.0, min(1.0, observed_p))
    num = observed_p * observed_n + base_rate_p * prior_strength
    den = observed_n + prior_strength
    if den == 0:
        return base_rate_p
    return max(0.0, min(1.0, num / den))
