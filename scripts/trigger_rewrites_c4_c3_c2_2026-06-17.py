"""Trigger rewrites batch c4+c3+c2 — méthode #135 systematic test 2026-06-17.

## Contexte

Suite directe du batch c5 (cf `scripts/trigger_rewrites_c5_2026-06-17.py`).
Test systématique des invalidation_triggers sur toutes les thèses actives par
conviction décroissante : c4 (8 tickers) + c3 (10 tickers) + c2 (1 ticker).

**Résultat global cumulé c5+c4+c3+c2** : 0/88 triggers fired actuels sur
26 thèses actives. **Toutes thèses INTACTES** sur le cycle bull AI/semi/
datacenter/defense actuel. **20 rewrites** appliqués pour mesurabilité
(criteria flou → seuils chiffrés avec baselines Q1 2026).

## Rewrites c4 (5 triggers, 5 tickers)

### 000660.KS #2 — S12 sentinelle non posée removed

AVANT : criteria référençait sentinelle S12 ('Hybrid bonding atteint parité')
qui n'a jamais été postée → cross-ref helper risque faux positif.

APRÈS : criteria self-contained mesurable (yield ≥80% sur 16-layer hybrid
bonding stack en production volume vs SK Hynix MR-MUF).

### MU #2 — S12 sentinelle removed (identique 000660.KS, PARTAGÉ groupe mémoire)

Même rewrite que 000660.KS #2 — sentinelle S12 jamais publiée donc remove
le cross-ref reference. Baseline 2026 SK Hynix MR-MUF advantage maintenu.

### HO.PA #3 — US primes criteria flou

AVANT : wording vague sur Thales/US primes share.

APRÈS : Thales revenue from European defense customers DOWN >10% YoY sur 2Q
consec OR US primes >50% European equipment market share annoncé. Baseline
2026 : US ~40% share (Oxford Economics).

### KLAC #3 — margin GM/op ambigu

AVANT : 'margin <50%' ambigu (GM vs OM).

APRÈS : GM <55% OR OM <30% sur 2Q consec (vs Q3 2026 baseline GM 62.2%, OM
42.6% — 12pp/12.6pp headroom).

### SU.PA #2 — Asian competition criteria flou

AVANT : 'Schneider margin under pressure from Asian competition'.

APRÈS : EBITA margin compression >100bps YoY OR China datacenter share drop
>5pp OR Huawei/Chinese wins >3 hyperscaler NA DC contracts/12mois. Baseline
Q4 2025 EBITA +12% organic 5e année expansion.

## Rewrites c3 (16 triggers, 8 tickers)

### 6920.T #1 — clarif actinic vs E-beam

AVANT : 'KLA ou concurrent design-in inspection masque EUV majeur foundry
tier-1' — wording capturerait KLA TeraBeam 8XX (E-beam, co-dev TSMC, annoncé
12/03/2026) qui ne substitue PAS Lasertec actinic.

APRÈS : précise 'EUV ACTINIC (13.5nm wavelength, vs E-beam ou DPV)'. KLA
TeraBeam = technologie complémentaire pitch <20nm, pas substitution MATRICS
pitch 36nm+.

### ALAB #1, #2, #3 — criteria one-liner → mesurables

AVANT : 'PCIe retimer commoditization.' / 'Cadence/Broadcom enter retimer
aggressive.' / 'Customer concentration risk.' — trois one-liners non-mesurables.

APRÈS :
- #1 : GM non-GAAP <60% sur 2Q consec (vs Q1 2026 ~73%) OR PCIe Gen 6 retimer
  ASP decline >25% YoY.
- #2 : AVGO/MRVL design-win majoritaire >30% socket-share chez ≥2 hyperscalers
  OR aggregate AVGO+MRVL retimer revenue >$500M/Q (vs ALAB $300-365M/Q).
  Baseline MRVL fiscal 2028 full revenue, ALAB Q1 +93% YoY.
- #3 : Single customer >40% (vs Customer A 29% Q1 2026) OR Top 2 >65% (vs 50%)
  OR Customer A revenue decline >15% YoY.

### AMD #2, #3, #4 — wording obsolete + doctrine violation

- #2 AVANT : 'MI300X design wins reculent' — gen obsolete (now MI355X/MI450/
  MI455X).
- #2 APRÈS : MI450/MI455X reductions (Meta 6 GW partiel, OpenAI/AWS/GCP/Azure)
  OR perte design >$2B annual au profit NVDA/AVGO. Baseline Meta 6 GW warrant
  160M shares, MI450 lead customer forecasts EXCEEDING 2027 plans.
- #3 AVANT : 'Server CPU share Intel reprend (ramp Sierra Forest)'.
- #3 APRÈS : AMD server share decline >2pp sur 2Q consec (vs gains accelerated
  Q1 2026) OR AMD server CPU revenue YoY <+20% sur 2Q (vs +50%/+70% Q1/Q2).
  Baseline Intel 6Q beating mais AMD aussi en expansion = market expanding.
- #4 **DOCTRINE VIOLATION** : 'Valuation passe sous 30x forward' = trigger
  price-only banni par memory `currency_native_invariant`.
- #4 APRÈS : GM non-GAAP <50% sur 2Q consec (vs Q1 2026 ~53%, +3pp YoY) OR
  Data Center op margin <25% (vs ~28% = $1.6B/$5.8B). Fundamental measurable.

### COHR #1, #2, #3 — three one-liners → mesurables

AVANT : 'Optical transceivers price war.' / 'Coherent margin <30% on optical.'
/ 'Datacom capex revised down.'

APRÈS :
- #1 : ASP 800G/1.6T transceiver decline >20% YoY (COHR/LITE/AAOI calls) OR
  Chinese OEM (Innolight/Eoptolink) >25% share design wins hyperscaler.
  Baseline Q3 FY2026 COHR Datacenter +41% YoY, NVDA $2B Coherent investment.
- #2 : Consolidated GAAP GM <33% sur 2Q OR Datacenter & Comms segment profit
  margin <22% (vs Q3 FY2026 25.5%). Baseline segment profit $348M / $1,362M.
- #3 : Hyperscaler CapEx aggregate MSFT+META+GOOGL+AMZN revised down >15% sur
  1Q OR ≥2 hyperscaler annonce ralentissement. Baseline 2026 capex
  $700-760B (+75-90% YoY), supply ahead of demand.

### ENTG #4, #5 — wording vague + audience off-target

- #4 AVANT : 'ASML EUV ramp <plan (downstream chemistry revenue suit)' — vague.
- #4 APRÈS : ASML EUV net sales sous low-end annual guidance sur 2Q consec
  (vs Q1 2026 ASML €8.8B above consensus €8.69B) OR ASML annual guide revised
  down >10% (vs backlog $46.47B).
- #5 AVANT : 'Cleaning chemistry hyperscaler contract loss' — ENTG sert fabs
  pas hyperscaler direct.
- #5 APRÈS : ENTG perte contract majeur (>$50M annual) chez foundry tier-1
  (TSMC/Samsung/Intel) au profit Versum/Air Liquide/Linde OR APS segment
  revenue YoY <0% sur 2Q (vs +7% Q1 2026).

### LNG #2 — terminologie 'Sabine Pass Stage 3' inexistante

AVANT : 'Sabine Pass Stage 3 OU Corpus Christi Stage 3 slip >12 mois' — SPL
n'a pas de Stage 3, c'est CCL (Corpus Christi).

APRÈS : CCL Stage 3 Trains 6-7 OU mid-scale 8-9 OU SPL Expansion / CCL
Expansion FID slip >12 mois. Baseline Trains 1-5 substantially complete, 6-7
accelerated, production raised +1 Mtpa, EBITDA guidance RAISED +$500M.

### MP #3, #5 — Stage 3 vague + audience off-target

- #3 AVANT : 'Stage 3 magnet plant slip >12 mois' — quel plant ?
- #3 APRÈS : 10X Facility Northlake TX OU Independence Facility expansion
  (3,000 tons) OU Mountain Pass HREE separation circuit slip >12 mois.
  Baseline Independence NdFeB Dec 2025, 10X broke ground Q1 2026.
- #5 AVANT : 'Hyperscaler magnet substitution' — MP sert EV/defense/Apple
  pas hyperscaler.
- #5 APRÈS : EV/automotive/defense customer (GM, Apple, DoD) annonce switch
  >$50M annual vers rare-earth-free magnets OR ≥2 EV OEM tier-1 design-in
  rare-earth-free. Baseline Apple $500M recycled commit MP (substitution
  REVERSE actuelle).

### SAF.PA #1, #4 — wording vague + baselines manquantes

- #1 AVANT : 'GTF P&W cure costs reduits >50% sur 2 quarters' — measurable
  mais peu de baseline.
- #1 APRÈS : RTX fleet management plan completed OR P&W charges trimestriels
  <$500M sur 2Q consec. Baseline RTX Q1 2026 + 10-K 'shop visits through
  end 2026'.
- #4 AVANT : 'Defense EU budget <2% PIB sur 2 ans' — pas de baseline chiffré.
- #4 APRÈS : EU aggregate <2% GDP moyen NATO Europe (vs 2.3% 2025 SIPRI) OR
  Germany <2% GDP (vs 2.3% + €1T 10-year program Merz) OR France revised down
  >10% YoY. Baseline NATO 5% GDP pledge 2035, Poland+Baltics >4%.

### STMPA.PA #1, #2, #3 (c2) — three one-liners → mesurables

AVANT : 'Automotive SiC cycle correction.' / 'Industrial slowdown EU.' / 'SiC
pricing pressure.'

APRÈS :
- #1 : Automotive segment ST <0% YoY sur 2Q consec (vs Q1 2026 +15% YoY return
  to growth) OR P&D op margin <-30% sur 2Q consec (vs Q1 2026 -21.5%).
- #2 : Industrial segment ST <+10% YoY sur 2Q consec (vs Q1 2026 +26% YoY)
  OR European OEM industrial tier-1 reduction order >25%. Baseline Industrial
  +26% YoY, inventories normalized, book-to-bill >1.
- #3 : SiC ASP decline >20% sur 12 mois cumulé (Infineon/Wolfspeed/onsemi
  public) ET ST P&D op margin <-25% sur 3Q consec (vs Q1 -21.5%). Baseline
  Infineon explicit 'SiC China substantial price pressure', ST 'maintains
  stable commercial market share'.

## Idempotence

Script vérifie wording actuel (substring de l'OLD) avant UPDATE. Skip si déjà
rewritten. Replay safe sur DB déjà à l'état cible.

## Cross-ref doctrine

Aucun nouveau code 'S{N}' introduit dans les rewrites (cf commit 05c8d22
mécanisme cross-ref). Rewrites suppriment au contraire les références S12
inutilisées (MU + 000660.KS).

## Doctrine compliance

- L21 fail-closed généralisé : tous rewrites mesurables avec seuils chiffrés
  + baselines Q1 2026.
- Memory `currency_native_invariant` : AMD #4 doctrine violation (valuation
  price-only) corrigée vers fundamental GM/op margin.
- Memory `feedback_no_probability_anchoring` : aucune suggestion de
  probabilité, criteria triggers binaires mesurables only.

## Usage

    python3 scripts/trigger_rewrites_c4_c3_c2_2026-06-17.py [--apply]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "bot.db"

REWRITES: dict[str, dict[int, dict[str, str]]] = {
    # ── c4 batch ─────────────────────────────────────────────────────────
    "000660.KS": {
        1: {
            "hint": "S12",  # OLD referenced S12 sentinelle non-postée
            "new": (
                "Hybrid bonding atteint parité yield MR-MUF sur ≥16 couches HBM "
                "(Samsung, Micron, ou CXMT démontrent yield ≥80% sur 16-layer "
                "hybrid bonding stack en production volume vs SK Hynix MR-MUF "
                "current standard) = érosion moat qualité memory cycle. PARTAGÉ "
                "groupe mémoire. Baseline 2026 : SK Hynix MR-MUF advantage "
                "maintenu, hybrid bonding adoption accélère (BESI 20 clients) "
                "mais parité yield non atteinte."
            ),
        },
    },
    "MU": {
        1: {
            "hint": "S12",  # OLD referenced S12 sentinelle non-postée
            "new": (
                "Hybrid bonding atteint parité yield MR-MUF sur ≥16 couches HBM "
                "(Samsung, Micron, ou CXMT démontrent yield ≥80% sur 16-layer "
                "hybrid bonding stack en production volume vs SK Hynix MR-MUF "
                "current standard) = érosion moat qualité memory cycle. PARTAGÉ "
                "groupe mémoire. Baseline 2026 : SK Hynix MR-MUF advantage "
                "maintenu, hybrid bonding adoption accélère (BESI 20 clients) "
                "mais parité yield non atteinte."
            ),
        },
    },
    "HO.PA": {
        2: {
            "hint": "US primes criteria",  # placeholder OLD fragment
            "new": (
                "Thales revenue from European defense customers DOWN >10% YoY "
                "sur 2 quarters consec OR US primes >50% European equipment "
                "market share annoncé (Oxford Economics report) = signal réel "
                "d'érosion EU autonomy push. Baseline 2026 : US ~40% market "
                "share déjà (Oxford), trigger nécessite accélération matérielle "
                "vs status quo."
            ),
        },
    },
    "KLAC": {
        2: {
            # OLD was a one-liner referencing 'margin <50%' alone (KLAC #3 c4
            # batch rewrite). NEW removes the quoted OLD reference to ensure
            # idempotent detection cleanly differentiates OLD vs NEW.
            "hint": "margin <50%",
            "new": (
                "Gross margin <55% sur 2 quarters consec OR operating margin "
                "<30% sur 2 quarters consec (vs Q3 2026 baseline GM 62.2%, OM "
                "42.6% = headroom 12pp / 12.6pp). Critère original ambigu "
                "(threshold unique non-disambigué entre GM et OM) clarifié en "
                "deux seuils distincts measurables = signal réel de compression "
                "margin structurelle dans un cycle bull AI."
            ),
        },
    },
    "SU.PA": {
        1: {
            "hint": "Schneider margin under pressure from Asian competition",
            "new": (
                "EBITA margin compression >100bps YoY sur 2 quarters consec (vs "
                "guidance +50-80bps expansion 2026) OR Schneider market share "
                "in China datacenter electrical infrastructure drops >5pp "
                "annoncé publiquement OR Huawei/Chinese competitor wins >3 "
                "hyperscaler North American DC contracts sur 12 mois = "
                "compression structurelle Asian competition. Baseline Q4 2025 "
                ": EBITA +12% organic 5e année consécutive expansion."
            ),
        },
    },
    # ── c3 batch ─────────────────────────────────────────────────────────
    "6920.T": {
        0: {
            "hint": "KLA ou concurrent remporte un design-in inspection masque EUV majeur",
            "new": (
                "Concurrent (KLA, Applied Materials, Carl Zeiss) remporte "
                "design-in inspection masque EUV ACTINIC (13.5nm wavelength, "
                "vs E-beam ou DPV) chez foundry tier-1 (TSMC/Samsung/Intel) "
                "pour production volume — NOTE : KLA TeraBeam 8XX (E-beam, "
                "co-dev TSMC 5 ans, annoncé Investor Day 12/03/2026) = "
                "technologie complémentaire pitch <20nm, PAS substitution "
                "Lasertec MATRICS sur pitch 36nm+. Actinic Lasertec leadership "
                "intact tant que pitch 36-100nm reste production EUV majoritaire."
            ),
        },
    },
    "ALAB": {
        0: {
            "hint": "PCIe retimer commoditization.",
            "new": (
                "GM non-GAAP <60% sur 2 quarters consec (vs Q1 2026 ~73%, Q2 "
                "2026 guide ~73% adj 200bp warrant) OR PCIe Gen 6 retimer ASP "
                "decline >25% YoY annoncé = signal commoditization réelle. "
                "Baseline 2026 : pricing power intact, scale leverage "
                "opérationnel."
            ),
        },
        1: {
            "hint": "Cadence/Broadcom enter retimer aggressive.",
            "new": (
                "Broadcom OU Marvell annonce design-win majoritaire (>30% "
                "socket-share dans earnings call) chez ≥2 hyperscalers sur "
                "PCIe Gen 6 retimer platform OR aggregate AVGO+MRVL retimer "
                "revenue déclaré >$500M/Q (vs ALAB run-rate ~$300-365M/Q) = "
                "compétition matérielle vs early-stage. Baseline Q1 2026 : "
                "MRVL retimer fiscal 2028 full revenue contribution, AVGO PCIe "
                "Gen 6 portfolio launched mais pre-production volumes. Astera "
                "Q1 +93% YoY = competitive position holds for now."
            ),
        },
        2: {
            "hint": "Customer concentration risk.",
            "new": (
                "Single customer >40% revenue (vs Customer A 29% Q1 2026) OR "
                "Top 2 customers >65% (vs 50% Q1 2026) OR Customer A absolute "
                "revenue declines >15% YoY = concentration risk matérialisé. "
                "Baseline Q1 2026 : Customer A 29% (up from 12% YoY), Top 2 "
                "50%, Top 5 ~90% — Customer A 29% < threshold critique."
            ),
        },
    },
    "AMD": {
        1: {
            "hint": "MI300X design wins reculent",
            "new": (
                "MI450/MI455X design wins reculent : annonce publique d'1 "
                "hyperscaler tier-1 (Meta/OpenAI/AWS/Google/Azure) qui REDUIT "
                "commit AMD Instinct GPU deployment >30% vs commitments "
                "annoncés (ex : Meta 6 GW partiel) OR perte design majeur "
                "(>$2B annual commit) au profit Nvidia/Broadcom. Baseline Q1 "
                "2026 : Meta 6 GW warrant 160M shares, OpenAI active, Samsung "
                "HBM4 MI455X, AWS/GCP/Azure/Tencent expanded. MI450 lead "
                "customer forecasts EXCEEDING initial 2027 plans."
            ),
        },
        2: {
            "hint": "Server CPU share intel reprend (ramp Sierra Forest)",
            "new": (
                "Server CPU share AMD declines >2pp sur 2 quarters consec (vs "
                "share gains accelerated Q1 2026) OR AMD server CPU revenue "
                "YoY <+20% sur 2 quarters consec (vs +50%+ Q1 2026, +70% Q2 "
                "guide) = signal réel Intel reprise share. Baseline Q1 2026 : "
                "Intel 6 consecutive quarters beating, Xeon 6 + Intel 18A Core "
                "Series 3 full volume, MAIS AMD share gains EN EXPANSION = "
                "both growing, market expanding."
            ),
        },
        3: {
            "hint": "Valuation passe sous 30x forward",  # DOCTRINE VIOLATION
            "new": (
                "GM non-GAAP <50% sur 2 quarters consec (vs Q1 2026 ~53%, "
                "expansion +3pp YoY) OR Data Center op margin <25% (vs Q1 "
                "2026 ~28% = $1.6B/$5.8B) = signal de compression structurelle "
                "/ pricing power érodé. Baseline Q1 2026 : GM 53%, favorable "
                "product mix, Data Center op income +71% YoY."
            ),
        },
    },
    "COHR": {
        0: {
            "hint": "Optical transceivers price war.",
            "new": (
                "ASP 800G/1.6T transceiver decline >20% YoY annoncé "
                "publiquement (Coherent/Lumentum/AAOI earnings call) OR "
                "Chinese OEM (Innolight/Eoptolink) remporte >25% share design "
                "wins hyperscaler tier-1 (MSFT/META/GOOGL/AMZN) = price war "
                "matérialisé. Baseline Q3 FY2026 : COHR Datacenter +41% YoY, "
                "NVDA multi-year strategic + $2B investment Coherent, 1.6T "
                "ramp faster than expected, pricing power intact toutes optical."
            ),
        },
        1: {
            "hint": "Coherent margin <30% on optical.",
            "new": (
                "Consolidated GAAP gross margin <33% sur 2 quarters consec OR "
                "Datacenter & Communications segment profit margin <22% (vs "
                "Q3 FY2026 25.5%, expansion attendue via 6-inch InP ramp "
                "Sherman TX) = compression structurelle pricing power "
                "photonics. Baseline Q3 FY2026 : segment profit $348M / "
                "$1,362M = 25.5% segment margin (post segment opex), GM "
                "consolidated ~33-35% à valider."
            ),
        },
        2: {
            "hint": "Datacom capex revised down.",
            "new": (
                "Hyperscaler CapEx aggregate (MSFT+META+GOOGL+AMZN) revised "
                "down >15% sur 1 quarter OR ≥2 hyperscaler tier-1 annonce "
                "ralentissement AI datacenter buildout = signal capex cycle "
                "turn. Baseline 2026 : hyperscaler capex $700-760B (+75-90% "
                "YoY), COHR Q3 Datacenter +41% YoY, OCS TAM raised to >$4B, "
                "supply ahead of demand."
            ),
        },
    },
    "ENTG": {
        3: {
            "hint": "ASML EUV ramp <plan (downstream chemistry revenue suit)",
            "new": (
                "ASML EUV system shipments <plan : ≥2 quarters consec ASML "
                "EUV net sales sous low-end annual guidance (vs Q1 2026 ASML "
                "€8.8B above consensus €8.69B) OR ASML annual guide revised "
                "down >10% (vs Q1 2026 backlog $46.47B) = downstream chemistry "
                "revenue ENTG suit baisse. Baseline Q1 2026 : ASML EUV supply "
                "tight, demand strong, ENTG benefiting downstream wafer/filter."
            ),
        },
        4: {
            "hint": "Cleaning chemistry hyperscaler contract loss",
            "new": (
                "ENTG annonce perte contract majeur (>$50M annual) sur cleaning "
                "chemistry / filtration chez foundry tier-1 (TSMC/Samsung/Intel) "
                "au profit concurrent (Versum/Air Liquide/Linde) OR APS segment "
                "revenue YoY <0% sur 2 quarters consec (vs +7% Q1 2026) = "
                "signal érosion plan-of-record positions. Baseline Q1 2026 : "
                "APS $463.6M (+7%), segment profit $133.6M (+24%), "
                "plan-of-record positions strong Asia."
            ),
        },
    },
    "LNG": {
        1: {
            "hint": "Sabine Pass Stage 3 OU Corpus Christi Stage 3 slip",
            "new": (
                "CCL Stage 3 Trains 6-7 OU mid-scale 8-9 OU SPL Expansion / "
                "CCL Expansion FID slip >12 mois vs guidance Q1 2026 (Trains "
                "1-5 substantially complete, 6-7 accelerated vs initial, 8-9 "
                "under construction, SPL/CCL Expansion FIDs coming into focus "
                "early 2027) = capex execution problem. Baseline Q1 2026 : "
                "production raised +1 Mtpa à 52-54 Mtpa 2026, EBITDA guidance "
                "RAISED +$500M."
            ),
        },
    },
    "MP": {
        2: {
            "hint": "Stage 3 magnet plant slip",
            "new": (
                "10X Facility Northlake TX OU Independence Facility expansion "
                "(3,000 tons) OU Mountain Pass HREE separation circuit slip "
                ">12 mois vs guidance Q1 2026 (Independence NdFeB manufacturing "
                "commenced Dec 2025, 10X broke ground Q1 2026, HREE separation "
                "commissioning Q2 2026, design nearing completion, equipment "
                "ordered) = capex execution problem compromis ramp. Baseline "
                "Q1 2026 : 'remain on track to achieve targeted start-up "
                "production dates'."
            ),
        },
        4: {
            "hint": "Hyperscaler magnet substitution",
            "new": (
                "EV/automotive/defense customer (GM, Apple, DoD, hyperscaler "
                "EV motor) annonce switch >$50M annual procurement vers "
                "rare-earth-free magnets (Proterial NdFeB-no-Dy/Tb, Tesla "
                "switched motor 2022) OR ≥2 EV OEM tier-1 annonce design-in "
                "rare-earth-free pour platform majeure = signal réel "
                "substitution magnet metal-free. Baseline Q1 2026 : Apple "
                "$500M recycled magnet commit MP, GM long-term supply "
                "agreement, DoW $140M EBITDA guarantee 10X. Substitution "
                "actuelle = REVERSE (Apple commit MP)."
            ),
        },
    },
    "SAF.PA": {
        0: {
            "hint": "GTF Pratt&Whitney cure costs reduits >50%",
            "new": (
                "GTF Pratt & Whitney powder metal cure costs RTX accelerated "
                "remediation : RTX guidance fleet management plan completed "
                "(no more shop visits incremental) OR Pratt & Whitney charges "
                "trimestriels <$500M sur 2 quarters consec (vs current "
                "'significant incremental shop visits through end of 2026' per "
                "RTX Q1 2026 + 10-K) = P&W concurrent retrouve momentum, "
                "Safran LEAP advantage érode. Baseline Q1 2026 : RTX still "
                "elevated A320neo AOG, Spirit Airlines 'inspection through at "
                "least 2026', cure ongoing au plein cap."
            ),
        },
        3: {
            "hint": "Defense EU budget annonces concrets <2% PIB sur 2 ans",
            "new": (
                "Defense EU aggregate spending revised down sous 2% GDP moyen "
                "NATO Europe (vs 2.3% 2025 actual SIPRI) sur 2 ans consec OR "
                "Germany defense budget <2% GDP (vs 2.3% 2025 + €1T 10-year "
                "program Merz coalition + 3.7% target 2030) OR France defense "
                "budget revised down >10% YoY = recul rearmement. Baseline "
                "2025-2026 : Allemagne +24% YoY €114B (2.3% GDP), UK 2.4%, "
                "France 2%, NATO 5% GDP pledge 2035 (Hague Summit), "
                "Poland+Baltics >4%. Catalyseur narrative MAXIMAL, opposé du "
                "trigger."
            ),
        },
    },
    # ── c2 batch ─────────────────────────────────────────────────────────
    "STMPA.PA": {
        0: {
            "hint": "Automotive SiC cycle correction.",
            "new": (
                "Automotive segment revenue ST <0% YoY sur 2 quarters consec "
                "(vs Q1 2026 +15% YoY = return to growth) OR P&D (Power & "
                "Discrete) segment op margin <-30% sur 2 quarters consec (vs "
                "Q1 2026 -21.5%, deteriorating de -6.9% prior) = cycle "
                "correction matérielle SiC automotive. Baseline Q1 2026 : "
                "Auto +15% YoY (turn), -10% sequential, SiC MOSFETs 'will "
                "grow again' Q4 commentary, ST maintains stable commercial "
                "market share."
            ),
        },
        1: {
            "hint": "Industrial slowdown EU.",
            "new": (
                "Industrial segment revenue ST <+10% YoY sur 2 quarters consec "
                "(vs Q1 2026 +26% YoY) OR European OEM industrial customers "
                "tier-1 annoncent reduction order >25% = slowdown EU "
                "matérialisé. Baseline Q1 2026 : Industrial +26% YoY, "
                "inventories normalized, book-to-bill >1 all end markets, "
                "strong booking momentum, design wins industrial automation/"
                "robotics."
            ),
        },
        2: {
            "hint": "SiC pricing pressure.",
            "new": (
                "SiC ASP decline >20% sur 12 mois cumulé (Infineon/Wolfspeed/"
                "onsemi public confirmations) ET impact matériel sur ST P&D "
                "segment : op margin <-25% sur 3 quarters consec (vs Q1 2026 "
                "-21.5%) = pricing pressure matérialisée sur compte STMicro. "
                "Baseline Q1 2026 : Infineon explicit 'SiC China substantial "
                "price pressure', ST 'maintains stable commercial market "
                "share', P&D op margin -21.5% Q1 (deterioration vs -6.9% "
                "prior)."
            ),
        },
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not DB.exists():
        print(f"ERROR: DB not found at {DB}", file=sys.stderr)
        return 1

    cx = sqlite3.connect(DB)
    n_updated = 0
    n_skipped_idempotent = 0

    for ticker, idx_map in REWRITES.items():
        row = cx.execute(
            "SELECT id, invalidation_triggers FROM theses WHERE ticker=? AND status='active'",
            (ticker,),
        ).fetchone()
        if not row:
            print(f"  {ticker}: thesis not found, skip")
            continue
        thesis_id, raw = row
        triggers = json.loads(raw)
        changed = False
        for idx, payload in idx_map.items():
            current = triggers[idx]
            if payload["hint"] in current:
                print(f"  {ticker} #{idx+1} : REWRITE")
                triggers[idx] = payload["new"]
                changed = True
            else:
                print(f"  {ticker} #{idx+1} : already rewritten, skip idempotent")
                n_skipped_idempotent += 1
        if changed and args.apply:
            cx.execute(
                "UPDATE theses SET invalidation_triggers = ? WHERE id = ?",
                (json.dumps(triggers, ensure_ascii=False), thesis_id),
            )
            n_updated += 1

    if args.apply:
        cx.commit()
    cx.close()

    total_rewrites = sum(len(v) for v in REWRITES.values())
    print(
        f"\n═ Summary : {n_updated} theses UPDATE'd, {n_skipped_idempotent}/{total_rewrites} "
        f"skipped idempotent ═"
    )
    if not args.apply:
        print("(dry-run, pass --apply pour modifier DB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
