#!/usr/bin/env python3
"""Audit-trace idempotent — triggers-check hebdo 2026-07-28 (validé Olivier).

30 mutations sur 15 thèses, 3 familles :
1. PREFIX_REWRITES (26) : triggers vagues ou ancrés sur des métriques NON
   PUBLIÉES (gross margin AWS/GCP, « SoC test margin », bookings ASML
   discontinués Q1 2026, segment « advanced materials » ENTG inexistant...)
   → re-ancrés sur métriques publiées + baselines datées (fact-check web
   28/07, sources dans SESSION_STATE ## Triggers check 2026-07-28).
2. FULL_REPLACE (2) : GEV id=56 + 6324.T id=55 stockaient du TEXTE BRUT
   (pas JSON) ; GEV portait la troncature « > guided 00M » (= $400M mangé).
   → listes JSON canoniques, clauses éclatées, baselines ajoutées.
3. APPENDS (2) : triggers Chine SNPS + MP — les deux risques qui ont
   MATÉRIALISÉ les pertes (−22,5 % / −32,3 %) vivaient hors-grille
   (reset Chine SNPS fév. 2026 ; MP sur liste de contrôle export chinoise
   22/06/2026). Ajoutés post-mortem sur décision Olivier 28/07.

Sûreté : match par PRÉFIXE UNIQUE, assert exactement 1 hit AVANT update ;
déjà réécrit → skip idempotent ; mismatch → ABORT du ticker entier (aucune
écriture partielle par thèse). Run sur VM authoritative (single-source).
Non touché ce round : MU S12 « sentinelle à poser » + codes S AVGO non
résolus par le cross-ref → rituel /sentinel-check dédié.
"""
import json
import sqlite3
import sys

from shared.storage import DB_PATH

# (old_prefix_unique, new_text)
PREFIX_REWRITES: dict[str, list[tuple[str, str]]] = {
    "ASML.AS": [(
        "Bookings <",
        "Guidance FY révisée en baisse (baseline 15/07/2026 : FY26 €43-45B, GM 54-56%) "
        "OU total net sales <€9B 2 Q consec. (baseline Q2 2026 : €9,3B, guide Q3 €11-12B) "
        "— remplace bookings, métrique discontinuée par ASML depuis Q1 2026",
    )],
    "4063.T": [(
        "Wafer ASP down",
        "Révision LTA 300mm H2 2026 conclue en BAISSE (baseline 12/05/2026 : prix maintenus, "
        "attente de hausse) OU ASP 300mm reporté en baisse YoY par Sumco/Shin-Etsu 2 Q consec.",
    )],
    "6857.T": [(
        "SoC test margin <30%",
        "Operating margin société <30% 2 Q consec. (baseline janv. 2026 : OI ¥454B / sales "
        "¥1,07T ≈ 42%, guidance FY2025 relevée) — remplace marge SoC test, non publiée",
    )],
    "AMZN": [
        (
            "AWS gross margin",
            "AWS operating margin <30% 2 Q consec. (baseline Q1 2026 : 37,7%) "
            "— gross margin AWS non publiée",
        ),
        (
            "Project Kuiper",
            "Kuiper/Leo : extension FCC refusée OU service commercial pas lancé au 31/12/2026 "
            "OU capex divulgué >1,5× dernier chiffre communiqué (baseline 28/07/2026 : "
            "deadline FCC 07/2026 non tenue, extension 2028 demandée)",
        ),
    ],
    "GOOGL": [(
        "GCP gross margin",
        "Google Cloud operating margin (segment) <25% 2 Q consec. (baseline Q2 2026 : 35,6%) "
        "— gross margin GCP non publiée",
    )],
    "KLAC": [(
        "KLA margin <50%",
        "Non-GAAP gross margin <58% 2 Q consec. (baseline Q3 FY26 : 62,2%, guide Q4 "
        "61,75%±1%, headwind DRAM ~100bps CY2026)",
    )],
    "SNPS": [
        (
            "Synergies Ansys ratées",
            "Guidance revenus FY abaissée 2 publications consec. OU cible synergies Ansys "
            "(400 M$ an 4) réduite OU client multiphysics majeur nommé perdu (baseline "
            "27/05/2026 : FY26 relevée à 9,665 Md$ mid, synergies « accélérées »)",
        ),
        (
            "Synopsys ASP under pressure",
            "Design IP sans retour en croissance YoY d'ici Q4 FY26 (management guide recovery "
            "séquentiel H2) OU adj op margin segment <20% un trimestre de plus (baseline "
            "Q2 FY26 : 454,2 M$, −5,8% YoY, marge 24%)",
        ),
    ],
    "SU.PA": [(
        "Schneider margin under pressure",
        "Marge adj. EBITA FY26 <19,1% (bas de fourchette) OU perte nommée d'un contrat "
        "datacenter majeur face à Huawei/Delta/Kehua (baseline 04/2026 : 19,1-19,4% "
        "réaffirmée, FX −10bps)",
    )],
    "7011.T": [
        (
            "Advanced reactor projects cancelled",
            "≥2 projets advanced-reactor flagship US (TerraPower Natrium, X-energy Xe-100, "
            "Holtec Palisades) annulés ou repoussés >24 mois sur 12 mois glissants (baseline "
            "07/2026 : TerraPower décision permis S1 2026, dépôt Holtec visé 2026)",
        ),
        (
            "Gas displaced renewables",
            "Turbines gaz : demande mondiale <70 GW/an OU commandes grandes turbines MHI "
            "<20 unités/an (baseline FY2025 publié 12/05/2026 : ~100 GW marché, 35 unités "
            "MHI, guidance 70-100 GW)",
        ),
    ],
    "ALAB": [
        (
            "PCIe retimer commoditization",
            "GM non-GAAP <70% 2 Q consec. (hors warrants) OU croissance rev <+20% YoY "
            "(baseline Q1'26 05/05/2026 : GM 76,4%, +93% YoY)",
        ),
        (
            "Cadence/Broadcom enter retimer",
            "Design win retimer/fabric Broadcom/Marvell/Credo/Parade chez un top-3 "
            "end-customer ALAB, OU décélération ALAB <+20% YoY simultanée à accélération "
            "retimers CRDO (baseline : ALAB +93% YoY, CRDO retimers ~+85% FY26)",
        ),
        (
            "Customer concentration risk",
            "Top end-customer (>70% rev FY2025) annonce in-sourcing/second-source "
            "connectivité OU rev −15% séquentiel attribué à ce client (baseline 10-K "
            "FY2025 : top-1 >70%, top-3 ~86%)",
        ),
    ],
    "AVGO": [
        (
            "S10 dual-sourcing TPU",
            "S10 dual-sourcing TPU : un second design partner (MediaTek/Marvell/AMD) livre "
            "EN VOLUME un TPU compute die (pas I/O ni variante cost-down) OU contrat "
            "Google-Marvell signé (baseline 04/2026 : MediaTek TPUv7e prod 2026, "
            "Marvell = talks non signés)",
        ),
        (
            "S11 backlog growth flat",
            "S11 AI bookings/backlog flat 2 Q consec. (baseline 03/06/2026 : bookings AI "
            ">30 Md$ au Q2 FY26, book-to-bill ~3× — série AI, ne pas comparer au backlog "
            "TOTAL 110 Md$ sept. 2025)",
        ),
    ],
    "BESI.AS": [(
        "Concurrence TEL aggressive",
        "Hybrid bonder TEL ou ASMPT qualifié en mass production HBM chez SK hynix/Samsung/"
        "Micron avec commande multi-systèmes documentée (baseline Q2-26 23/07/2026 : BESI "
        "orders record €292,9 M, 20 clients hybrid bonding)",
    )],
    "CCJ": [(
        "Production cost > $40/lb",
        "Unit cost of sales segment uranium (C$/lb) en hausse >10% a/a 2 Q consec. OU coût "
        "moyen d'inventaire >C$55/lb (baseline 31/03/2026 : C$50,24/lb, unit cost Q1 2026 "
        "−3% a/a)",
    )],
    "COHR": [(
        "Optical transceivers price war",
        "ASP marché 800G <$350/module OU GM non-GAAP consolidée en baisse a/a 2 Q consec. "
        "(baseline 06/05/2026 : GM 39,6% +105bps a/a, ASP 800G 2026E ~$400 vs $600-800 "
        "en 2025)",
    )],
    "ENTG": [
        (
            "Margin advanced materials",
            "GM consolidée <44% 2 Q consec. (baseline Q1 2026 30/04/2026 : 46,9%, guide Q2 "
            "46,25-47,25%) — segment « advanced materials » inexistant dans le reporting ENTG",
        ),
        (
            "EUV resist share loss",
            "Perte design win précurseurs/filtration MOR-EUV chez un client top-3 OU "
            "JSR/TOK/Shin-Etsu internalise précurseurs+filtration (baseline 26/05/2026 : "
            "cross-licensing non-exclusif Entegris×JSR/Inpria) — ENTG ne vend pas de resist",
        ),
    ],
    "LNG": [(
        "Tarifs LNG export US",
        "DOE/FERC : restriction quantitative, taxe export ou moratoire rétabli (Federal "
        "Register) OU autorisations long terme gelées <56,3 Bcf/d sur 12 mois (baseline "
        "31/03/2026 : 44 autorisations, 56,3 Bcf/d)",
    )],
    "SAF.PA": [
        (
            "GTF Pratt&Whitney cure costs",
            "AOG A320neo (PW1100) <100 appareils OU P&W annonce 2 Q consec. de gains nets "
            "de campagnes A320neo vs LEAP (baseline 07/2026 : engagement P&W AOG "
            "single-digit fin 2026)",
        ),
        (
            "Aftermarket margin <22%",
            "Spares civils <+5% YoY (USD) 2 semestres consec. (baseline S1 2026 : +27,9%) "
            "OU marge op groupe <16% (baseline S1 2026 : 18,4%) — marge aftermarket "
            "non publiée",
        ),
        (
            "Defense EU budget annonces",
            "Défense Europe+Canada repasse <2,5% PIB agrégé (baseline 2026 : 2,53%, ICDS "
            "07/2026) OU abandon/report officiel cible NATO 3,5% core 2035",
        ),
    ],
}

# ticker -> (raw_prefix_attendu_du_champ_texte_brut, nouvelle_liste)
FULL_REPLACE: dict[str, tuple[str, list[str]]] = {
    "GEV": (
        "Wind segment EBIT loss deepens",
        [
            "Wind : perte EBITDA segment creuse au-delà du guide ~$400M FY26 (baseline "
            "22/07/2026 : guide réitéré ≈$400M, perte Q2 ~$275M vs $165M a/a — run-rate "
            "sous tension)",
            "Tarifs : impact net 2026 re-guidé >$250M OU en hausse séquentielle (baseline "
            "22/07/2026 : $100-200M, révisé en baisse vs $250-350M avril)",
            "Gas : slippage du ramp H2 turbines (baseline 07/2026 : 20 GW cadence "
            "annualisée attendue Q3 2026, 24 GW visés 2028, backlog+slots 116 GW, "
            "réservations jusqu'à 2031)",
            "Valo : forward P/E <35× (baseline 23/07/2026 : ~46× — source retenue "
            "stockanalysis.com)",
        ],
    ),
    "6324.T": (
        "Earnings deterioration continue",
        [
            "OP trimestriel en baisse YoY 2 Q consec. POST-guidance OU révision en baisse "
            "de la guidance FY27/3 (baseline 13/05/2026 : OP ¥6,2 Md, RN ¥4,5 Md — premier "
            "test Q1 FY27 le 07/08/2026)",
            "Breakthrough cycloïdal concurrent (Nabtesco, Spinea) : annonce techno ou "
            "design-win majeur documenté (baseline 07/2026 : aucun ; expansion capacitaire "
            "Nabtesco ≠ rupture ; rumeur M&A Nabtesco/HDS démontée — alliance dissoute 2022)",
            "Ventes totales OU commandes en baisse YoY 2 Q consec. (baseline FY26/3 : "
            "¥59,56 Md, +7,0%)",
        ],
    ),
}

APPENDS: dict[str, str] = {
    "SNPS": (
        "Chine : revenus Chine en baisse >25% YoY 2 semestres consec. OU nouvelle "
        "restriction export US EDA→Chine (règle BIS) (baseline fév. 2026 : Chine −22% YoY "
        "= driver n°1 du reset guidance — risque matérialisé hors-grille, ajouté 28/07/2026)"
    ),
    "MP": (
        "Chine (risque direct) : nouveau durcissement MOFCOM visant MP post-22/06/2026 OU "
        "suspension du 10/11/2026 non levée avec licences refusées OU retard 10X attribué "
        "au sourcing équipements (baseline 22/06/2026 : MP sur liste de contrôle export "
        "chinoise, aucun retard annoncé — ajouté 28/07/2026)"
    ),
}


def _load(cx: sqlite3.Connection, ticker: str) -> tuple[list | None, str | None]:
    row = cx.execute(
        "SELECT invalidation_triggers FROM theses WHERE ticker=? AND status='active'",
        (ticker,),
    ).fetchone()
    if not row:
        return None, None
    raw = row[0] or "[]"
    try:
        parsed = json.loads(raw)
        return (parsed if isinstance(parsed, list) else None), raw
    except (json.JSONDecodeError, TypeError):
        return None, raw


def _save(cx: sqlite3.Connection, ticker: str, trigs: list[str]) -> None:
    cx.execute(
        "UPDATE theses SET invalidation_triggers=? WHERE ticker=? AND status='active'",
        (json.dumps(trigs, ensure_ascii=False), ticker),
    )


def main() -> int:
    # timeout=30 : la VM a le bot qui écrit en parallèle (WAL) — sans busy
    # timeout le run 28/07 a pris "database is locked" en pleine boucle.
    cx = sqlite3.connect(DB_PATH, timeout=30)
    done = skipped = aborted = 0

    # 1. Réparations texte brut -> JSON (avant les prefix-rewrites)
    for ticker, (raw_prefix, new_list) in FULL_REPLACE.items():
        trigs, raw = _load(cx, ticker)
        if raw is None:
            print(f"{ticker} : thèse active introuvable — skip")
            skipped += 1
            continue
        if trigs is not None and trigs == new_list:
            print(f"{ticker} : déjà réparé — idempotent skip")
            skipped += 1
            continue
        if trigs is not None:
            print(f"{ticker} : champ déjà JSON mais ≠ attendu — ABORT (vérifier à la main)")
            aborted += 1
            continue
        if not raw.startswith(raw_prefix):
            print(f"{ticker} : texte brut ne commence pas par « {raw_prefix} » — ABORT")
            aborted += 1
            continue
        _save(cx, ticker, new_list)
        done += 1
        print(f"{ticker} : texte brut → JSON {len(new_list)} triggers ✓")

    # 2. Rewrites par préfixe unique
    for ticker, entries in PREFIX_REWRITES.items():
        trigs, raw = _load(cx, ticker)
        if trigs is None:
            print(f"{ticker} : triggers illisibles/absents — ABORT ticker")
            aborted += len(entries)
            continue
        pending: list[tuple[int, str]] = []
        ok = True
        for old_prefix, new_text in entries:
            if new_text in trigs:
                print(f"{ticker} [{old_prefix[:30]}…] : déjà réécrit — skip")
                skipped += 1
                continue
            hits = [i for i, t in enumerate(trigs) if isinstance(t, str) and t.startswith(old_prefix)]
            if len(hits) != 1:
                print(f"{ticker} [{old_prefix[:30]}…] : {len(hits)} hit(s) (attendu 1) — ABORT ticker")
                ok = False
                break
            pending.append((hits[0], new_text))
        if not ok:
            aborted += len(entries)
            continue
        for idx, new_text in pending:
            trigs[idx] = new_text
            done += 1
        if pending:
            _save(cx, ticker, trigs)
            print(f"{ticker} : {len(pending)} rewrite(s) ✓")

    # 3. Appends Chine
    for ticker, new_text in APPENDS.items():
        trigs, raw = _load(cx, ticker)
        if trigs is None:
            print(f"{ticker} (append) : triggers illisibles — ABORT")
            aborted += 1
            continue
        if new_text in trigs:
            print(f"{ticker} (append Chine) : déjà présent — skip")
            skipped += 1
            continue
        trigs.append(new_text)
        _save(cx, ticker, trigs)
        done += 1
        print(f"{ticker} : trigger Chine ajouté ✓ ({len(trigs)} triggers)")

    cx.commit()
    print(f"\nBILAN : {done} écrits, {skipped} skips idempotents, {aborted} ABORT")
    return 1 if aborted else 0


if __name__ == "__main__":
    sys.exit(main())
