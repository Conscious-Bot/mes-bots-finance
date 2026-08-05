"""RÉPARATION — sections 3→9 du tribunal 30/07, jamais exécutées sur la VM.

Découvert le 05/08 (gate invariants durci + crash 2802 introuvable) : le run VM du
31/07 a crashé sur l'assert n==14 (dates 31/07 vs filtre 30/07) APRÈS les trades,
AVANT tout le doctrinal. Manquent depuis 5 jours : clôtures thèses, créations
000660/2802, amendements triggers, 21 stops §XIV, SPGI, 10 décisions.
Classe RÉPARATION (la base contredit les décisions écrites du 30/07, decision log
e95c7ae/b7bf44e). Urgence : P1/P3 s'arbitrent contre des thèses absentes.

Leçons appliquées : commit PAR SECTION (le rollback du 05/08) · dup-safe par item ·
garde mort-né par prix courant (un stop >= prix est SKIPPÉ + flaggé, jamais posé) ·
SPCX EXCLU des stops (§XVI l'a annulé le 04/08) · natifs 000660/2802 alignés sur le
ledger VM accepté (fx 31/07) · journalisation tardive marquée comme telle.

Usage (VM, bot arrêté) : PYTHONPATH=$(pwd) venv/bin/python scripts/vm_tribunal_sections_3_9_2026-08-05.py
"""
import json
import sqlite3
from datetime import UTC, datetime

from intelligence.thesis import add_thesis
from shared import storage
from shared.book_performance import _last_price

NOW = datetime.now(UTC).isoformat()
TARD = " (journalisation tardive 05/08 — réplication VM des décisions du 30/07)"


def tid(cx, tk):
    r = cx.execute(
        "SELECT id FROM theses WHERE ticker=? AND status='active' ORDER BY id DESC LIMIT 1",
        (tk,),
    ).fetchone()
    return r[0] if r else None


def main() -> None:
    cx = sqlite3.connect(storage.DB_PATH)

    # ===== §3 CLÔTURES (dup-safe : skip si déjà concluded/closed) =====
    for tk in ("COHR", "ALAB", "ENTG", "6920.T", "6324.T"):
        i = tid(cx, tk)
        if i:
            cx.execute(
                "UPDATE theses SET status='concluded', notes=COALESCE(notes,'')||? , last_reviewed=? WHERE id=?",
                (" | tribunal 30/07" + TARD, NOW, i),
            )
            print(f"§3 clôture thèse {tk} (id {i})")
        n = cx.execute(
            "UPDATE positions_meta SET status='closed' WHERE ticker=? AND status='open'", (tk,)
        ).rowcount
        if n:
            print(f"§3 positions_meta closed {tk}")
    cx.commit()

    # ===== §4 CRÉATIONS (dup-safe : skip si thèse active existe) =====
    if not tid(cx, "000660.KS"):
        add_thesis(
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
            entry_price=1333333.32,  # natif ledger VM (fx 31/07, version acceptée)
            target_price=None, stop_price=1000000,
            variant_perception=(
                "HBM = infrastructure strategique sous engagements pluriannuels ; SKH leader ; "
                "sortie 20/07 = erreur EXECUTION pas invalidation (signe gerant 30/07)"
            ),
            notes="CIBLE A REBASER anti-lock_in. Stop 1M KRW structurel. T3 print Q3 fin oct." + TARD,
        )
        i = tid(cx, "000660.KS")
        cx.execute(
            "UPDATE theses SET stop_value=1000000, stop_currency='KRW', stop_asof=? WHERE id=?",
            (NOW, i),
        )
        cx.commit()  # libère le verrou AVANT le prochain add_thesis (sa propre connexion)
        print(f"§4 thèse 000660.KS créée (id {i}, stop 1M KRW)")
    if not tid(cx, "2802.T"):
        add_thesis(
            ticker="2802.T", direction="long", horizon="18m", conviction=3,
            key_drivers=[
                "Coeur food defensif (~1/2 ballast pur)",
                "Monopole substrat ABF packaging avance = call quasi gratuit AI-compute",
            ],
            invalidation_triggers=[
                "film ABF alternatif qualifie en volume",
                "marges food erodees 2 trim consec",
                "bust capex packaging avance",
                # draft pré-print dicté O. 05/08 :
                "part de marche ABF < 75% constatee (second fournisseur qualifie en volume chez Intel/AMD/NVDA)",
                "croissance segment materiaux electroniques < +10% YoY au print pendant que packaging avance croit >30% (perte de pricing power dans un goulot = incoherence fatale au recit monopole)",
                "capex expansion annonce SANS engagement clients adosse (§XI)",
                "organic interposers (Shinko/Ibiden) qualifies en substitut ABF sur un flagship accelerator",
            ],
            entry_price=4790.92,  # natif ledger VM (fx 31/07, version acceptée)
            target_price=None, stop_price=None,
            variant_perception=(
                "coeur food defensif + call ABF quasi gratuit (monopole substrat packaging avance) | "
                "DRIVER instruit 05/08 (dicte O.): monopole ABF film ~90% (Citrini, secondaire) — "
                "capacite mondiale 18-24 mois derriere la demande 2.5D/3D ; consommable = vit du VOLUME "
                "de packaging (NIVEAU), pas du capex equipement (filtre plateau : favorable)."
            ),
            notes=(
                "CIBLE/STOP A POSER post-print 06/08. Typage ballast-vs-infra §XII. c3 PROPOSEE. | "
                "LECTURE PRINT 06/08 : le consolide ne dit RIEN (ABF pese peu) — lire UNIQUEMENT segment "
                "materiaux (croissance, marge, capacite annoncee) + toute phrase sur allocation. Le print "
                "juge aussi l'override timing du 30/07 (§XIV RESTE OUVERT)." + TARD
            ),
        )
        print(f"§4 thèse 2802.T créée (id {tid(cx, '2802.T')}, draft pré-print inclus)")
    cx.commit()

    # ===== §5 AMENDEMENTS TRIGGERS (dup-safe par item) =====
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
    for tk, adds in amend.items():
        i = tid(cx, tk)
        if not i:
            print(f"§5 SKIP {tk} (pas de thèse active)")
            continue
        raw = cx.execute("SELECT invalidation_triggers FROM theses WHERE id=?", (i,)).fetchone()[0]
        cur = json.loads(raw) if raw else []
        added = 0
        for a in adds:
            if a not in cur:
                cur.append(a)
                added += 1
        if added:
            cx.execute(
                "UPDATE theses SET invalidation_triggers=?, last_reviewed=? WHERE id=?",
                (json.dumps(cur, ensure_ascii=False), NOW, i),
            )
        print(f"§5 {tk}: +{added} triggers")
    cx.commit()

    # ===== §7 STOPS §XIV — garde MORT-NÉ par prix courant ; SPCX EXCLU (§XVI) =====
    stops = {
        "ASML.AS": (1270, "EUR"), "TSM": (350, "USD"), "KLAC": (160, "USD"), "SNPS": (345, "USD"),
        "AVGO": (335, "USD"), "MU": (685, "USD"), "BESI.AS": (177, "EUR"), "6857.T": (22500, "JPY"),
        "4063.T": (5350, "JPY"), "GOOGL": (298, "USD"), "AMZN": (215, "USD"), "SU.PA": (246, "EUR"),
        "SAF.PA": (304, "EUR"), "HO.PA": (208, "EUR"), "7011.T": (3450, "JPY"), "GEV": (855, "USD"),
        "LNG": (224, "USD"), "CCJ": (78, "USD"), "MP": (34, "USD"), "000660.KS": (1000000, "KRW"),
    }
    flagged = []
    for tk, (val, cur_c) in stops.items():
        i = tid(cx, tk)
        if not i:
            print(f"§7 SKIP {tk} (pas de thèse active)")
            continue
        lp = _last_price(cx, tk, None)
        px = lp[0] if lp else None
        if px is not None and float(val) >= float(px):
            flagged.append((tk, val, px))
            print(f"§7 ⚠ SKIP {tk}: stop {val} >= prix {px:.2f} (mort-né — re-dictée gérant requise)")
            continue
        cx.execute(
            "UPDATE theses SET stop_price=?, stop_value=?, stop_currency=?, stop_asof=?, last_reviewed=? WHERE id=?",
            (float(val), float(val), cur_c, NOW, NOW, i),
        )
        print(f"§7 stop {tk} -> {val} {cur_c}")
    cx.commit()

    # ===== §8 SPGI parkée =====
    i = tid(cx, "SPGI")
    if i:
        storage.update_thesis_status(i, "out_of_scope", notes="sans position — parke reel-et-detenu 30/07" + TARD)
        print(f"§8 SPGI out_of_scope (id {i})")

    # ===== §9 DÉCISIONS + CF (dup-safe par marqueur ; qty_before = état courant - qty tribunal, inchangé depuis) =====
    def qb(tk):
        r = cx.execute(
            "SELECT COALESCE(SUM(CASE WHEN side='BUY' THEN qty ELSE -qty END),0) FROM transactions WHERE ticker=?",
            (tk,),
        ).fetchone()[0]
        return float(r or 0)

    def dup(tag):
        return cx.execute(
            "SELECT count(*) FROM decisions WHERE reasoning LIKE ?", (f"%{tag}%",)
        ).fetchone()[0] > 0

    trade_decs = [
        ("MU", "scale_in", "OVERRIDE vs verdict tribunal", 3, 737.73, qb("MU") - 0.784, ["fomo_greed"]),
        ("AMZN", "scale_in", "OVERRIDE timing pre-print", 4, 235.24, qb("AMZN") - 2.46, ["fomo_greed"]),
        ("2802.T", "entry", "OVERRIDE timing+taille Ajinomoto", 3, 4790.92, 0.0, ["fomo_greed"]),
        ("SPCX", "scale_in", "OVERRIDE §XI (§XIII) SPCX claim-only HOLD ~5.6%", 4, 114.98, 13.602345, ["fomo_greed"]),
    ]
    for tk, dt, rea, conv, px, q0, bias in trade_decs:
        tag = f"[TRIB-30/07] {rea}"
        if dup(tag):
            print(f"§9 SKIP décision {tk} (déjà présente)")
            continue
        storage.insert_decision_with_cf(
            ticker=tk, decision_type=dt,
            reasoning=f"[STRUCTURED] {tag} | conviction: {conv}{TARD}",
            thesis_id=tid(cx, tk), conviction=conv, price_native=px, qty_before=q0,
            currency="USD" if tk != "2802.T" else "JPY", direction="long",
            bias_hypothesis_json=json.dumps(bias),
        )
        print(f"§9 décision {dt} {tk} + CF")
    policy = [
        ("*PORTFOLIO*", "override", "BACKSTOP §IX 2 closes -> expo ~50%", 5),
        ("*PORTFOLIO*", "override", "DIGUE gel_25 levee de facto §X, rail = backstop", 4),
        ("ASML.AS", "no_action_flag", "CAP-OVERRIDE trim 9->7% REFUSE (franchise EUV)", 5),
        ("LNG", "no_action_flag", "CAP-OVERRIDE trim 5->3.5% REFUSE", 3),
        ("*PORTFOLIO*", "override", "EXCLUSION FISCALE permanente", 5),
        ("*PORTFOLIO*", "override", "STOPS FRAIS §XIV 21 lignes low-juillet-buffer", 5),
    ]
    for tk, dt, rea, conv in policy:
        tag = f"[TRIB-30/07] {rea}"
        if dup(tag):
            print(f"§9 SKIP policy ({rea[:30]}…)")
            continue
        storage.insert_decision_with_cf(
            ticker=tk, decision_type=dt,
            reasoning=f"[STRUCTURED] {tag} | conviction: {conv}{TARD}",
            thesis_id=None, conviction=conv, price_native=0, qty_before=0, currency="EUR",
        )
        print(f"§9 policy {dt} ({rea[:40]}…)")
    cx.commit()

    # ===== PREUVE =====
    t28, t66 = tid(cx, "2802.T"), tid(cx, "000660.KS")
    nstops = cx.execute(
        "SELECT count(*) FROM theses WHERE status='active' AND stop_value IS NOT NULL AND stop_asof >= date('now')"
    ).fetchone()[0]
    print(f"\nPREUVE: 2802={t28} 000660={t66} stops_frais_aujourdhui={nstops} flagged_mort_ne={flagged}")
    cx.close()


if __name__ == "__main__":
    main()
