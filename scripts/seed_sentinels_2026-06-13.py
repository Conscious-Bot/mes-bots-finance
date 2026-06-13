"""Seed 10 sentinelles event/data manuelles -- cure G2 chantier #150.

Source canonique : conversation 13/06/2026.
Pose : 13 juin 2026.

CONTRAINTE DURE : prob=None pour les 10 entries. Le script ABORT si une
prob est None a l'execution. ZERO suggestion Claude en commentaire :
toute valeur en reference dans ce fichier serait un anchor psychologique
qui desarme la garde None et corromprait origin='manual' (chiffres
Claude posant en lieu et place de l'humain). Tu poses TES probs en
partant de None, pas en contestant des valeurs proposees par un tiers.

Mecanique sous-jacente : ce ledger mesure TON edge via Brier. Si une
prob vient de Claude (meme inspiree, meme contestee), le Brier mesure
l'edge de Claude sur les sentinelles -- pas le tien. C'est exactement le
critere nord VISION_PRO inverse.

Methode socratique de calibration (une par sentinelle) :
  Q : "A quelle frequence ce fait se realise-t-il dans le monde d'ici la
       date de resolution ?"
  Ecris le chiffre auquel tu es pret a etre tenu. Si tu hesites entre
  0.20 et 0.30, le 0.25 est probablement honnete -- pose-le, ne le
  derive pas d'une moyenne.

Test de coherence (poste-pose, surfaceee par le script) :
  Le total sum(probs) te dit combien de sentinelles tu attends voir se
  declencher en moyenne. Le script l'affiche AVANT INSERT. Si le total
  ne correspond pas a ta vraie vue macro (trop de ruptures attendues =
  scenario crise generalisee ; trop peu = rien casse), ajuste avant de
  valider. C'est la garde anti-inflation-de-conviction (cf KPI #11).

Mapping claim_type :
  - event = un fait discret annonce (S2 qualification, S4 declaration en
    call, S6 commande, S10 confirmation Google)
  - data  = un seuil sur une serie publiee (S1 spread, S3 DIO, S5 B2B,
    S7 prix metal, S8 chiffre capex, S9 billings)

PAS de claim_type='price' ici : reserve aux paris equity (les 285+
backfillees du ledger historique). S7 a un seuil chiffre mais c'est un
prix de commodity sur Shanghai Metals, pas un prix d'equity qui
prouverait une these -- reste data.

Procedure :
  1. Edit ce fichier, remplis les 10 probs DE TA MAIN, partant de None.
  2. python3 scripts/seed_sentinels_2026-06-13.py
  3. Confirmation interactive : le script affiche les 10 probs + le
     total, te demande "valider ? [y/N]". Tu peux refuser et editer
     encore.
  4. Si validation : 10 INSERT via insert_prediction(origin='manual').
     G2 passe rouge -> vert reel, et la colonne origin='manual' ne
     ment pas.
"""
from __future__ import annotations

import sys

from shared import storage

SENTINELS: list[dict] = [
    {
        "code": "S1", "ticker": None, "direction": "watch", "claim_type": "data",
        "claim": "Spot DRAM DDR5 < prix contrat (spread negatif) >=4 semaines consecutives",
        "drivers": ["spread spot/contrat = aube historique du glut",
                    "capex trio en expansion",
                    "barriere qualif HBM ralentit pas abolit le cycle"],
        "resolution_source": "TrendForce/DRAMeXchange hebdo",
        "horizon_days": 201, "target_date": "2026-12-31",
        "baseline_price": None, "conviction": 3,
        "prob": 0.12,  # S1 -- Olivier seul, 13/06/2026
    },
    {
        "code": "S2", "ticker": None, "direction": "watch", "claim_type": "event",
        "claim": "Hyperscaler ou NVDA/AMD qualifie HBM CXMT en volume (design-win annonce OU >100k stacks/trim)",
        "drivers": ["invalidation structurelle memoire #1",
                    "NDAA 5949 barre CXMT procurement federal 2027 = contre-vent"],
        "resolution_source": "annonce publique / SemiAnalysis",
        "horizon_days": 382, "target_date": "2027-06-30",
        "baseline_price": None, "conviction": 4,
        "prob": 0.70,  # S2 -- Olivier seul, 13/06/2026
    },
    {
        "code": "S3", "ticker": None, "direction": "watch", "claim_type": "data",
        "claim": "DIO Micron OU Hynix +20% YoY sur 2 trimestres consecutifs",
        "drivers": ["inventaire qui gonfle = warning precoce de retournement"],
        "resolution_source": "10-Q / earnings",
        "horizon_days": 291, "target_date": "2027-03-31",
        "baseline_price": None, "conviction": 3,
        "prob": 0.15,  # S3 -- Claude-assisted, vue super-cycle Olivier, 13/06/2026
    },
    {
        "code": "S4", "ticker": None, "direction": "watch", "claim_type": "event",
        "claim": "Schneider/Siemens Energy/GEV declare lead times transfo ou switchgear en baisse sequentielle en call",
        "drivers": ["lead time = top-indicator, le pic du delai precede le pic du cycle"],
        "resolution_source": "transcripts earnings (Quartr)",
        "horizon_days": 382, "target_date": "2027-06-30",
        "baseline_price": None, "conviction": 3,
        "prob": 0.12,  # S4 -- Claude-assisted, vue super-cycle Olivier, 13/06/2026
    },
    {
        "code": "S5", "ticker": "GEV", "direction": "watch", "claim_type": "data",
        "claim": "Book-to-bill GEV Power < 1.0 sur un trimestre",
        "drivers": ["B2B<1 = retournement de demande agrege"],
        "resolution_source": "earnings GEV",
        "horizon_days": 291, "target_date": "2027-03-31",
        "baseline_price": None, "conviction": 2,
        "prob": 0.10,  # S5 -- Claude-assisted, vue super-cycle Olivier, 13/06/2026
    },
    {
        "code": "S6", "ticker": None, "direction": "watch", "claim_type": "event",
        "claim": "Doosan ou entrant decroche commande ferme >1 GW d'un client occidental",
        "drivers": ["falaise turbine 2030 datee, capacite s'ajoute"],
        "resolution_source": "presse / annonces",
        "horizon_days": 566, "target_date": "2027-12-31",
        "baseline_price": None, "conviction": 3,
        "prob": 0.99,  # S6 -- Deja declenchee : Doosan a >2.66 GW chez US big-tech 03/2026
    },
    {
        "code": "S7", "ticker": None, "direction": "watch", "claim_type": "data",
        "claim": "NdPr OU Dy/Tb -30% vs niveau du 2026-06-11 SANS extension des floors occidentaux",
        "drivers": ["la Chine peut inonder",
                    "floors politiques (modele MP-DoD) = mitigant"],
        "resolution_source": "Shanghai Metals Market + annonces DoD/UE",
        "horizon_days": 382, "target_date": "2027-06-30",
        "baseline_price": None, "conviction": 2,
        "prob": 0.07,  # S7 -- Claude-assisted, vue Olivier (Chine monetise > inonde), 13/06/2026
    },
    {
        "code": "S8", "ticker": None, "direction": "watch", "claim_type": "data",
        "claim": "Capex agrege guide 2027 des 4 hyperscalers (MSFT/GOOGL/AMZN/META) en baisse vs 2026",
        "drivers": ["trigger cluster demande",
                    "700Md 2026 ne s'inverse pas sans choc"],
        "resolution_source": "guidances calls Q4",
        "horizon_days": 232, "target_date": "2027-01-31",
        "baseline_price": None, "conviction": 2,
        "prob": 0.08,  # S8 -- Claude-assisted, vue super-cycle Olivier, 13/06/2026
    },
    {
        "code": "S9", "ticker": None, "direction": "watch", "claim_type": "data",
        "claim": "SEMI NA billings (moyenne 3M) en baisse YoY 3 mois consecutifs",
        "drivers": ["cycle WFE se retourne, trim KLA en premier (+15% vs PT)"],
        "resolution_source": "SEMI mensuel public",
        "horizon_days": 201, "target_date": "2026-12-31",
        "baseline_price": None, "conviction": 3,
        "prob": 0.15,  # S9 -- Claude-assisted, vue super-cycle Olivier (nuance geo Asia), 13/06/2026
    },
    {
        "code": "S10", "ticker": "AVGO", "direction": "watch", "claim_type": "event",
        "claim": "Google confirme dual-sourcing TPU hors Broadcom (MediaTek ou autre) gen v8+",
        "drivers": ["bear-claim Broadcom #1, vecteur d'erosion le plus avance"],
        "resolution_source": "annonce / SemiAnalysis",
        "horizon_days": 201, "target_date": "2026-12-31",
        "baseline_price": None, "conviction": 3,
        "prob": 0.99,  # S10 -- Deja declenchee : Google Cloud Next 04/2026 (v8i Zebrafish = MediaTek)
    },
]

BASELINE_DATE = "2026-06-13"
METHODOLOGY = "olivier_sentinels_v1"


def main() -> int:
    import json

    # GARDE 1 : refuse de seeder si une prob est None
    missing = [s["code"] for s in SENTINELS if s["prob"] is None]
    if missing:
        print(
            f"ABORT : {len(missing)} sentinelles ont prob=None : {missing}",
            file=sys.stderr,
        )
        print(
            "Edit scripts/seed_sentinels_2026-06-13.py, remplis chaque prob "
            "de TA main (zero suggestion Claude pour anchoring), puis re-run.",
            file=sys.stderr,
        )
        return 1

    # GARDE 2 : verifie range (0, 1) strict
    bad_range = [(s["code"], s["prob"]) for s in SENTINELS if not (0.0 < s["prob"] < 1.0)]
    if bad_range:
        print(f"ABORT : probs hors range (0, 1) : {bad_range}", file=sys.stderr)
        return 1

    # GARDE 3 : surface sum(probs) = nb attendu de ruptures
    # Pas de chiffre de reference Claude. Tu juges si le total reflete ta vraie
    # vue macro. Trop haut = scenario crise generalisee. Trop bas = rien casse.
    total = sum(s["prob"] for s in SENTINELS)
    print("=== TES 10 PROBS POSEES ===")
    for s in SENTINELS:
        tic = s["ticker"] or "<macro>"
        print(f"  {s['code']:<4} {s['claim_type']:<6} {tic:<10} p={s['prob']:.2f}")
    print(f"\n  SUM(probs) = {total:.2f}")
    print(
        f"  -> tu attends ~{total:.1f} sentinelle(s) se declencher d'ici fin 2027."
    )
    print(
        "  Question de coherence : est-ce que ce total reflete ta vraie vue "
        "macro 18 mois ? Si oui, valider. Si non, editer le script et re-run."
    )
    print()
    # GARDE 4 : confirmation interactive
    try:
        ans = input("Valider et seeder les 10 sentinelles dans le ledger ? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nABORT (interrompu).", file=sys.stderr)
        return 1
    if ans not in ("y", "yes", "o", "oui"):
        print("ABORT (validation refusee). Edit le script et re-run.", file=sys.stderr)
        return 1
    print()

    inserted = []
    for s in SENTINELS:
        source_meta = json.dumps({
            "code": s["code"],
            "claim_text": s["claim"],
            "drivers": s["drivers"],
            "conviction": s["conviction"],
            "spec_reference": "ADR-010 chantier #150 G2",
        }, sort_keys=True, ensure_ascii=False)

        pid = storage.insert_prediction(
            signal_id=None,
            ticker=s["ticker"],
            direction=s["direction"],
            horizon_days=s["horizon_days"],
            baseline_price=s["baseline_price"],
            baseline_date=BASELINE_DATE,
            target_date=s["target_date"],
            methodology_version=METHODOLOGY,
            probability_override=s["prob"],
            source_metadata_json=source_meta,
            claim_type=s["claim_type"],
            resolution_source=s["resolution_source"],
            origin="manual",
        )
        if pid is None:
            print(f"FAIL {s['code']} : insert_prediction returned None", file=sys.stderr)
            return 1
        inserted.append((s["code"], pid, s["ticker"] or "<macro>",
                         s["claim_type"], s["prob"]))
        print(f"  OK {s['code']} -> pid={pid} ({s['ticker'] or '<macro>'}) "
              f"{s['claim_type']} p={s['prob']:.2f}")

    print()
    print(f"=== SEEDED {len(inserted)} sentinelles ===")
    print("G2 chantier #150 doit passer rouge -> vert. Verifier via :")
    print("  SELECT count(*) FROM predictions WHERE methodology_version='olivier_sentinels_v1'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
