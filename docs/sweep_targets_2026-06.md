# Sweep niveaux décidés juin 2026 — scorecard humain-décide

> Registre du sweep #133 conformément à [[L30]] LESSONS : *cible figée + cost roulant = mensonge en formation ; instrument révèle, humain décide, jamais auto-recompute*. **Scorecard, pas table de niveaux** : la valeur du registre dans 12 mois sera de pouvoir **scorer le ressenti** (delta_vs_consensus) contre la réalité — pour ça il faut tracer ce qu'on pariait contre la foule au moment de la décision, pas juste le niveau posé.

**Anti-piège #1** : ne pas auto-recompute (`target = cost × (1+x%)` = interp 1 banni nuit 09/06)
**Anti-piège #2** : ne pas calquer un pair stale (MP partiel mourant lui-même 10/06 → calquer MP→CCJ propage la staleness, validé empiriquement)
**Anti-piège #3** : la distribution observée ≠ le seuil (médiane morts -4.7%, mourants +1.1% = état actuel, pas où le seuil L30 doit être ; choix de politique normatif, anti-L16)

---

## Finding #1 (corrigé après vérification statut détention)

Cadrage initial "18 aveugles = 42% du book sans protection" **invalidé** par vérif `storage.get_position_by_ticker()` :

- **17 candidats watchlist (NON tenus)** : ASMI, ASP Isotopes, Advantest, Air Liquide, Atlas Copco, BWXT, Constellation, Ferrotec, GE Vernova, Harmonic Drive, MRVL, Prysmian, SNOW, Soitec, TER, VRT, ams OSRAM. `get_position_by_ticker → None` pour tous. **Hors sweep — zéro exposition, zéro risque drawdown, rien à protéger.** Définir stop/target sur un candidat = bonne hygiène pose-time (= remède L30 anticipé) pour quand l'entrée se fera, mais pas un feu maintenant.

- **1 position RÉELLEMENT tenue sans bande** : **SNPS**, `qty=8.027`, `status=open`, value ≈ 3 290 EUR (≈ 1-2% du book). Vrai cas "tenu sans plan de sortie ni protection". À traiter dans le sweep, mais cas isolé, pas un finding portefeuille-wide.

**Note classification** : `_blind_positions_panel()` à `dashboard/render.py:1633` confond actuellement "candidat watchlist (pas entré)" et "position tenue qui vole à l'aveugle" — deux catégories opposées sous une même étiquette. **Refinement de classification possible, basse priorité** (le label "aveugle" n'est juste que pour SNPS, pas pour les 17 candidats).

**Pattern d'erreur capté** (capture honnête pour méta-doctrine) : escalader un risque sur la prémisse "ces positions sont tenues" sans vérifier la prémisse = même classe d'erreur que présumer un prix marché de mémoire (cas SK Hynix 10/06 matin). **Verify-before-patch s'applique aussi aux faits marché/portefeuille, pas seulement au code.** À graver dans la méta-leçon de la session.

---

## Scorecard sweep targets

### Schéma de colonnes (lock 2026-06-10)

```
position | ccy | cost | cur | old_partial | old_full | edge_p | edge_f
       | consensus_ancre (range)
       | new_partial | new_full | new_stop
       | delta_vs_consensus (pourquoi tu pries plus haut/bas que la foule)
       | thèse_raison (le pourquoi du delta, en 1-2 lignes)
       | asof
```

Les colonnes **delta_vs_consensus + thèse_raison** sont LA scorabilité du registre. Sans elles : on saura où on a posé, pas ce qu'on pariait. Elles sont obligatoires par ligne.

### Convention

- `delta_vs_consensus` est exprimé en **% au-dessus/en-dessous de la médiane consensus** (ex. "+30% vs médiane 139.66 = pari supercycle plus fort que la foule")
- `thèse_raison` doit nommer le mécanisme (catalyseur, valuation re-rate, supercycle, etc.), pas répéter "j'y crois"
- Tout niveau posé doit passer **born-dead**, règles distinctes par type :
  - **Cibles** (partial, full) : > cost ET > cur (sinon déjà atteint à la pose)
  - **Stop** : **< cur toujours** (c'est un plancher de sortie). Trois formes valides :
    1. *Stop downside* : `stop < cost` — protection à la baisse classique
    2. *Stop protège-gain (trailing)* : `cost < stop < cur` — légitime quand cur a monté vs cost (ex. AMD cost 170, stop 396, cur 524)
    3. *Core compounder sans stop assumé* : pas de stop posé, **choix explicite tracé tel quel**, pas forcé
  - **Anti-pattern flag** : un "stop" ≥ cur n'est pas un stop. Refus de pose en born-dead-check.

---

## Worklist sweep targets (snapshot 2026-06-10, sweep full-book)

```
ticker    ccy           cost          cur   edge_p   edge_f  verdict
----------------------------------------------------------------------
000660.KS KRW     1868446.04   2077000.00    -8.5%    -0.4%  MORT
CCJ       USD         109.72       105.44    -7.4%    +0.8%  MORT
4063.T    JPY        7232.71      6615.00    -5.1%    +3.7%  MORT
AMZN      USD         258.96       245.22    -4.7%    +4.1%  MORT
AVGO      USD         427.73       396.60    -4.6%    +4.2%  MORT
KLAC      USD        1835.48      2108.06    -2.5%    +9.0%  MORT
7011.T    JPY        4108.96      3581.00    -2.3%    +9.2%  MORT
6857.T    JPY       26616.16     25440.00    -1.7%    +4.6%  MORT
6920.T    JPY       39657.52     41390.00    +0.1%   +11.9%  mourant
TSLA      USD         414.33       408.95    +1.1%   +13.1%  mourant
LNG       USD         230.89       236.61    +1.1%   +10.1%  mourant
MP        USD          60.78        57.58    +2.8%   +11.9%  mourant
```

13 vifs hors scope (ne pas toucher).

---

## Décisions (scorecard)

### 000660.KS (SK Hynix) — KRW — ✅ POSÉ 2026-06-10

| | |
|---|---|
| **cost** | 1 868 446 KRW |
| **cur** | 2 077 000 KRW |
| **old_partial / edge_p** | 1 709 060 / -8.5% (mort) |
| **old_full / edge_f** | 1 860 304 / -0.4% (mort) |
| **old_stop** | 1 285 576 (entry × 0.85, -15% vs entry) |
| **consensus_ancre** | médiane ~2.3M (range 2.0-2.5M, 38 analystes) ; bull post-HBM upgrade : SK Sec 3.0M, KB/KoreaInv/Mirae/Shinhan 3.8M ; high-max 4.0M ; ATH récent 02/06 = 2.407M ; fwd P/E 5.3-5.8× |
| **new_partial** | **2 650 000 KRW** (+41.8% vs cost, +27.6% vs cur — vif) |
| **new_full** | **3 800 000 KRW** (+103% vs cost, +83% vs cur — pile sur bull brokers KB/KoreaInv/Mirae/Shinhan) |
| **new_stop** | **1 209 954 KRW** (entry × 0.80, -20% vs entry, -35.3% vs cost — élargissement assumé explicitement par Olivier ; born-dead ✓ < cur) |
| **delta_vs_consensus_partial** | **+15.2%** vs médiane partial-zone consensus (~2.3M) — partial atteignable mais plus exigeant que la foule |
| **delta_vs_consensus_full** | **+47.6%** vs consensus moyen #2 (2.575M) ; **+0%** vs bull brokers 3.8M (alignement exact) — pari : la vague d'upgrades post-HBM gen5 délivre |
| **thèse_du_delta** | *(formulée par Claude depuis contexte conv, à valider/réviser par Olivier)* HBM gen5 leader incontesté ; capacité 2026 déjà vendue, share AI mémoire 70-80% ; multiple compressed fwd P/E 5-6× = re-rate possible si earnings power délivre ; full ancrée sur bull brokers (3.8M) plutôt que consensus moyen, sans aller jusqu'au high-max 4.0M (single analyst). |
| **asof** | 2026-06-10 |
| **DB write** | `UPDATE theses SET target_partial=2650000, target_full=3800000, stop_price=1209954 WHERE rowid=28` — exécuté, rowid 21 (doublon fantôme) intacte. |

### CCJ (Cameco) — USD — MORT (partial -7.4%, full +0.8%)

| | |
|---|---|
| **cost** | 109.72 USD |
| **cur** | 105.44 USD |
| **old_partial / edge_p** | 101.56 / -7.4% |
| **old_full / edge_f** | 110.55 / +0.8% |
| **consensus_ancre** | médianes 137.86-148.62 USD (range 82.60-174.98) ; bull Scotiabank 175 (mai 2026) ; NAV/action 66 ; EV/EBITDA 37× (élevé) ; revenue CAGR +8%, EBITDA CAGR +12% (2025-28) ; 70+ réacteurs en construction |
| **calque MP** | **BANNI** — MP partial lui-même mourant 10/06 (cas canonique L30 "pair stale propage la staleness") |
| **new_partial** | *(à poser)* |
| **new_full** | *(à poser)* |
| **new_stop** | *(à poser, conserver, OU marquer explicitement "core compounder sans stop assumé")* |
| **delta_vs_consensus_partial** | *(claim falsifiable : "+X% / -X% vs consensus médian")* |
| **delta_vs_consensus_full** | *(claim falsifiable)* |
| **thèse_du_delta** | *(pourquoi ta vue diverge de la foule, 1 ligne — mécanisme nommé : supercycle uranium long, catalyseur réacteurs, etc.)* |
| **asof** | 2026-06-10 |

### Positions en attente d'ancres externes (batch à venir)

10 lignes à traiter : 4063.T, AMZN, AVGO, KLAC, 7011.T, 6857.T (morts) ; 6920.T, TSLA, LNG, MP (mourants).

Batch les **morts d'abord** (urgents) puis les **mourants** ensuite, conformément séquence Olivier.

### Cas mineur séparé : SNPS (Synopsys) — USD — tenu sans bande

| | |
|---|---|
| **statut** | RÉELLEMENT tenu (qty 8.027, status open, id 9) |
| **value approximative** | ~3 290 EUR (≈ 1-2% du book) |
| **stop / partial / full** | None / None / None — sans plan de sortie ni protection |
| **cur** | 473.48 USD |
| **fx** | 0.8657 |
| **action** | À traiter dans le sweep avec SK+CCJ ou après — petit en valeur absolue, mais c'est un vrai cas "tenu qui vole à l'aveugle". |
| **note classification** | Seule position où le label "aveugle" du `_blind_positions_panel()` est sémantiquement juste (vs 17 candidats watchlist qui sont juste hors-portefeuille). |

---

## Doctrine en chantier (à graver dans L30 expansion post-sweep)

### Mécanisme L30 (acquis)

Cible figée + cost roulant (renforts + FX) → mensonge silencieux. Le partial est juste le canari. **Instrument révèle, humain décide, jamais auto-recompute.**

### Élargissements 10/06

1. **Partial vs full = deux fonctions distinctes** — partial = échelle de prise atteignable (zone consensus-haut), full = bull case thesis complet (zone bull-max). Cadrages différents.
2. **Stop figé vs cost roulant** = même mécanisme L30 (corollaire). Stop pré-rally peut devenir absurdement bas (ne protège plus rien) ou trop proche du cur (déclenche au bruit). À réviser en même temps que les targets — ratio R/R cohérent post-révision.
3. **Échantillonner par cause, pas par symptôme visible** — partir des thèmes en rally, pas du panneau asym closest-to-target (qui ne montre que la sous-population déjà visible). Le sweep full-book a sorti 12 positions stale, pas les 8 du panneau.
4. **Ne pas calquer sur un pair stale** — MP candidat calque pour CCJ, mais MP lui-même mourant 10/06. Le calque propagerait littéralement la staleness. **Cas canonique L30 à citer comme exemple empirique.** Ancrer sur fair-value externe, pas sur un autre pair non-vérifié.
5. **Séparation 3 colonnes anti-biais** — ressenti seul = re-pose au feeling (bug d'origine) ; ancre seule = ignore la thèse propre (calque MP→CCJ) ; les deux ensemble + scorecard delta = juste ET scorable.
6. **Seuil L30 = choix de politique, pas stat sur N** — la distribution observée (médiane morts -4.7%, mourants +1.1%) décrit le désordre actuel, pas où le seuil doit être. À écrire dans L30 comme normatif provisoire, anti-glissement vers "seuil = 0%".

### Doctrine élargie au cas "absence de niveau" (manifesté SNPS)

L'absence de niveau décidé est un cas-limite de L30 : un niveau absent ne ment pas, mais **il ne protège ni ne signale rien non plus**. La gauge degraded l'affiche fidèlement (KNOWN-GAP §4 SPEC_GAUGE). **Cas isolé** sur le book (SNPS uniquement, ~1-2% de valeur) — pas un finding structurel comme initialement craint. Mais la classification doit distinguer "absence sur position tenue" (vrai cas) vs "absence sur candidat watchlist" (normal, pas en jeu).

### Méta-leçon de la session (à graver dans L30 expansion ou LESSONS dédiée)

**Verify-before-patch s'applique aux faits marché/portefeuille, pas seulement au code.** Pattern d'erreur observé deux fois en une session :
1. SK Hynix matin — magnitude prix présumée de mémoire (~100-150 Md$) sans cherche live, conclusion "cost corrompu" fausse (la boîte est dans le club trillion en 2026).
2. 18 "aveugles" — détention présumée sans vérification, escalade à "42% du book sans protection" alors que 17/18 sont des candidats non-entrés.

**Pattern** : fiabilité haute en lecture d'artefact (bug tests, drift §5, schéma registre), dérive sur supposition d'un fait externe (prix marché, statut détention). **Remède** : cherche le prix, demande "tenue ?", lis l'artefact source — n'escalade pas sur une prémisse non vérifiée. L'humain (Olivier) et l'instrument (moi) sont sujets au même piège : il y a un parallèle direct avec la doctrine anti-fabrication L16/L19. La méta-leçon est unifiée — *toute affirmation à enjeu (technique ou marché) doit citer son artefact-source, pas s'appuyer sur la mémoire ou la supposition*.

---

## Méta-méthode (acté)

- **Feed consensus systématique** — à terme via skills lseg:research-equity / daloopa / bigdata plutôt que WebSearch ad-hoc (qui ne scale pas à 12+ positions, et plus encore au book entier). Pour ce sweep N=12 WebSearch reste OK ; pour le chantier #135 (refonte complète) feed structuré requis.
- **Born-dead check obligatoire** par ligne avant écriture DB.
- **Trace asof + raison** — sans ces deux, la révision est silencieuse et non-auditable.
- **Atomique** — chaque ligne validée écrite en transaction unique, registre + DB mis à jour ensemble.

---

*Document évolutif. Une ligne validée et écrite en DB n'est pas effaçable ; les révisions ultérieures ajoutent un nouvel entry avec asof distinct.*
