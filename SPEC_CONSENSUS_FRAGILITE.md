# Spec — Projection micro (consensus) + lentille de fragilité

> La seconde projection du cornerstone (cf `SPEC_CORNERSTONE`). Hérite de `CALIBRATION_DOCTRINE`, `PLAN_REFONTE_ALERTES`. **Point central : la projection micro a une situation statistique OPPOSÉE à la macro — et donc une stratégie de calibration opposée.**

## 0. L'asymétrie de N qui change tout (à lire avant tout)

Les deux projections du même moteur sont dans des mondes statistiques inverses :

| | Macro (cycle / crisis gauge) | **Micro (consensus)** |
|---|---|---|
| Structure | série temporelle | **panel cross-sectionnel** |
| N effectif | ~10-15 épisodes (starved) | **centaines de noms × années (riche)** |
| Calibration | **falsifier**, pas confirmer ; borrow-from-breadth | **calibration réelle** : IC, PR-AUC, vraie matrice de confusion |
| Inputs | indicateurs macro composites | **facteurs connus** (crowding, révisions, short) — décennies de littérature |
| Validation | prior faiblement validé, bandes larges | **proprement validable, track-record qui s'accumule vite** |

Conséquences directes :
1. **Le consensus est là où le projet peut avoir une validation statistique FORTE.** Contrairement à la crisis gauge, tu as la puissance.
2. Les inputs micro sont des **facteurs documentés** (positionnement/crowding, earnings-revision momentum, short interest) → **signes et priors empruntés à la recherche**, pas devinés.
3. **La fragilité (cycle × consensus) hérite de la confiance la PLUS FAIBLE des deux** — le marginal micro est fort, le conditionnement-cycle est un prior faible (N-starved sur la phase). La présentation doit refléter cette différence de confiance, jamais la masquer.

## 1. La primitive micro

```
D_micro = (croyance pricée : multiple + crowding) − (réalité livrable : révisions + momentum drivers)
Φ_micro = delta de crowding (accélère→renforce / ralentit→épuise) + divergence prix-croyance
```

Inputs (taxonomie, tier, signe figé, contrainte data) :

| Bucket | Input | Tier | Signe | Data |
|---|---|---|---|---|
| Croyance pricée | Crowding passif (% float en SMH/SOXX/QQQ) | **S** | ↑ → étiré | holdings ETF (fiddly, free) |
| | Borrow fee | A | élevé → short crowdé | **data-constrained** (proxy via SI+utilisation en v0) |
| | Multiple vs propre historique | B | élevé → étiré | **free** (financials) |
| | Dispersion analystes | B | serré+bullish → crowdé | yfinance partiel |
| Réalité livrable | Largeur révisions BPA (nom) | **S** | roule → divergence | **data-constrained** (clean = payant ; direction grossière free) |
| | Momentum drivers de thèse | A | dégrade → divergence | lit le moteur d'érosion (déjà spécifié) |
| Phase réflexive | **Delta** de crowding | **S** | — | dérivé (besoin de `consensus_snapshots` append-only) |
| | Divergence prix-vs-croyance | A | prix ne confirme plus → bascule | free |
| **Rejets** | sentiment social, Trends, gamma, SI brut | — | — | bruit / tactique |

## 2. La calibration micro — la VRAIE (N-riche)

- **Outcome = return RELATIF forward** (le nom vs son secteur/facteur) sur H. Cross-sectionnel : « crowding élevé + révisions qui roulent → sous-performe le facteur sur 3M ? »
- **Métriques factor-world** : **IC** (information coefficient — corrélation rank entre score et return forward), **PR-AUC**, **matrice de confusion** sur le panel. Là tu as la puissance, contrairement à la macro.
- **Purged walk-forward cross-sectionnel** : purge sur le chevauchement de label, embargo. Cross-sectionnel mais l'anti-look-ahead temporel tient (L16).
- **Le but n'est PAS de harvester de l'alpha** — c'est d'identifier **où TU n'as pas d'edge** (consensus = tu es avec la foule) et **où la fragilité est haute**. Discipline, pas signal de trade. (Garde la douve réglementaire : process, pas reco.)
- **Baselines à battre** : équipondéré, et le **single-best-factor** (« juste les révisions BPA » — le facteur le plus robuste de la littérature). Si le cocktail ne le bat pas OOS → fallback.

## 3. La lentille de fragilité (cycle × consensus)

- Interaction = **re-pricing multiplicatif** : le crowding micro est plus dangereux quand le cycle macro est late/divergent. `Fragilité = |D_micro| × amplificateur(phase macro) × fragilité-réflexive`.
- **Calibration de l'interaction** : le « coin danger » (late × crowded) prédit-il une *pire asymétrie forward* que chaque marginal seul ? (interaction term dans le modèle relatif).
- **Honnêteté obligatoire** : le marginal micro est fort (N-riche, validable) ; le conditionnement-cycle est **N-starved** (dépend de la phase, rare). Donc la fragilité = **micro solide × cycle faiblement-prioré**, et la confiance affichée de la fragilité **plafonne à celle du cycle**. Ne jamais présenter la fragilité plus confiante que sa moitié la plus faible.

## 4. Sortie & présentation (cohérent doctrine alerte)

- **Par nom** : score de divergence + **trajectoire** (delta de crowding — le vrai signal) + jauges fines par composante (percentile + delta + poids skill). Jamais R/J/V.
- **Feeds** : la position-card (le « qu'est-ce qui a changé » + le steer), la lentille de fragilité 2D.
- **Self-scoring** : chaque lecture pré-enregistre « crowded + révisions roulent → sous-perf facteur 3M » via `insert_prediction` (`methodology_version='consensus_v0'`) → résolu → Brier. **N-riche = un vrai track-record s'accumule en semaines, pas en années** (contrairement à la crisis gauge). C'est ici que la calibration du projet prouve qu'elle marche.

## 5. Architecture

```
intelligence/divergence_engine.py  (le même que macro)
  compute_divergence('micro', ticker) -> {D, phase, fragility, p_outcome, band, drivers, confidence, ...}
intelligence/micro_inputs.py   (disjoint de macro_inputs.py — test verrouillant)
table consensus_snapshots (append-only) -> trajectoire + delta + self-scoring
```

## 6. Build sequence (free-data-first)

1. **v0 = ce qui est cleanly free** : short interest + multiple vs historique + crowding ETF (holdings) + divergence prix-croyance → `consensus_v0`. Fail-soft sur les composantes absentes (None, pas crash).
2. `consensus_snapshots` append-only (sans ça, pas de delta de crowding = pas de phase réflexive).
3. **Calibration panel** : outcome = return relatif forward, IC/PR-AUC/confusion, purged walk-forward, baselines.
4. **v1** : ajouter révisions BPA (S-tier, data-constrained → décider feed) + borrow fee.
5. **Fragilité** : brancher l'amplificateur cycle (depuis la projection macro), calibrer l'interaction, plafonner la confiance.
6. Wire : position-card + fragility lens 2D.

## 7. Seams (verify-before-patch) + pièges

- **Source crowding ETF** : holdings de SMH/SOXX/QQQ — confirmer un accès propre (issuer / un endpoint free) avant de promettre le S-tier. Sinon v0 sans, flaggé.
- **Révisions BPA propres** = payant (le S-tier le plus important côté réalité). Décision feed (lié à Q2). En v0, direction grossière via yfinance, marquée basse-fiabilité.
- **Pièges** : k-fold (→ purged walk-forward) ; **IC sur N=jours** (→ N = noms×périodes indépendantes) ; harvester de l'alpha au lieu de mesurer l'absence d'edge (dérive de mission) ; présenter la fragilité plus confiante que le cycle (interdit §3).

## 8. Tests verrouillants

- **inputs disjoints** macro∩micro = ∅ (assert).
- **fail-soft** : composante absente → None + confidence réduite, jamais crash.
- **delta réflexif** : sans `consensus_snapshots` historique → la phase est `unknown`, pas fabriquée.
- **confiance fragilité ≤ confiance cycle** (assert sur le plafond).
- **self-scoring wired** : lecture → ligne `predictions` `consensus_v0`.
- **baseline single-factor** : le pipeline logge l'IC du meilleur facteur seul ; si le cocktail ne bat pas → fallback (assert).

## 9. Implementation Status

- **Gravé** : 2026-06-08 (doc reçu, archivé pour build futur post-cornerstone macro)
- **Implémentation** : NOT_STARTED — orphelin (0 refs code 09/06)
- **Doublon résolu** : `SPEC_CONSENSUS_MICRO.md` était une version brute du même SPEC (10 sections identiques), supprimé 09/06 après verify-before-delete (zéro contenu doctrinal unique perdu). FRAGILITE conservée car master-référencée + markdown enrichi.
- **Fichiers cibles** : `config/divergence.yaml` (à créer, partagé avec macro), `intelligence/consensus_fragilite.py` (à créer ; nom final tranché à la création selon vocabulaire canonique), `tests/test_consensus_fragilite.py` (à créer)
- **Audit drift** : `scripts/audit_canonical_drift.py`
- **Prochain step** : FUTURE post-cornerstone-macro (cf TODO #92).

## 10. Le fil

> La crisis gauge est spéculative et N-starved : on la *falsifie*, on l'humilie, on l'affiche faible. Le **consensus est N-riche et validable** : c'est là que la calibration du projet **prouve** qu'elle marche, vite. La fragilité est leur produit — et elle ne ment jamais sur le fait qu'elle est forte d'un côté (micro) et faible de l'autre (cycle). Construire le consensus brillamment, c'est exploiter sa richesse statistique sans la confondre avec la pauvreté de la macro.
