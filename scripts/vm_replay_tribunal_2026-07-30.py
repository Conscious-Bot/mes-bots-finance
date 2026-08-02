"""REPLAY VM — tribunal 30/07 + CCJ signée. À LANCER SUR LA VM (source de vérité).

MERGE sur l'état VM actuel (préserve les écritures cron de la nuit) — n'écrase RIEN.
Portable : ids existants partagés VM/Mac ; nouveaux ids (000660/2802/CCJ) via lookup ticker.
Dup-safe : refuse si des trades 30/07 existent déjà sur la VM.

Usage (sur la VM) :
    git pull && python scripts/vm_replay_tribunal_2026-07-30.py
Puis réactiver le sync VM->Mac.
"""
import json
from datetime import UTC, datetime

from intelligence.thesis import add_thesis
from shared import positions, storage

NOW = datetime.now(UTC).isoformat()

# trade_date ÉPINGLÉ au 30/07 (défauts 1+2, catch 02/08) : add_buy/add_sell defaultent
# a now() -> sur la VM aujourd'hui les 14 trades seraient dates 08-02, et l'assert
# n==14 (post-inserts) leverait APRES insertion sur une table append-only = 14 trades
# mal dates INDESTRUCTIBLES. Valeur = cluster reel du run Mac (12:41:xx).
TRADE_DATE = "2026-07-30T12:41:00+00:00"


def tid(ticker: str) -> int | None:
    with storage.db() as cx:
        row = cx.execute(
            "SELECT id FROM theses WHERE ticker=? AND status='active' ORDER BY id DESC LIMIT 1",
            (ticker.upper(),),
        ).fetchone()
    return row[0] if row else None


def main() -> None:
    with storage.db() as cx:
        n0 = cx.execute(
            "SELECT count(*) FROM transactions WHERE trade_date LIKE '2026-07-30%'"
        ).fetchone()[0]
    assert n0 == 0, f"STOP: {n0} trades 30/07 deja sur la VM — reconcilier a la main, NE PAS re-jouer"
    # Garde AVANT écritures (défaut 2, catch 02/08) : sur append-only, valider en amont
    # — un assert post-insert ne protège rien (les lignes sont déjà là, indestructibles).
    assert TRADE_DATE.startswith("2026-07-30"), f"STOP: TRADE_DATE={TRADE_DATE} != 30/07"

    # FX ÉPINGLÉ aux taux du 30/07 (ceux que le run Mac a stockés), PAS get_fx_rate
    # (défaut 3, catch 02/08) : le fx du jour du run dériverait de +1.12% USD / +2.78%
    # JPY / +0.78% KRW = natifs faux, classe L12/L28 (bug trades 198-201). Épingler
    # garantit en prime la convergence bit-à-bit VM/Mac (mêmes price_native).
    fx = {
        "USD": 0.870700001716614,
        "JPY": 0.00534910010173917,
        "KRW": 0.000606500019785017,
    }

    def nat(eur: float, cur: str) -> float:
        return round(eur / fx[cur], 4)

    # ===== 1. VENTES =====
    sells = [
        ("COHR", 6.455648, 188.62, "USD", "tribunal 30/07 no-moat, slot faible"),
        ("ALAB", 3.759237, 221.59, "USD", "cloture juin, on-cost non-fiable"),
        ("ENTG", 9.244346, 90.73, "USD", "revirement: mediocrite relative"),
        ("6920.T", 5.307952, 177.81, "JPY", "doublon inspection, champion=KLAC"),
        ("6324.T", 30.75, 29.43, "JPY", "erreur de type venture, non requalifiee"),
    ]
    for tk, qty, eur, cur, note in sells:
        r = positions.add_sell(
            tk, qty=qty, price=nat(eur, cur), currency=cur, fx_at_trade=fx[cur],
            notes=f"{note} | ancre EUR {eur}/sh", trade_date=TRADE_DATE,
        )
        print("SELL", tk, "closed", r["closed"])
    positions.add_sell(
        "4063.T", qty=22.764, price=nat(30.71, "JPY"), currency="JPY",
        fx_at_trade=fx["JPY"], notes="rightsize cluster JPY", trade_date=TRADE_DATE,
    )

    # ===== 2. ACHATS (8) =====
    buys = [
        ("KLAC", 4.586, 152.64, "USD", "bump champion inspection"),
        ("000660.KS", 1.24, 806.0, "KRW", "re-entree T1 HBM confirmee"),
        ("000660.KS", 0.56, 806.0, "KRW", "re-entree T2"),
        ("MU", 0.784, 637.4, "USD", "OVERRIDE vs tribunal"),
        ("SPCX", 7.549, 99.34, "USD", "OVERRIDE bump non-instruite 1er"),
        ("AMZN", 2.46, 203.25, "USD", "OVERRIDE pre-print"),
        ("2802.T", 57.63, 26.03, "JPY", "NOUVELLE Ajinomoto ballast teinte"),
        ("SPCX", 4.93, 100.12, "USD", "2e bump SPCX OVERRIDE §XI ref §XIII"),
    ]
    for tk, qty, eur, cur, note in buys:
        positions.add_buy(
            tk, qty=qty, price=nat(eur, cur), currency=cur, fx_at_trade=fx[cur],
            notes=note, trade_date=TRADE_DATE,
        )
        print("BUY", tk)

    with storage.db() as cx:
        n = cx.execute("SELECT count(*) FROM transactions WHERE trade_date LIKE '2026-07-30%'").fetchone()[0]
    assert n == 14, f"STOP {n}!=14"
    assert abs((positions.get_position("SPCX") or {}).get("qty", 0) - 26.08) < 0.05, "SPCX!=26.08"
    print("LEDGER OK: 14 rows")

    # ===== 3. CLÔTURES + positions_meta closed =====
    for tk in ("COHR", "ALAB", "ENTG", "6920.T", "6324.T"):
        i = tid(tk)
        if i:
            storage.update_thesis_status(i, "concluded", notes="tribunal 30/07")
    with storage.db() as cx:
        for tk in ("COHR", "ALAB", "ENTG", "6920.T", "6324.T"):
            cx.execute("UPDATE positions_meta SET status='closed' WHERE ticker=? AND status='open'", (tk,))

    # ===== 4. CRÉATIONS (000660 signée + 2802) =====
    r = add_thesis(
        ticker="000660.KS", direction="long", horizon="18m", conviction=4,
        key_drivers=[
            "HBM sous engagements pluriannuels (LTAs take-or-pay, sold-out, record Q, marges 76%)",
            "SKH leader techno+commercial transition HBM (HBM4)",
            "Infrastructure strategique = pricing power sous-offre",
        ],
        invalidation_triggers=[
            "S2: CXMT design-win OU >100k stacks/trim",
            "Samsung: slot majoritaire HBM4 NVDA OU 2 trim. part>SK",
            "LTAs renegocies prix-vs-volume (Q1)",
            "marges HBM->commodity (baseline 76%)",
            "reduction structurelle contenu HBM/GPU",
            "S12: hybrid bonding parite yield",
        ],
        entry_price=1306321, target_price=None, stop_price=1000000,
        variant_perception=(
            "HBM = infrastructure strategique sous engagements pluriannuels ; SKH leader ; "
            "sortie 20/07 = erreur EXECUTION pas invalidation (signe gerant 30/07)"
        ),
        notes="CIBLE A REBASER anti-lock_in. Stop 1M KRW structurel 2 closes. T3 print Q3 fin oct.",
    )
    t660 = r["thesis_id"] if isinstance(r, dict) else r
    with storage.db() as cx:
        cx.execute("UPDATE theses SET stop_value=1000000,stop_currency='KRW',stop_asof=? WHERE id=?", (NOW, t660))

    r = add_thesis(
        ticker="2802.T", direction="long", horizon="18m", conviction=3,
        key_drivers=[
            "Coeur food defensif (~1/2 ballast pur)",
            "Monopole substrat ABF packaging avance = call quasi gratuit AI-compute",
        ],
        invalidation_triggers=[
            "film ABF alternatif qualifie en volume",
            "marges food erodees 2 trim consec",
            "bust capex packaging avance",
        ],
        entry_price=4450, target_price=None, stop_price=None,
        variant_perception="coeur food defensif + call ABF quasi gratuit (monopole substrat packaging avance)",
        notes="CIBLE/STOP A POSER post-print 06/08. Typage ballast-vs-infra §XII. c3 PROPOSEE.",
    )
    t2802 = r["thesis_id"] if isinstance(r, dict) else r

    # ===== 5. TRIGGERS amendes =====
    amend = {
        "KLAC": ["Export controls Chine amputent >20% du CA equipement OU inspection domestique chinoise qualifiee foundry tier-1"],
        "SNPS": [
            "Bascule modele licence-par-siege: churn seats EDA 2 trim OU perte pricing power workflows agentiques",
            "Revenus Chine IP: coupe reglementaire materielle",
        ],
        "MU": [
            "Part CXMT du bit supply DRAM mondial >20%",
            "Capex NAND coreen: expansion greenfield confirmee SKH/Samsung",
        ],
    }
    with storage.db() as cx:
        for tk, adds in amend.items():
            i = tid(tk)
            raw = cx.execute("SELECT invalidation_triggers FROM theses WHERE id=?", (i,)).fetchone()[0]
            cur = json.loads(raw) if raw else []
            for a in adds:
                if a not in cur:
                    cur.append(a)
            cx.execute(
                "UPDATE theses SET invalidation_triggers=?,last_reviewed=? WHERE id=?",
                (json.dumps(cur, ensure_ascii=False), NOW, i),
            )

    # ===== 6. CCJ re-souscrite (supersede) =====
    old_ccj = tid("CCJ")
    r = add_thesis(
        ticker="CCJ", direction="long", horizon="24-36m", conviction=3,
        key_drivers=[
            "Utilities occidentales sous-couvertes post-2027 (cycle de contrats)",
            "Offre primaire inelastique McArthur/Cigar tier-1 occidental quasi unique",
            "Annuite Westinghouse (49%, services+AP1000)",
            "Spot uranium +21% YoY pendant crash equity = preuve qui monte",
        ],
        invalidation_triggers=[
            "Term price uranium <$70 durablement 2 trim malgre AP1000",
            "Vague offre Kazatomprom+retours russes (contrats LT <$75)",
            "Glissement AP1000/SMR: zero commande ferme 12 mois",
            "Westinghouse marge services erosion 2 trim",
        ],
        entry_price=89.88, target_price=None, stop_price=78,
        variant_perception="Marche price un momentum-IA ; on possede un CYCLE DE CONTRATS. Signe gerant 30/07.",
        notes="CIBLE A DONNER. Cap ~4% c3. Stop $78 §XIV. Add eventuel = decision SEPAREE.",
    )
    tccj = r["thesis_id"] if isinstance(r, dict) else r
    with storage.db() as cx:
        cx.execute("UPDATE theses SET stop_value=78,stop_currency='USD',stop_asof=? WHERE id=?", (NOW, tccj))
        if old_ccj and old_ccj != tccj:
            cx.execute("UPDATE theses SET status='superseded',last_reviewed=? WHERE id=?", (NOW, old_ccj))

    # ===== 7. STOPS FRAIS (ids existants partages VM/Mac ; 000660/CCJ deja poses) =====
    stops = {
        "ASML.AS": (1270, "EUR"), "TSM": (350, "USD"), "KLAC": (160, "USD"), "SNPS": (345, "USD"),
        "AVGO": (335, "USD"), "MU": (685, "USD"), "BESI.AS": (177, "EUR"), "6857.T": (22500, "JPY"),
        "4063.T": (5350, "JPY"), "GOOGL": (298, "USD"), "AMZN": (215, "USD"), "SU.PA": (246, "EUR"),
        "SAF.PA": (304, "EUR"), "HO.PA": (208, "EUR"), "7011.T": (3450, "JPY"), "GEV": (855, "USD"),
        "LNG": (224, "USD"), "CCJ": (78, "USD"), "MP": (34, "USD"), "SPCX": (98, "USD"),
    }
    with storage.db() as cx:
        for tk, (val, cur) in stops.items():
            i = tid(tk)
            if i:
                cx.execute(
                    "UPDATE theses SET stop_price=?,stop_value=?,stop_currency=?,stop_asof=?,last_reviewed=? WHERE id=?",
                    (float(val), float(val), cur, NOW, NOW, i),
                )

    # ===== 8. SPGI parkée =====
    i = tid("SPGI")
    if i:
        storage.update_thesis_status(i, "out_of_scope", notes="sans position — parke reel-et-detenu 30/07, reversible")

    # ===== 9. DÉCISIONS + CF =====
    def qb(tk: str) -> float:
        return (positions.get_position(tk) or {}).get("qty", 0)

    storage.insert_decision_with_cf(
        ticker="MU", decision_type="scale_in", reasoning="[STRUCTURED] OVERRIDE vs verdict tribunal | conviction: 3",
        thesis_id=tid("MU"), conviction=3, price_native=737.73, qty_before=qb("MU") - 0.784,
        currency="USD", direction="long", price_eur=round(737.73 * fx["USD"], 2),
        bias_hypothesis_json=json.dumps(["override_vs_tribunal", "bottom_timing_instinct"]),
    )
    storage.insert_decision_with_cf(
        ticker="AMZN", decision_type="scale_in", reasoning="[STRUCTURED] OVERRIDE timing pre-print | conviction: 4",
        thesis_id=tid("AMZN"), conviction=4, price_native=235.24, qty_before=qb("AMZN") - 2.46,
        currency="USD", direction="long", price_eur=round(235.24 * fx["USD"], 2),
        bias_hypothesis_json=json.dumps(["override_pre_print"]),
    )
    storage.insert_decision_with_cf(
        ticker="2802.T", decision_type="entry", reasoning="[STRUCTURED] OVERRIDE timing+taille | conviction: 3",
        thesis_id=t2802, conviction=3, price_native=4450, qty_before=0,
        currency="JPY", direction="long", price_eur=round(4450 * fx["JPY"], 2),
        bias_hypothesis_json=json.dumps(["override_timing_taille"]),
    )
    storage.insert_decision_with_cf(
        ticker="SPCX", decision_type="scale_in",
        reasoning=(
            "[STRUCTURED] OVERRIDE §XI (§XIII) SPCX claim-only: HOLD ~5.6% vs venture 1%, "
            "couvre 2 bumps. Contrefactuels trim-460/exit | conviction: 4"
        ),
        thesis_id=tid("SPCX"), conviction=4, price_native=114.98, qty_before=13.602344922847626,
        currency="USD", direction="long", price_eur=round(114.98 * fx["USD"], 2),
        bias_hypothesis_json=json.dumps(["fomo_greed"]),
    )
    policy = [
        ("*PORTFOLIO*", "override", "[STRUCTURED] BACKSTOP §IX 30000EUR 2 closes -> expo ~50% | conviction: 5", None, 5),
        ("*PORTFOLIO*", "override", "[STRUCTURED] DIGUE gel_25 levee de facto §X, rail = backstop | conviction: 4", None, 4),
        ("ASML.AS", "no_action_flag", "[STRUCTURED] CAP-OVERRIDE trim 9->7% REFUSE (franchise EUV) | conviction: 5", "ASML.AS", 5),
        ("LNG", "no_action_flag", "[STRUCTURED] CAP-OVERRIDE trim 5->3.5% REFUSE | conviction: 3", "LNG", 3),
        ("*PORTFOLIO*", "override", "[STRUCTURED] EXCLUSION FISCALE permanente | conviction: 5", None, 5),
        ("*PORTFOLIO*", "override", "[STRUCTURED] STOPS FRAIS §XIV 21 lignes low-juillet-buffer, risque ~5.8k au-dessus backstop 30k | conviction: 5", None, 5),
    ]
    for tk, dt, rea, thtk, conv in policy:
        storage.insert_decision_with_cf(
            ticker=tk, decision_type=dt, reasoning=rea,
            thesis_id=(tid(thtk) if thtk else None), conviction=conv,
            price_native=0, qty_before=0, currency="EUR",
        )

    # ===== PREUVE =====
    with storage.db() as cx:
        tr = cx.execute("SELECT count(*) FROM transactions WHERE trade_date LIKE '2026-07-30%'").fetchone()[0]
        ccj = cx.execute("SELECT id,conviction FROM theses WHERE ticker='CCJ' AND status='active'").fetchone()
        a2802 = cx.execute("SELECT id FROM theses WHERE ticker='2802.T' AND status='active'").fetchone()
    print(f"PREUVE VM: trades_3007={tr} | CCJ active={ccj} | 2802={a2802}")
    print("REPLAY VM COMPLET OK. Puis: reactiver le sync (VM->Mac) -> le Mac converge sur la VM.")


if __name__ == "__main__":
    main()
