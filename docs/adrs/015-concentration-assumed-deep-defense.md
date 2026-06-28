---
type: adr
id: 015
amends: 010-cluster-cap-shock-underwriting
supersedes: "ADR 010 — paramètre cap 35% (méthode underwriting conservée)"
title: Gouvernance de la concentration — PF AI assumé, digues graduées, réconciliation cap→choc→stop
status: Accepted
date: 2026-06-28
relates: [008, 009, 010-cluster-cap-shock-underwriting]
---

# ADR 015 — Concentration assumée + défense en profondeur

## Statut
Accepted (2026-06-28). Supersède le *paramètre* d'ADR 010 (cap 35%) ; en **conserve la méthode**
(cap dérivé d'un underwriting de choc). Amende la chaîne cap→choc→stop. Ne touche pas ADR 009
(caps de conviction par ligne, étage séparé).

## Contexte — le fork à réparer (faits vérifiés dans le code, 2026-06-28)
1. **Le cap 35% n'est PAS un artefact.** Il existe, est wiré (`config.yaml:436`, `calibration.yaml:251`,
   consommé `portfolio_analytics.py:381`), et dérivé rigoureusement par ADR 010 (26/05) :
   `cap × choc ≤ stop` → `0.35 × 0.57 ≈ 0.1995 ≤ 0.20`. Le choc supposé y est **57%**
   (hypothèse explicite : « un AI-capex-winter fait −50%+ »).
2. **La transition 35%→70% a cassé la chaîne en silence.** Le cap opératoire réel est 70%
   (`concentrator_thematic` / `user_cluster_target_pct`, 24/06). La note `config.yaml:414-418` (29/05)
   l'a raisonnée — mais sur un choc de **30%** : `0.70 × 0.30 = 0.21`. Or `0.70 × 0.57 = 0.40`.
   **Le 70% n'est cohérent que sous un choc 30% qu'ADR 010 avait explicitement réfuté.** Aucune
   des deux ADR ne le voit.
3. **Le stop 0.20 est inerte.** `risk.drawdown_stop_pct: 0.2` (`config.yaml:372`) n'a qu'un consommateur,
   `risk_engine.validate`, désactivé (`config.yaml:377` `validate_enabled: false`) — et qui checke le
   drawdown *portfolio*, pas le *cluster*. Le stop est cosmétique.
4. **Rien n'auto-vend.** STRESS→55% (`portfolio_grade.py:848`) cappe la note-lettre du dashboard,
   ne touche aucune position. kill_switch (P1 26/06) = reco Telegram en exécution manuelle
   (`cmd_kill_exec` → `/kill_exec`, `bot/registry.py:142`), avec une reco de trim *sélective*. Le
   système de risk de concentration est donc, à ce jour, **advisory ou débranché** sur presque tous
   ses organes.

## Décision

### 1. Concentration assumée, pas de cible de concentration
PF AI revendiqué. Aucune cible/plafond sur la masse AI qui *ordonnerait* un rééquilibrage.
Rationale : une cible-% est une machine à déclencher le biais #1 (vendre des winners pour rentrer
dans la cible faute de capital frais). Le cap 70% est **mou** (flag + justification consciente),
conforme au code actuel (validate off, grade-cap only). STRESS→55% conservé tel quel (cappe le
grade, ne vend pas).

### 2. Réconciliation cap→choc→stop : choc honnête 57% assumé
On retient le choc **57%** d'ADR 010 (le pessimiste honnête), PAS le 30% glissé en douce.
Conséquence assumée : cap 70% ⇒ **drawdown cluster théorique ~−40%** en choc sévère, supérieur aux
−21% au dossier. On **assume cette tolérance** plutôt que de redescendre le cap (qui forcerait une
déconcentration = biais #1). `risk.drawdown_stop_pct: 0.2` est **relabellisé non-liant** (il l'est
déjà de fait) : conservé comme mesure-miroir affichée, retiré comme déclencheur. Le garde-fou réel
n'est plus un stop *ex-ante* sur le cap, mais le **système de digues** ci-dessous.

### 3. Défense en profondeur — deux digues sur drawdown RÉALISÉ
Signal de déclenchement = **drawdown réalisé du book** (équity vs plus-haut = fait objectif),
**JAMAIS `classify_regime`** (capteur à faux positifs, ex. faux STRESS sur usd/jpy). Le bot ne trade
pas : les deux digues sont gate + reco, exécution manuelle.

- **Digue 1 — pause + revue (comportementale), seuil −15% réalisé.**
  Gèle les commandes d'ajout/renfort (`/position_buy` refusé). Ne vend RIEN. Impose un protocole
  de revue à compléter avant déblocage : relire chaque thèse du cluster, état des sentinelles S4/S5,
  métrique d'inflation de conviction, constat de régime. **Cooldown incompressible** : déblocage
  conditionné à l'écoulement d'un délai fixe OU à la complétion du protocole — jamais à un simple
  clic. Cible : intercepter les corrections cycliques normales, là où les biais #1 (capituler) et #2
  (moyenner à la baisse) sont le vrai risque.

- **Digue 2 — prorata ponctuel (capital), sur le kill_switch existant.**
  Requalifie la reco du kill_switch de *sélective* (« plus-corrélées / plus-basse-conviction d'abord »)
  en **prorata uniforme** : dégagement ponctuel d'un **ratio fixe de 20%** sur **chaque ligne du
  cluster `compute_ai`** (`:381`), sans sélection, cash levé en réserve. Reste en exécution manuelle
  (`cmd_kill_exec`), bot calcule le prorata exact. Rationale : si réduction il y a, qu'elle soit
  non-discrétionnaire — pour que le biais #1 ne reprenne pas la main via le choix de *quel* winner
  couper. Ratio fixe (pas cible-%) pour ne pas réintroduire une cible de concentration par la digue 2.

  **Articulation aux seuils existants (vérifié `config.yaml:830-832`)** : le kill_switch a déjà
  Stage 1 = **−25% gel / VIGILANCE** et Stage 2 = **−35% trim partiel / DÉ-RISQUE** (Stage 3 par prix
  désactivé). La digue 2 **requalifie le trim de Stage 2 (−35%) de sélectif en prorata 20%**. Le gel
  de Stage 1 (−25%) fait doublon conceptuel avec la digue 1 (−15%) et sera **réconcilié au chantier
  d'implémentation** (un seul gel gradué, pas deux seuils de gel redondants). Le palier −35% peut en
  outre armer un mode `paper_only` via `PROCEDURE_URGENCE`. Le mapping exact seuil→action est un point
  d'implémentation explicite, pas un acquis.

### 4. Définition de cluster — une seule, alignée sur le code
Toutes les mesures (cap 70%, STRESS 55%, prorata, plancher ballast) portent sur
`concentration.clusters.compute_ai` (`:381`, ~73%), PAS sur le champ `driver` taxonomy (~78-82%).
Interdiction de créer une 2e définition (= fork PnL rejoué). Si une décomposition lisible
(cat. driver 1/2/3) est affichée, elle doit **sommer à compute_ai**, sinon elle ne le décompose pas.

### 5. Plancher de ballast décorrélé — inchangé, conservé
`decorrelators` (`user_decorrelation_target_pct`) ≥ **15%** de la NAV, mesuré sur l'agrégat
(déjà calculé, ~17% aujourd'hui → respecté). Flag non bloquant si < 15% → ajout par capital frais,
JAMAIS par cession de cluster.

### 6. Sizing par ligne — inchangé (ADR 009)
Caps de conviction (c5=8% … c1=2%) intacts. Étage séparé de la gouvernance globale.

## Conséquences
- Implémentation : digue 1 (gate `/position_buy` + protocole + cooldown incompressible) ;
  digue 2 (prorata 20% pré-calculé sur compute_ai, reco `cmd_kill_exec`) ; signal = drawdown réalisé.
- `drawdown_stop_pct: 0.2` → commenté non-liant / déplacé en mesure-miroir.
- Dashboard : afficher drawdown réalisé vs seuils digues (−15% / −25% / −35%) ; cap 70% en flag.
- Taxonomie : Safran = aéro civil (pas défense) ; Prysmian = électrification (pas décorrélateur).

## Limites (ce que 015 NE fait PAS — honnêteté)
- **Les digues protègent contre un drawdown PROGRESSIF, pas un gap instantané.** Un krach overnight
  qui saute directement à −40% ne laisse pas le temps aux paliers de s'armer. Les digues sont
  efficaces sur un AI-winter qui se développe sur semaines/mois (cas le plus courant), pas sur un choc
  gap.
- **Le prorata est procyclique.** À −35% réalisé, il vend dans la baisse → sur un V-shape (fréquent
  sur corrections AI) il réalise près du creux et rate une partie du rebond. C'est le prix assumé d'un
  vrai frein de capital. Le mode prorata supprime le défaut *discrétionnaire* (choix de quel winner),
  pas le coût procyclique.
- **Drawdown −40% théorique pleinement assumé.** Aucun mécanisme ne le borne *ex-ante* ; seules les
  digues en amortissent la trajectoire. C'est la cohérence ultime d'un PF de conviction — mais c'est
  un choix conscient, pas une protection.
- Les % (73 / 82 / 40 / −21) sont des estimations datées, pas des constantes ; le drawdown théorique
  se recalcule depuis `cap × choc`. Leur justesse dépend de la déf compute_ai et de l'hypothèse de
  choc (jugements révisables).

## Invalidation / déclencheurs de RÉVISION (≠ ordre d'exécution)
- Ballast < 15% → ajout par capital frais.
- Une ligne > son cap de conviction → rightsize cette ligne (ADR 009).
- Rupture structurelle AI : les 4 hyperscalers (baromètre avancé) coupent le capex 2 trimestres
  consécutifs ; sentinelles S4/S5.
- Si un vrai épisode de stress survient : revoir l'hypothèse de choc (57%) et les seuils de digues
  à la lumière du drawdown réellement observé. « Réviser l'ADR » = décision réflexive, jamais un
  auto-trade.
