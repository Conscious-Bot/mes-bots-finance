# ADR 008 — Politique de concentration : AI_compute, pari concentré assumé

**Statut** : Accepted — 2026-05-25 (Day 15 suite)
**Décideur** : Olivier (principal). Le bot force la cohérence, le principal tranche le risque.

## Contexte

21 positions, ~€42,7K. Cluster AI_compute ≈ 67% (~14 positions). config.yaml spécifie des caps (position 5%, secteur 20%, narratif 30%) mais ils ne sont PAS enforced (risk engine non câblé). Réalité 67% >> plafond narratif 30%. Le vrai risque n'est pas single-name (ce que borne un cap de position) mais *factoriel* : un facteur dominant, 14 noms corrélés.

Question tranchée : ce 67% est-il un pari assumé ou une dérive ? → **Assumé.**

## Décision

1. **Pari concentré délibéré.** AI_compute est la thèse de plus haute conviction. La concentration est le mécanisme qui produit un track record différencié (Path 5/6) ; diversifier à 30%/narratif diluerait l'edge qu'on cherche à démontrer.

2. **Cap de position = ENTRÉE (cost basis), jamais valeur de marché.** Un cap MV forcerait à vendre les gagnants = biais #1, que le système existe pour combattre. L'appréciation au-delà du cap se gère par le stop asymétrique de la thèse, pas par un trim mécanique. `position_max_pct: 0.05` conservé, sémantique = poids à l'entrée.

3. **Plat, pas tiéré, jusqu'à validation Brier.** Tiérer sur conviction (c5=8%…) = amplifier des croyances non testées (track record pré-fix). Le tiering se mérite à la révision automne, post N≥30 résolues.

4. **Plafond narratif 30% → 75%, max dur.** Au-delà, trim discipliné même sur conviction. Garde-fou contre le biais #2 (ne pas vendre aux tops) qui pousserait le cluster vers 85%+ par inertie.

5. **Freins existants conservés, non relevés — mécanique précise (vérifiée).** Les gates drawdown portfolio sont des gardes *à l'entrée*, pas des sorties : `drawdown_reduce_pct: 0.08` réduit le sizing des nouveaux achats (premier gate, ~-€3,4K portfolio), `drawdown_stop_pct: 0.20` bloque les nouvelles positions (~-€8,5K). Aucun ne VEND, et les deux sont inertes jusqu'au câblage de `validate()`. La sortie réelle en drawdown cluster = stops asymétriques par thèse (alertés par price_monitor) → décision manuelle ; le bot alerte, ne trade pas. On ne relève aucun seuil pour consommer la tolérance : le frein qui agit tôt est une feature. **Parké (post-observation, behavior-affecting)** : un trim automatique déclenché par drawdown portfolio — seul mécanisme qui dé-risquerait le 67% sans dépendre de la discipline manuelle (que les biais corrompent).

6. **Queue acceptée yeux ouverts.** Scénario sévère (AI-capex/semis winter, corrélation intra-cluster → 1, noms -50/60% type NVDA-2022) : cluster ~-45/50% → ~-€13-14K, **-33% portfolio**. Accepté.

7. **Invalidation niveau-portefeuille** (sans quoi "assumé" = "marié") : réduire la concentration si — guidance capex hyperscalers révisée en baisse 2 trimestres consécutifs OU roll soutenu des prix HBM OU air-pocket demande sovereign-AI. Déclenche une revue de réduction, pas un hold automatique.

## Conséquences

- `config.yaml` : `narrative_max_pct` 0.30 → 0.75.
- `risk_engine.validate()` (câblage post-observation) : poids calculé sur **cost basis**, pas MV. Enforce 5% entrée + 75% narratif + drawdown gates.
- 6 positions over-cap : triage **entry-oversized (trim) vs appreciation (garde + stop)** via `/positions` + `/tiers`. Apply manuel.
- Watch biais #2 : alerter si cluster dérive >75%.
