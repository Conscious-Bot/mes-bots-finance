# ADR 007 — Crédibilité source : autorité unique Brier

Status: Accepted — 25 May 2026

## Contexte
Deux writers sur `sources.credibility`, objectifs divergents :
- Immédiat/résolution (learning.py): `update_source_credibility(delta)`, OUTCOME_DELTA catégoriel +0.03/−0.05/0 — hitrate, relatif, tire dès la 1ère résolution, pas de gate.
- Mensuel (storage.recalibrate_source_credibility_from_hitrate, min_n=10): recompute absolu depuis AVG(brier).
Le mensuel écrase la dérive de l'immédiat ; les deux n'optimisent pas la même chose (hitrate vs Brier) → sawtooth + incohérence sémantique.

## Décision
Le Brier est l'autorité unique. On supprime l'**application** du writer incrémental catégoriel. Crédibilité = recompute mensuel Brier (min_n=10).
- `credibility_delta` reste calculé et stocké sur la ligne prediction (audit, post_mortem) — on cesse seulement de l'appliquer à `sources`.
- Coût accepté : slow-first-light (crédibilité à 0.5 jusqu'à 10 résolues-Brier/source). Honnête : pas d'évidence = poids neutre. Le prior précoce est porté par le terme score recentré (commit 89a43e0), pas par la crédibilité.

## Rationale
- On-thesis : le produit est la calibration Brier, pas le hitrate. Une crédibilité hitrate-based pollue le prior.
- Moins de pièces mobiles (un writer en moins).
- Élimine le sawtooth-overwrite et le conflit d'objectif.

## Alternative notée (futur, non requis)
Rendre l'incrémental Brier-proportionnel (`delta = f(brier de cette prédiction)`) et démettre le mensuel en audit → signal crédibilité plus rapide, même objectif. Reporté tant que le terme score porte le prior précoce.
