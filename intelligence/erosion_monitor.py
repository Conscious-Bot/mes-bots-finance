"""Capteur d'ÉROSION — détecte la perte qui n'a pas d'événement.

POURQUOI (diagnostic 03/08/2026)
--------------------------------
Du 22/06 au 27/07, le book a rendu 25,6 points de rendement en 35 jours.
Aucune journée n'a perdu plus de 3,4 points sur les 33 dernières. Il ne s'est
jamais rien passé — 35 fois de suite. Aucun trigger ne pouvait se déclencher :
tous les mécanismes du système sont des détecteurs d'ÉVÉNEMENT.

Le seul dispositif qui a mordu est l'échelle de drawdown, à `R1_FREEZE_DD`
(−15 %) le 17/07 — alors que 23 des 32,8 points étaient déjà partis. Et R1
GÈLE les achats : il ne réduit rien.

Une échelle de drawdown mesure un NIVEAU. L'érosion est une PENTE. Ce module
mesure la pente — et surtout la part de la baisse portée par les journées
ORDINAIRES, celle qu'aucun événement n'explique.

LA DISTINCTION QUI PILOTE L'ACTION
-----------------------------------
Deux baisses de même amplitude n'appellent pas la même réponse :

  * CHOC     — la baisse vit dans les QUEUES : la tronquer l'efface.
               Se retrace le plus souvent. C'est de la volatilité.
  * ÉROSION  — la baisse vit dans le CORPS de la distribution : elle survit
               à la troncature. Ne se retrace pas. C'est un re-rating.

RÉSULTAT INATTENDU (03/08) : appliqué au book, ce détecteur classe ÉROSION la
fenêtre contenant le « crash » du 27-29/07 — 18,2 des 18,7 points survivent à
la troncature, 12 séances négatives sur 20. Les deux plus fortes baisses
quotidiennes de tout l'épisode sont les 23 et 26 JUIN, pas la semaine du
crash. Statistiquement, il n'y a jamais eu deux objets : un seul processus
continu, dont la pente s'est accentuée trois jours.

Confondre les deux coûte cher : on encaisse un choc comme s'il était un
re-rating (on vend le bas), et on subit un re-rating comme s'il était un choc
(on attend un rebond qui ne vient pas).

CE MODULE N'ÉCRIT RIEN
----------------------
La série est RECALCULÉE depuis `transactions` + `price_history` via le socle
`book_performance` (A8 : aucune valeur dérivée n'est source de vérité). Le
ledger et l'historique de prix SONT le journal — il ne manquait que la lecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any

# ── Constantes déclarées (A3) ───────────────────────────────────────────────

#: Fenêtre d'observation. 20 jours : assez long pour qu'une pente lente
#: devienne lisible, assez court pour ne pas noyer un régime dans le précédent.
#: L'épisode de référence (22/06→27/07) dure 35 jours — il est donc détectable
#: dans deux fenêtres consécutives, pas seulement à son terme.
WINDOW_DAYS: int = 20

#: Fraction tronquée à CHAQUE extrémité de la distribution des variations
#: quotidiennes. 10 % : statistique robuste standard. On ne retire pas « les
#: pires journées » (ça ampute mécaniquement 40 à 70 % de n'importe quelle
#: baisse et fait conclure « choc » partout — première version, réfutée par
#: les données le 03/08) ; on tronque SYMÉTRIQUEMENT, ce qui neutralise les
#: queues sans biaiser le signe.
TRIM_FRACTION: float = 0.10

#: Un CHOC vit dans les queues : en les tronquant, la baisse doit largement
#: se dissiper. Si la baisse tronquée conserve plus de cette part de la baisse
#: brute, la perte est portée par les journées ORDINAIRES — c'est une érosion.
#: Seuil structurel (une majorité), pas calibré sur données : hors L16.
SHOCK_MAX_TRIMMED_SHARE: float = 0.50

#: Amplitude minimale, en POINTS de rendement tronqués, pour qu'une pente
#: mérite un signal.
#: STATUS: PROPOSE — NON CALIBRÉ. N=1 épisode observé ; L16 interdit de tuner
#: un seuil sur l'unique épisode qui a motivé le détecteur. Ancré faute de
#: mieux sur un tiers de `R1_FREEZE_DD` (−15 %) de config/policy.yaml.
#: Tant que le statut est PROPOSE, ce module MESURE et RAPPORTE ; l'armement
#: d'une notification exige une calibration sur N>=3 épisodes datés.
EROSION_MIN_PP: float = 5.0
EROSION_THRESHOLD_STATUS: str = "PROPOSE"


@dataclass(frozen=True)
class ErosionReading:
    """Lecture de pente sur la fenêtre. Tous les deltas en POINTS de rendement.

    `verdict` :
      - "insuffisant" : série incomplète — aucune conclusion (L15).
      - "sain"        : pas de baisse significative.
      - "choc"        : baisse portée par les queues → volatilité.
      - "erosion"     : baisse portée par les journées ordinaires → re-rating.
    """

    verdict: str
    asof: str
    window_days: int

    return_start_pct: float | None = None
    return_end_pct: float | None = None
    decline_pp: float | None = None            # baisse totale sur la fenêtre
    decline_ex_worst_pp: float | None = None   # baisse des journées ORDINAIRES (tronquée)
    shock_concentration_pct: float | None = None  # part de la baisse effacée par la troncature
    worst_day: tuple[str, float] | None = None
    n_days_observed: int = 0
    n_days_expected: int = 0
    n_days_down: int = 0

    threshold_status: str = EROSION_THRESHOLD_STATUS
    would_alert: bool = False   # True seulement si le seuil était CALIBRÉ
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_conclusive(self) -> bool:
        return self.verdict in ("sain", "choc", "erosion")


def classify_erosion(series: list[tuple[str, float]]) -> ErosionReading:
    """Classe une série (date, rendement_pct) — fonction PURE, testable seule.

    Source de vérité UNIQUE de la classification (L1).

    Méthode : moyenne TRONQUÉE des variations quotidiennes × nombre de jours.
    Elle estime la baisse imputable aux journées ORDINAIRES. Un choc vit dans
    les queues : la troncature l'efface. Une érosion vit dans le corps de la
    distribution : elle survit.

    Args:
        series : [(date ISO, rendement total en %)] triée croissant.

    Returns:
        ErosionReading. Série trop courte -> verdict "insuffisant", jamais un
        verdict fabrique (L15 fail-closed).
    """
    import statistics

    asof = series[-1][0] if series else ""
    if len(series) < 6:
        return ErosionReading(
            verdict="insuffisant", asof=asof, window_days=WINDOW_DAYS,
            n_days_observed=len(series),
            notes=(
                f"{len(series)} point(s) — il en faut au moins 6 pour tronquer "
                "les queues et conserver une pente lisible.",
            ),
        )

    deltas = [series[i][1] - series[i - 1][1] for i in range(1, len(series))]
    decline = series[-1][1] - series[0][1]

    k = int(len(deltas) * TRIM_FRACTION)
    core = sorted(deltas)[k:len(deltas) - k] if k else sorted(deltas)
    decline_trimmed = statistics.fmean(core) * len(deltas)
    n_down = sum(1 for d in deltas if d < 0)
    share = (decline_trimmed / decline) if decline < 0 else 0.0

    notes: list[str] = []
    if decline >= 0:
        verdict = "sain"
        notes.append(f"aucune baisse sur la fenêtre ({decline:+.1f} pt).")
    elif -decline_trimmed < EROSION_MIN_PP:
        verdict = "choc" if share < SHOCK_MAX_TRIMMED_SHARE else "sain"
        if verdict == "choc":
            notes.append(
                f"baisse de {-decline:.1f} pt dont seulement {-decline_trimmed:.1f} pt "
                "survivent a la troncature : la perte vit dans les QUEUES. Profil de "
                "CHOC (volatilite), historiquement retrace — ne pas traiter comme un "
                "re-rating, c'est ainsi qu'on vend le bas."
            )
        else:
            notes.append(
                f"baisse de {-decline:.1f} pt, dont {-decline_trimmed:.1f} pt sur les "
                f"journees ordinaires : sous le plancher de {EROSION_MIN_PP} pt."
            )
    elif share < SHOCK_MAX_TRIMMED_SHARE:
        verdict = "choc"
        notes.append(
            f"{(1 - share) * 100:.0f} % de la baisse disparait a la troncature : CHOC. "
            "Un choc se retrace le plus souvent."
        )
    else:
        verdict = "erosion"
        notes.append(
            f"EROSION : {-decline:.1f} pt sur la fenetre, dont {-decline_trimmed:.1f} pt "
            f"portes par les journees ORDINAIRES ({share * 100:.0f} % de la baisse "
            f"survit a la troncature ; {n_down}/{len(deltas)} seances negatives). "
            "Aucune journee n'est aberrante : il n'y a pas d'evenement a attendre, "
            "et rien a retracer. C'est un re-rating."
        )

    if verdict == "erosion" and EROSION_THRESHOLD_STATUS != "VALIDE":
        notes.append(
            f"Seuil d'amplitude ({EROSION_MIN_PP} pt) en statut "
            f"{EROSION_THRESHOLD_STATUS} — non calibre (N=1 episode, L16). "
            "Ce verdict INFORME, il ne declenche aucune notification."
        )

    return ErosionReading(
        verdict=verdict, asof=asof, window_days=WINDOW_DAYS,
        return_start_pct=series[0][1], return_end_pct=series[-1][1],
        decline_pp=decline, decline_ex_worst_pp=decline_trimmed,
        shock_concentration_pct=(1 - share) * 100 if decline < 0 else 0.0,
        worst_day=(series[deltas.index(min(deltas)) + 1][0], min(deltas)),
        n_days_observed=len(series), n_days_down=n_down,
        threshold_status=EROSION_THRESHOLD_STATUS,
        would_alert=(verdict == "erosion" and EROSION_THRESHOLD_STATUS == "VALIDE"),
        notes=tuple(notes),
    )


def build_return_series(
    cx: Any, end: str | None = None, window_days: int = WINDOW_DAYS
) -> list[tuple[str, float]]:
    """Série quotidienne du rendement total, RECALCULÉE depuis le ledger.

    Les jours dont la performance n'est pas réconciliée ou dont la couverture
    prix est incomplète sont OMIS — jamais interpolés. Une série trouée est
    déclarée trouée ; elle ne devient pas une pente inventée (L15, L31).
    """
    from shared.book_performance import compute_book_performance

    end_d = date.fromisoformat(end[:10]) if end else date.today()
    out: list[tuple[str, float]] = []
    for i in range(window_days, -1, -1):
        d = (end_d - timedelta(days=i)).isoformat()
        p = compute_book_performance(cx, asof=f"{d}T23:59:59")
        if p.status == "ok" and p.total_return_pct is not None:
            out.append((d, p.total_return_pct))
    return out


def read_erosion(cx: Any, end: str | None = None) -> ErosionReading:
    """Point d'entrée : lit le book et rend le verdict de pente."""
    series = build_return_series(cx, end)
    r = classify_erosion(series)
    expected = WINDOW_DAYS + 1
    if r.n_days_observed < expected:
        r = replace(
            r,
            n_days_expected=expected,
            notes=(
                *r.notes,
                f"{expected - r.n_days_observed} jour(s) non valorisables sur "
                f"{expected} (prix manquants ou non réconciliés) : la pente porte "
                "sur les jours réellement mesurés, aucun n'a été interpolé.",
            ),
        )
    return r
