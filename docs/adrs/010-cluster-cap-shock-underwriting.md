# ADR 010 — Cap cluster = 35% (risk-adjusted via choc underwrité), config aligné

**Date**: 2026-05-26
**Status**: Accepted — **paramètre superseded par [`015-concentration-assumed-deep-defense`](015-concentration-assumed-deep-defense.md) (28/06/2026)** ; méthode (cap dérivé d'un underwriting de choc) conservée. Le cap opératoire est passé à 70% sous choc honnête 57% (drawdown ~−40% assumé) + système de digues. La présente ADR reste la trace de la dérivation 35%.
**Résout**: la contradiction 35-vs-57 (SESSION_STATE suite-4).
**Reaffirme**: `008-cluster-cap-grandfather` (35% liant, position 5% soft, grandfather strict).
**Supersede**: config Day-14 `cluster_max_pct: 0.57` (choc underwrité trop bénin).

## Contexte
Deux caps cluster se réclamaient "source de vérité" :
- config Day-14 (`df89dc8`) : `0.57`, dérivé `cap × choc ≤ stop` avec choc **0.35** → 0.57×0.35 = 0.1995 < 0.20.
- ADR-008-cluster-cap + code (`positions.py CLUSTER_CAP_PCT=35.0`) : **35%**.

Même formule, hypothèse de choc différente. La vraie variable de décision = **le choc cluster qu'on underwrite**.

## Décision
Cap cluster liant = **35%**. Choc underwrité = **≥57%** — le tail honnête d'un cluster AI_compute corrélé (chokepoints même chaîne semi, beta>1 ; un AI-capex-winter fait -50%+, pas -35%). Posture **risk-adjusted** : dimensionner pour le tail.

Formule gravée, choc explicite et révisable :
`cluster_max_pct × choc_underwrité ≤ drawdown_stop`  →  `0.35 × 0.57 ≈ 0.1995 ≤ 0.20` ✓

57 rejeté : il underwrite un choc 35% qui sous-price la corrélation. À un choc réel 50%, 0.57×0.50 = 0.285 ≫ 0.20 = stop explosé. 35 survit à un choc 57% **sous** le stop.

## Alignement
- code : déjà 35, aucun changement.
- config : `cluster_max_pct 0.57 → 0.35`, `assumed_cluster_shock 0.35 → 0.57` (produit ≈ stop, choc honnête).
- ADR-008-cluster-cap : 35% confirmé, **rationale upgradée** (comportemental → risk-adjusted, défendable en audit Path 5/6).

## Conséquences
- Un seul cap cluster cohérent partout : 35%.
- Inerte au runtime (config lue par `risk.validate()` non câblé ; `/portfolio` lit le 35 hardcodé) → sûr pendant l'observation.
- Révisable : si la corrélation/beta du cluster baisse, ré-underwrite le choc → re-dérive le cap.
- Revue : trigger J+28 d'ADR-008-cluster-cap (10 juin, trim forcé si cluster >50%).

## Hors scope (à froid)
`/portfolio` affiche "max sizing 8%" vs ADR-008 "5% soft" — divergence position-cap distincte, non traitée ici.
