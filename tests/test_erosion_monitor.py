"""Verrouille le capteur d'érosion — la perte qui n'a pas d'événement.

CONTEXTE : du 22/06 au 27/07/2026 le book a rendu 25,6 points sans qu'aucune
journée ne constitue un événement. Tous les détecteurs du système sont des
détecteurs d'ÉVÉNEMENT ; aucun ne pouvait voir ça.

Ces tests verrouillent surtout la LEÇON DE MÉTHODE du 03/08 : la première
version excluait « les K pires journées », ce qui ampute mécaniquement 40 à
70 % de n'importe quelle baisse et fait conclure « choc » partout. La donnée
a réfuté le détecteur ; la statistique a été remplacée (moyenne tronquée
symétrique), PAS le seuil. `test_choc_franc_reste_un_choc` et
`test_erosion_lente_reste_une_erosion` échouent si quelqu'un revient à une
exclusion asymétrique.
"""
from __future__ import annotations

import pytest

from intelligence.erosion_monitor import (
    EROSION_MIN_PP,
    EROSION_THRESHOLD_STATUS,
    classify_erosion,
)


def _serie(deltas: list[float], start: float = 30.0) -> list[tuple[str, float]]:
    """Construit une série de rendements à partir de variations quotidiennes."""
    out, v = [("2026-01-01", start)], start
    for i, d in enumerate(deltas, start=2):
        v += d
        out.append((f"2026-01-{i:02d}", v))
    return out


# ── Les deux profils que le détecteur DOIT séparer ──────────────────────────

def test_erosion_lente_reste_une_erosion():
    """20 séances à −0,7 pt : rien n'arrive jamais, et 14 points disparaissent.

    C'est le profil exact de juin-juillet. Une statistique qui retire « les
    pires journées » conclurait « choc » ici — c'est le défaut corrigé.
    """
    r = classify_erosion(_serie([-0.7] * 20))
    assert r.verdict == "erosion", (
        "une baisse uniforme sans aucun outlier est l'érosion par excellence ; "
        "si le détecteur dit 'choc', la statistique ampute le corps de la "
        "distribution au lieu des queues"
    )
    assert r.decline_ex_worst_pp == pytest.approx(r.decline_pp, abs=0.5), (
        "sans queues, baisse tronquée et baisse brute doivent coïncider"
    )
    assert r.n_days_down == 20


def test_choc_franc_reste_un_choc():
    """18 séances plates + 2 séances à −8 : toute la perte vit dans les queues."""
    r = classify_erosion(_serie([0.1] * 9 + [-8.0, -8.0] + [0.1] * 9))
    assert r.verdict == "choc", (
        "une perte concentrée sur 2 séances est de la volatilité, pas un "
        "re-rating — les confondre fait vendre le bas"
    )
    assert abs(r.decline_ex_worst_pp) < abs(r.decline_pp) / 2, (
        "la troncature doit effacer l'essentiel d'un choc"
    )


def test_hausse_est_saine():
    r = classify_erosion(_serie([+0.8] * 15))
    assert r.verdict == "sain"
    assert r.decline_pp > 0


def test_baisse_minuscule_ne_declenche_rien():
    """Sous le plancher d'amplitude : pas d'érosion déclarée (anti-bruit)."""
    r = classify_erosion(_serie([-0.05] * 20))
    assert r.verdict == "sain"
    assert abs(r.decline_pp) < EROSION_MIN_PP


# ── Fail-closed : jamais de verdict fabriqué ────────────────────────────────

def test_serie_trop_courte_est_insuffisante_pas_saine():
    """L15 : une série trop courte rend « insuffisant », JAMAIS « sain ».

    « Sain » se lirait comme « j'ai regardé et tout va bien ». Le détecteur
    n'a pas regardé — il doit le dire.
    """
    r = classify_erosion(_serie([-1.0] * 3))
    assert r.verdict == "insuffisant"
    assert not r.is_conclusive
    assert r.verdict != "sain"


def test_serie_vide_ne_leve_pas():
    r = classify_erosion([])
    assert r.verdict == "insuffisant"
    assert r.decline_pp is None


# ── L16 : un seuil non calibré ne déclenche rien ────────────────────────────

def test_seuil_non_calibre_informe_mais_ne_notifie_pas():
    """N=1 épisode observé : tuner le seuil dessus serait du sur-ajustement.

    Tant que le statut n'est pas VALIDE, le verdict INFORME sans notifier.
    Ce test échoue si quelqu'un arme l'alerte sans calibrer.
    """
    r = classify_erosion(_serie([-0.7] * 20))
    assert r.verdict == "erosion"
    if EROSION_THRESHOLD_STATUS != "VALIDE":
        assert r.would_alert is False, (
            "un seuil PROPOSE ne doit jamais déclencher de notification (L16)"
        )
        assert any("non calibre" in n or "non calibré" in n for n in r.notes), (
            "l'absence de calibration doit être DÉCLARÉE au lecteur"
        )


# ── Le verdict porte sa preuve ──────────────────────────────────────────────

def test_le_verdict_expose_ses_primitives():
    """A8 : jamais un verdict nu — les nombres qui le fondent sont exposés."""
    r = classify_erosion(_serie([-0.7] * 20))
    assert r.decline_pp is not None
    assert r.decline_ex_worst_pp is not None
    assert r.n_days_down > 0
    assert r.notes, "un verdict sans explication n'est pas auditable"
