"""Position Card V3 — tests DOCTRINE (07/08/2026). Remplace les tests legacy.

Chaque test verrouille un principe (P1-P9), pas un pixel. Fakes duck-typés :
la carte est une fonction pure de (inputs, steer) — aucun import storage,
exécutable py3.10 sandbox comme py3.14 Mac.
"""
from __future__ import annotations

from types import SimpleNamespace as NS

from dashboard.position_card import (
    cost_of_inaction,
    critical_trigger,
    render_position_card,
    single_lesson,
)


def _bl(**kw):
    d = dict(qty=3.0, avg_cost_eur=1150.0, current_eur=4497.0,
             last_price_native=1499.0, last_price_currency="EUR",
             price_asof="2026-08-07T18:00:00+00:00")
    d.update(kw)
    return NS(**d)


def _inputs(**kw):
    d = dict(
        ticker="ASML.AS",
        thesis={"conviction": 5, "horizon": "24m", "opened_at": "2026-03-15",
                "variant_perception": "monopole EUV — capex hyperscaler paie le péage",
                "invalidation_triggers": '["Guidance FY révisée (baseline 15/07 : FY26 €43-45B)", "Export restrictions matériaux", "Hyperscaler capex décélération"]',
                "stop_value": 1270.0, "stop_currency": "EUR"},
        book_line=_bl(),
        weight_pct=8.8, conviction_current=5,
        over_cap_status=None, kill_status="dormant", kill_at=None,
        bias_events_open=[], counter_argument_brief=None, counter_argument_at=None,
        erosion_driver_status=[], last_cf=None, similar_situations=[],
        next_event=None, binding_target_pct=None,
    )
    d.update(kw)
    return NS(**d)


def _steer(verdict="HOLD", delta=None, bandeau=""):
    return NS(verdict=NS(value=verdict), target_qty_delta_pct=delta, bandeau=bandeau)


# ── P1 : l'ordre des blocs = l'ordre des questions ──────────────────────────

def test_ordre_verbal_des_blocs():
    h = render_position_card(_inputs(), _steer())
    agir = h.index("DOIS-JE AGIR ?")
    pourquoi = h.index("POURQUOI CETTE POSITION EXISTE")
    avis = h.index("CHANGER D’AVIS ?")
    assert agir < pourquoi < avis, "le verdict d'abord, jamais en bas (péché ASML)"


# ── P2 : datums interdits ───────────────────────────────────────────────────

def test_datums_sans_pouvoir_de_decision_sont_morts():
    h = render_position_card(_inputs(), _steer())
    for banned in ("beta", "P/E", "ISIN", "market cap", "TYPE &"):
        assert banned not in h, f"« {banned} » ne change aucune décision (P2)"


# ── P4 : fail-honest ────────────────────────────────────────────────────────

def test_variant_vide_est_crie_pas_masque():
    i = _inputs(thesis={**_inputs().thesis, "variant_perception": ""})
    assert "POURQUOI JE POSSÈDE CETTE LIGNE : INDÉFINI" in render_position_card(i, _steer())


def test_stop_absent_est_crie():
    i = _inputs(thesis={**_inputs().thesis, "stop_value": None})
    assert "stop non posé" in render_position_card(i, _steer())


def test_distance_non_mesuree_est_declaree_jamais_inventee():
    _txt, note, _ = critical_trigger(["Samsung slot majoritaire HBM4"], [])
    assert note == "distance : à mesurer", "L15 : pas de distance fabriquée"


# ── P5 : coût de l'inaction, règle mécanique avec raison ────────────────────

def test_cout_inaction_over_cap_est_eleve_avec_raison():
    lvl, why = cost_of_inaction(_inputs(over_cap_status="over"), None, "2026-08-07")
    assert lvl == "ÉLEVÉ" and "over_cap" in why


def test_cout_inaction_fait_proche_eleve_fait_loin_moyen():
    lvl, _ = cost_of_inaction(_inputs(), ("print", "2026-08-12"), "2026-08-07")
    assert lvl == "ÉLEVÉ"
    lvl2, _ = cost_of_inaction(_inputs(), ("print", "2026-09-01"), "2026-08-07")
    assert lvl2 == "MOYEN"


def test_cout_inaction_defaut_faible_avec_raison():
    lvl, why = cost_of_inaction(_inputs(), None, "2026-08-07")
    assert lvl == "FAIBLE" and why, "le niveau seul, sans raison, est interdit"


# ── P6 : un trigger, une leçon ──────────────────────────────────────────────

def test_un_seul_trigger_les_autres_comptes_masques():
    h = render_position_card(_inputs(), _steer())
    assert "+2 masqués" in h
    # « Export restrictions » a le droit d'apparaître comme ANTI-THÈSE (⚖,
    # fallback triggers[1] hérité V2) — mais le 3e trigger, lui, est masqué :
    assert "Hyperscaler capex décélération" not in h, "un seul trigger visible (P6)"


def test_trigger_mesurable_prefere_au_T1_narratif():
    txt, _, _ = critical_trigger(
        ["narratif sans chiffre", "marges HBM (baseline 76%)"], [])
    assert "76%" in txt, "baseline mesurable > ordre d'écriture"


def test_etat_moteur_non_dormant_prime_sur_tout():
    txt, note, _ = critical_trigger(
        ["a (baseline 5%)", "b"], [{"driver": "marges érodées", "status": "erode"}])
    assert txt == "marges érodées" and "erode" in note


def test_lecon_unique_cf_du_prioritaire():
    i = _inputs(
        last_cf={"state": "pending", "decision_type": "full_exit",
                 "decided_at": "2026-07-20", "branch": "hold", "due": "2026-08-17"},
        bias_events_open=[{"bias": "lock_in", "created_at": "2026-08-01"}],
    )
    lesson = single_lesson(i, today="2026-08-07")
    assert "verdict dans 10 j (17/08)" in lesson
    assert "lock_in" not in lesson, "UNE leçon : le CF dû prime (P6)"


def test_lecon_silence_honnete():
    assert "historique jeune" in single_lesson(_inputs())


# ── P5+P8 : verdict « Rien » daté, question de propriété à 3 états ──────────

def test_rien_est_date_du_prochain_fait():
    i = _inputs(last_cf={"state": "pending", "decision_type": "trim",
                         "decided_at": "2026-07-20", "branch": "hold", "due": "2026-08-17"})
    h = render_position_card(i, _steer())
    assert "Rien — prochain fait daté" in h and "2026-08-17" in h


def test_question_de_propriete_trois_etats():
    h = render_position_card(_inputs(), _steer())
    assert "seulement à un meilleur prix" in h, "l'état qui évite les faux oui (P8)"


# ── verdict TRIM en euros (l'instruction, pas la justification) ─────────────

def test_trim_exprime_en_euros_d_abord():
    i = _inputs(over_cap_status="over", binding_target_pct=8.0)
    h = render_position_card(i, _steer("TRIM_TO_X", delta=-9.6))
    assert "TRIM ~432 €" in h and "retour cap 8.0 %" in h
    assert "INTERDIT : renforcer" in h


# ── L15 : bandeau fail-closed survit à la V3 ────────────────────────────────

def test_bandeau_fail_closed_prefixe_la_carte():
    h = render_position_card(_inputs(), _steer(bandeau="steer dégradé : prix stale"))
    assert "steer dégradé" in h
    assert h.index("v3-bandeau") < h.index("DOIS-JE AGIR ?")


# ── couleur = ressource rare ────────────────────────────────────────────────

def test_monochrome_hors_verdict():
    h = render_position_card(_inputs(), _steer())
    for emoji in ("\U0001F7E0", "\U0001F7E2", "\U0001F534", "⚪"):
        assert emoji not in h, "zéro emoji couleur : la couleur vit dans le CSS du verdict seul"


# ── kill triggered : la thèse commande, le steer se tait ────────────────────

def test_kill_triggered_prend_le_verdict():
    i = _inputs(kill_status="triggered", kill_at="2026-08-05")
    h = render_position_card(i, _steer("TRIM_TO_X", delta=-5.0))
    assert "kill-criterion DÉCLENCHÉ" in h
    assert "INTERDIT : renforcer, moyenner" in h
