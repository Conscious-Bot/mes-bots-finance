"""Verrouille le rewire HWM canonique (04/08/2026) — tests de SOURCE.

LE FORK FERMÉ : deux HWM coexistaient — 60 258 € (rolling legacy des snapshots,
figé sur un pic intraday) et 59 224 € (reconstruction ledger+prix réconciliée,
arbitrée au decision log couche_vie_hwm_2026-08-03). Le digest affichait l'un,
le decision log l'autre : deux vérités pour le même objet (L1 violé).

Design retenu (note session terminal 04/08, option a) : ancre arbitrée dans
policy.yaml + rolling max auto-entretenu = max(ancre, snapshots POSTÉRIEURS).
Aucun nouvel état — la table portfolio_snapshots existante EST le journal.

Tests de source (pas d'exécution : digue_monitor importe storage, py3.14-only
en sandbox) — même pattern que test_dashboard_doctrine.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
DIGUE = ROOT / "intelligence" / "digue_monitor.py"
POLICY = ROOT / "config" / "policy.yaml"


@pytest.fixture(scope="module")
def src() -> str:
    if not DIGUE.is_file():
        pytest.skip("digue_monitor absent")
    return DIGUE.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def pol() -> dict:
    return yaml.safe_load(POLICY.read_text(encoding="utf-8"))


# ── 1. L'ancre : déclarée en policy, jamais en littéral Python ──────────────

def test_ancre_declaree_en_policy_avec_methode(pol: dict):
    a = pol["drawdown_ladder"]["HWM_ANCHOR"]
    assert a["value_eur"] == 59224
    assert a["date"] == "2026-06-22"
    assert a["status"] == "VALIDE"
    assert "decision log" in a["note"], "l'ancre doit citer son arbitrage (traçabilité)"


def test_pas_de_littoral_hwm_en_python(src: str):
    """A3 : le code lit policy.yaml, jamais un chiffre en dur."""
    assert "59224" not in src and "59 224" not in src, (
        "l'ancre HWM ne doit exister QU'EN policy.yaml — un littéral Python "
        "recréerait la double vérité que ce rewire ferme"
    )


# ── 2. Source unique et sens du calcul ──────────────────────────────────────

def test_canonical_hwm_existe_et_est_la_source_unique(src: str):
    assert "def canonical_hwm(" in src, "la source unique du HWM a disparu"
    assert "def _hwm_anchor(" in src
    # le lecteur du drawdown passe par elle
    body = re.search(r"def _latest_drawdown.*?(?=\ndef |\Z)", src, re.S)
    assert body and "canonical_hwm()" in body.group(0), (
        "_latest_drawdown doit consommer canonical_hwm() — sinon le digest et "
        "le dashboard repartent sur le rolling legacy"
    )


def test_le_rolling_est_borne_a_l_ancre(src: str):
    """max(ancre, snapshots POSTÉRIEURS à la date d'ancre) — les snapshots
    antérieurs portent la méthode legacy (60 258 intraday) et ne doivent
    JAMAIS re-contaminer le max."""
    assert re.search(r"snapshot_date\s*>\s*\?", src), (
        "la requête doit être STRICTEMENT postérieure à la date d'ancre"
    )
    assert "post_max > anchor_val" in src or "max(" in src


def test_gap_unpriced_applique_au_rolling(src: str):
    """Un snapshot partiel ne peut pas devenir le HWM (agrégat partiel ≠ total)."""
    m = re.search(r"MAX\(total_value_eur\).*?n_priced\)\s*<=\s*\?", src, re.S)
    assert m, "le max post-ancre doit filtrer les rows partielles (DIGUE_MAX_UNPRICED_GAP)"


# ── 3. Fallback : legacy possible, mais JAMAIS silencieux ───────────────────

def test_fallback_legacy_est_bruyant_et_etiquete(src: str):
    """Ancre illisible → on retombe sur le rolling row, mais log.error +
    hwm_source explicite. Pas de fallback silencieux (design note, L15)."""
    assert "legacy_snapshot_rolling" in src, "le fallback doit être ÉTIQUETÉ dans le state"
    assert re.search(r'log\.error\([^)]*fork L1', src), (
        "le fallback doit crier que le fork est ROUVERT — un fallback muet "
        "reproduirait le défaut que le rewire ferme"
    )
    assert '"hwm_source"' in src, "hwm_source doit être exposé aux afficheurs (A8 : la base est nommée)"


# ── 4. Non-régression comportementale (données du 04/08) ────────────────────

def test_verdict_inchange_sur_donnees_du_rewire(pol: dict):
    """Au moment du rewire : DD legacy −18,4 %, DD canonique −16,98 % — MÊME
    verdict gel_15. Le rewire corrige la mesure sans transition parasite.
    (Gel si jamais quelqu'un 'ajuste' l'ancre : à 49 169 € de book, une ancre
    qui ferait sortir du gel_15 serait > 57 846 € — la nôtre y est, 59 224.)"""
    a = float(pol["drawdown_ladder"]["HWM_ANCHOR"]["value_eur"])
    book_at_rewire = 49168.99
    dd = (book_at_rewire / a - 1) * 100
    assert -25 < dd <= -15, f"DD à l'ancre = {dd:.2f} % — doit rester en gel_15"
