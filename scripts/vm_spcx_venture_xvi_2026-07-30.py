"""§XVI SPCX — re-typage venture + decision override. À LANCER SUR LA VM, APRÈS le replay.

Mécanise la seule décision du 30/07 restée littérature (§XVI) : SPCX cesse d'être
une ligne 'priced' jugée au cours et devient une VENTURE jugée aux milestones —
conviction c1 (= cap 2% via calibration.yaml:line_cap_by_conviction), position_type
'tactical' + tag 'venture', stop 98 ANNULÉ, cible NULL.

CE QUE CE SCRIPT NE FAIT PAS : le trim (26.081 -> ~10) est un ordre LIMITE non
rempli. Le partial_exit + son CF (fomo_greed, contrefactuels, résolution +30/60/90)
ne se journalisent qu'AU FILL — insert_decision_with_cf ne crée un CF que pour un
trade-type, et fabriquer un fill serait mentir. Le re-typage ci-dessous est un
'override' (judgment), sans CF ; la ligne reste à 26.081 jusqu'au fill.

Précondition (force l'ordre) : le replay tribunal doit avoir tourné — SPCX à ~26.08
avec stop 98 posé. Dup-safe : refuse si une décision §XVI existe déjà.

Usage (VM, APRÈS vm_replay_tribunal_2026-07-30.py) :
    git pull && python scripts/vm_spcx_venture_xvi_2026-07-30.py
"""
import json
from datetime import UTC, datetime

from shared import positions, storage

NOW = datetime.now(UTC).isoformat()

VARIANT = (
    "asymétrie détenue, pas valorisation : monopole physique du lancement + Starlink "
    "prouvé (11,4 Md$ rev / +4,4 Md$ op) ; ~72-83% de la capitalisation repose sur des "
    "anticipations de croissance difficiles à vérifier (S-1 2025 : consolidé -2,6 Md$ op, "
    "segment AI -6,4 Md$)"
)
INVAL = [
    "perte op consolidée aggravée 2 trim",
    "croissance profit op Starlink <20% YoY",
    "levée dilutive majeure",
    "pertes segment AI ni plafonnées ni séparées d'ici 12 mois",
    "ventes massives d'insiders au déblocage des lock-ups",
    "concurrent crédible réduisant durablement la part Falcon OU Starlink",
]
MILESTONES = (
    "MILESTONES (jugée ici, pas au cours) : cadence Falcon + part de marché mondiale · "
    "Starlink abonnés/ARPU/marge + coût marginal d'acquisition · Starship réutilisation · "
    "contrats défense · cash (levée/revalorisation/dilution)"
)
NOTES = (
    "§XVI venture V2 (cap 2% = c1). Pas de cible : jugée aux milestones. Stop 98 annulé "
    "(une venture ne se juge pas au cours). Trim 26.081->~10 = ordre LIMITE ; partial_exit "
    "+ CF fomo_greed à journaliser AU FILL, séparément. " + MILESTONES
)


def main() -> None:
    with storage.db() as cx:
        row = cx.execute(
            "SELECT id FROM theses "
            "WHERE ticker='SPCX' AND status='active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row, "STOP: pas de thèse SPCX active"
    sid = row[0]

    # Précondition : le replay tribunal a tourné (SPCX à ~26.08). §XVI est en AVAL.
    pos = positions.get_position("SPCX") or {}
    qty = pos.get("qty", 0)
    assert abs(qty - 26.08) < 0.5, (
        f"STOP: SPCX qty={qty} != ~26.08 — lancer le replay tribunal AVANT §XVI"
    )

    # Dup-safe : refuse si une décision §XVI SPCX existe déjà.
    with storage.db() as cx:
        dup = cx.execute(
            "SELECT count(*) FROM decisions WHERE ticker='SPCX' AND reasoning LIKE '%§XVI%'"
        ).fetchone()[0]
    assert dup == 0, "STOP: décision §XVI SPCX déjà présente — ne pas re-jouer"

    # 1. Re-typage : tactical + tag venture (position_type != priced).
    storage.set_position_type(sid, "tactical", position_tags=["venture"])

    # 2. Thèse : conviction 4->1 (c1 = cap 2%), stop NULL, cible NULL, variant/inval/milestones.
    with storage.db() as cx:
        cx.execute(
            "UPDATE theses SET conviction=1, "
            "stop_price=NULL, stop_value=NULL, stop_currency=NULL, stop_asof=NULL, "
            "target_price=NULL, "
            "target_full_value=NULL, target_full_currency=NULL, target_full_asof=NULL, "
            "target_partial_value=NULL, target_partial_currency=NULL, target_partial_asof=NULL, "
            "variant_perception=?, invalidation_triggers=?, notes=?, last_reviewed=? WHERE id=?",
            (VARIANT, json.dumps(INVAL, ensure_ascii=False), NOTES, NOW, sid),
        )

    # 3. Décision override (re-typage). PAS de CF : le CF fomo_greed appartient au
    #    trim (partial_exit), journalisé au fill. Contrefactuels notés en texte.
    storage.insert_decision_with_cf(
        ticker="SPCX", decision_type="override",
        reasoning=(
            "[STRUCTURED] §XVI typage venture V2 (cap 2%=c1) apres tribunal SPCX ; "
            "§XI-A non retenue, condition (c') echouee sur donnees ; stop 98 annule "
            "(venture jugee aux milestones, pas au cours). Trim 26.081->~10 = ordre "
            "limite -> partial_exit + CF fomo_greed au fill. Contrefactuels : hold 5.1% / "
            "sortie totale / panier KLAC-TEL-000660 | conviction: 1"
        ),
        thesis_id=sid, conviction=1, price_native=0, qty_before=0, currency="USD",
        bias_hypothesis_json=json.dumps(["fomo_greed"]),
    )

    # PREUVE
    with storage.db() as cx:
        r = cx.execute(
            "SELECT conviction, position_type, position_tags_json, stop_value, "
            "target_full_value FROM theses WHERE id=?", (sid,)
        ).fetchone()
    print(f"§XVI OK: SPCX id={sid} conv={r[0]} type={r[1]} tags={r[2]} stop={r[3]} target={r[4]}")
    print("RESTE (broker): placer l'ordre limite trim 26.081->~10, puis au fill "
          "journaliser partial_exit + CF fomo_greed (contrefactuels hold5.1/exit/panier).")


if __name__ == "__main__":
    main()
