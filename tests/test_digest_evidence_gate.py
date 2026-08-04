"""Verrouille le gate ACT-006 — le LLM propose les urgents, le gate dispose.

CONTEXTE : deux jours de suite, le digest a produit des urgents fabriqués
(évidence secondaire seule) et des « touche le kill-criterion explicite »
alors que kill_criteria_alerts affichait 713/713 dormant. La spec v2.3
(Fix 1) l'interdisait depuis fin juillet mais n'était pas implémentée.

Tests PURS : aucun DB, aucun LLM, py3.10-compatible.
"""
from __future__ import annotations

import json

from intelligence.digest_evidence_gate import (
    apply_evidence_gate,
    parse_urgents,
    primary_backing,
)


def _sig(id_, type_, tickers, title="t"):
    return {"id": id_, "signal_type": type_, "entities": json.dumps(tickers), "title": title}


NARRATIVE = (
    "## VERDICT: 2 urgent / 3 monitoring / 5 noise — urgent: MU (insider dump) | urgent: TSM (expo croisée)\n"
    "\n"
    "**MU** — Triple choc documenté : ventes insiders massives, leverage ETF Korea. "
    "MU touche le kill-criterion explicite du rerank [score 13].\n"
    "**TSM** — présent dans les trois signaux top.\n"
)


# ── 1. LE test : un urgent sans signal primaire est dégradé ─────────────────

def test_urgent_sur_evidence_secondaire_est_degrade():
    """MU n'est porté que par des narratives/opinions → urgent DOIT tomber.

    C'est le bug du 03/08 : « urgent: MU » fabriqué sur tweets + narratif
    late-cycle, zéro print, zéro filing.
    """
    signals = [
        _sig(1, "narrative", ["MU"]),
        _sig(2, "opinion", ["MU", "TSM"]),
        _sig(3, "data", ["TSM"]),  # TSM, lui, a un signal primaire
    ]
    out = apply_evidence_gate(NARRATIVE, signals, {})
    assert "VERDICT (gated): 1 urgent" in out, "MU dégradé → il ne reste que TSM"
    assert "urgent: TSM" in out
    assert "↓ MU" in out, "la dégradation doit être PUBLIQUE (trailer)"
    assert "évidence secondaire" in out


def test_urgent_avec_signal_primaire_tient():
    signals = [_sig(1, "catalyst", ["MU"]), _sig(2, "data", ["TSM"])]
    out = apply_evidence_gate(NARRATIVE, signals, {})
    assert "VERDICT (gated): 2 urgent" in out
    assert "urgent: MU" in out and "urgent: TSM" in out


def test_zero_urgent_est_un_resultat_normal():
    """Tous les urgents tombent → 0 urgent, sans erreur, comptes recalés."""
    signals = [_sig(1, "narrative", ["MU"]), _sig(2, "opinion", ["TSM"])]
    out = apply_evidence_gate(NARRATIVE, signals, {})
    assert "VERDICT (gated): 0 urgent / 5 monitoring" in out  # 3 + 2 dégradés
    assert out.count("↓") == 2


# ── 2. Claims kill-criterion confrontées au moteur (L1) ─────────────────────

def test_claim_kill_criterion_desarmee_si_moteur_dormant():
    """« touche le kill-criterion » + moteur dormant → correctif inline visible.

    Le gate ne supprime pas la phrase (pas de réécriture d'analyse) : il la
    désarme, à découvert.
    """
    signals = [_sig(1, "catalyst", ["MU"])]
    out = apply_evidence_gate(NARRATIVE, signals, {"MU": "dormant", "TSM": "dormant"})
    assert "GATE ACT-006 : proximité thématique, AUCUN kill-criterion franchi" in out
    line = next(ln for ln in out.split("\n") if "kill-criterion explicite" in ln)
    assert "GATE ACT-006" in line, "le correctif doit être SUR la ligne fautive"


def test_claim_kill_criterion_conservee_si_reellement_triggered():
    signals = [_sig(1, "catalyst", ["MU"])]
    out = apply_evidence_gate(NARRATIVE, signals, {"MU": "triggered"})
    assert "AUCUN kill-criterion franchi" not in out, (
        "un franchissement RÉEL (kill_criteria_alerts=triggered) ne doit pas être désarmé"
    )


def test_absence_de_statut_vaut_dormant():
    """Fail-closed : pas de donnée moteur → aucune claim autorisée."""
    signals = [_sig(1, "catalyst", ["MU"])]
    out = apply_evidence_gate(NARRATIVE, signals, {})
    assert "AUCUN kill-criterion franchi" in out


# ── 3. Fail-loud : le gate ne se tait jamais ────────────────────────────────

def test_gate_casse_devient_bandeau_incident_pas_silence():
    """Un contrôle en panne DOIT s'annoncer — jamais se lire comme un contrôle passé."""
    # entities imparsable est TOLÉRÉ (set vide) — ne doit PAS déclencher l'incident :
    tol = apply_evidence_gate(NARRATIVE, [{"entities": object()}], {})
    assert "GATE ACT-006 EN ÉCHEC" not in tol
    # forcer une vraie casse (signals=None → TypeError interne) :
    out2 = apply_evidence_gate(NARRATIVE, None, {})  # type: ignore[arg-type]
    assert "GATE ACT-006 EN ÉCHEC" in out2
    assert "MU touche le kill-criterion" in out2, "le narratif d'origine reste lisible"


def test_narrative_sans_verdict_ne_casse_pas():
    out = apply_evidence_gate("Pas de ligne verdict ici.", [_sig(1, "data", ["MU"])], {})
    assert "Pas de ligne verdict ici." in out


# ── 4. Primitives ───────────────────────────────────────────────────────────

def test_parse_urgents_lit_le_bloc_verdict_pas_le_corps():
    """Format réel (dry-run 03/08) : les urgents nommés sont sur la ligne
    SUIVANT le VERDICT. Le bloc = ligne + continuation jusqu'à la ligne vide ;
    le corps (après la ligne vide) ne compte JAMAIS."""
    txt = ("## VERDICT: 2 urgent / 1 monitoring / 3 noise\n"
           "**urgent: AVGO** (x) | **urgent: MU** (y)\n"
           "\n"
           "corps : urgent: FAKE ne compte pas")
    assert parse_urgents(txt) == ["AVGO", "MU"]


def test_primary_backing_filtre_type_et_ticker():
    sigs = [_sig(1, "data", ["MU"]), _sig(2, "narrative", ["MU"]), _sig(3, "data", ["TSM"])]
    assert primary_backing("MU", sigs) == [1]
    assert primary_backing("XXX", sigs) == []


# ── 5. Formats réels attrapés en production (04/08) ─────────────────────────

def test_format_liste_du_04_08_tous_les_urgents_sont_traites():
    """« urgent: A (...) | B (...) | C (...) » — B et C n'ont pas le mot urgent.

    Bug attrapé par dry-run : seuls les tickers précédés de « urgent: » étaient
    parsés ; les suivants DISPARAISSAIENT du verdict réécrit — ni gardés ni
    dégradés. Un urgent ne peut pas s'évaporer en silence.
    """
    txt = ("**VERDICT: 3 urgent / 4 monitoring / 11 noise**\n"
           "urgent: AVGO (insider -$283M) | MU (CXMT) | AMZN (AWS +37%)\n"
           "\ncorps.")
    assert parse_urgents(txt) == ["AVGO", "MU", "AMZN"]
    out = apply_evidence_gate(txt, [_sig(1, "narrative", ["AVGO"])], {})
    assert "↓ AVGO" in out and "↓ MU" in out and "↓ AMZN" in out, (
        "les TROIS doivent être dégradés à découvert, aucun ne s'évapore"
    )
    assert "VERDICT (gated): 0 urgent / 7 monitoring" in out


def test_cecite_entities_est_declaree_pas_silencieuse():
    """0 signal taggé dans la fenêtre → le gate DOIT dire qu'il est aveugle.

    Constat 04/08 : enrichissement entities en retard (44 % juin → 20 % juillet
    → 0 % sur la fenêtre fraîche). Sans cette déclaration, « 0 urgent » se
    lirait comme « rien d'urgent » alors que c'est « rien de vérifiable » (L31).
    """
    txt = ("VERDICT: 1 urgent / 2 monitoring / 3 noise\n"
           "urgent: MU (x)\n\ncorps.")
    out = apply_evidence_gate(txt, [_sig(1, "catalyst", [])], {})
    assert "CÉCITÉ DÉCLARÉE" in out
    assert "invérifiable" in out
