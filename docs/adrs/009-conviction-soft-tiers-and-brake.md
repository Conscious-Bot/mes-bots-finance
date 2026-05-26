# ADR 009 — Alertes soft tiérées par conviction + mécanique du frein (subordonné au cap cluster d'ADR 008)

**Date**: 2026-05-26
**Status**: Accepted
**Parent**: `008-cluster-cap-grandfather.md` — l'invariant de concentration qui LIE (cap cluster 35% hard, cap position 5% soft, grandfather strict). Cet ADR raffine la couche SOFT et clarifie le frein ; il **ne change pas** l'invariant liant.

## Contexte
Session 26/05 : sizing re-discuté à l'aveugle (readout `/portfolio` cassé par 2 instances zombies + mauvais noms de commande). Un ADR 008 doublon (`008-concentration-policy.md`) avait été créé, contredisant le cap-cluster (il faisait du cap position tiéré l'invariant liant, alors qu'ADR 008 a précisément rétrogradé le cap position en soft et fait du cluster l'invariant). Doublon retiré. Ce qui suit survit, recadré sous l'invariant cluster.

## Décision

### 1. Cap position SOFT tiéré par conviction (alerte, NON liant)
Le cap position reste soft (ADR 008 §2). On le tiére comme seuils d'**alerte** :

| tier | seuil d'alerte (cost-basis) |
|---|---|
| c5 | 8% |
| c4 | 6% |
| c3 | 5% |
| c2 | 4% |
| c1 | 3% |

- Gate de nombre : ≤20% des lignes en c5 (conviction ordinale — KPI inflation).
- **Non liant** : l'invariant qui lie reste le cap cluster 35% (ADR 008). Ceci ne fait que tiérer le signal visuel.
- Tiers auto-assignés, validés par Brier à N≥30 (re-tiérage sur preuve).
- Si ce cap tiéré devait un jour devenir *liant*, c'est une ré-ouverture de la décision centrale d'ADR 008 (cluster = invariant) — à faire explicitement, pas ici.

### 2. Clarification mécanique du frein (vérifiée)
- Les gates drawdown portfolio (`reduce 0.08`, `stop 0.20`) sont des gardes **à l'entrée**, ne vendent rien, et sont **inerts** jusqu'au câblage de `risk.validate()`.
- Sortie réelle en drawdown = stops par thèse (alerte price_monitor) → décision manuelle. Pas de trim auto sur drawdown portfolio (mécaniserait le biais #1).
- Caveat corrélation : les noms du tier haut (ASML, TSM, Shin-Etsu, SK Hynix, Synopsys, Advantest, Lasertec, BESI) sont des chokepoints de la même chaîne semi → corrélés. Affine le « cluster moves as one » d'ADR 008.

## Conséquences
- Remplace le doublon retiré `008-concentration-policy.md`.
- Timing de revue : gouverné par le trigger d'ADR 008 (J+28 = 10 juin, trim forcé si cluster >50%). Pas de cadence séparée.
- `narrative_max_pct` remis à 0.30 (bump 0.75 = mauvais axe).
- POLICY, pas enforcement : `risk.validate()` non câblé.

## Dette de cohérence (audit à froid, préexistant — pas de cette session)
- config `cluster_max_pct: 0.57` (dérivé risk-budget) vs ADR 008/code `35%` (comportemental) — deux caps cluster divergents.
- `/portfolio` affiche « max sizing 8% » vs ADR 008 §2 « 5% soft ».
- Numérotation ADR : collisions 005×2 / 006×3 / 007×3 / 008×3 — passe de renumérotation à prévoir.
