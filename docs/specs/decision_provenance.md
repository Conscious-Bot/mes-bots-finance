# SPEC — DECISION PROVENANCE (la primitive manquante)

_Créée 01/08/2026. Statut : SPEC, non implémentée._

## 0. Pourquoi cette spec est courte

Huit « chantiers » de la feuille de route (attribution de valeur, retrait des règles
mortes, dérive structurelle, entropie de décision, comptabilité informationnelle,
détecteur d'angles morts, méta-calibration, coût économique des règles) **n'ont
aucune donnée propre**. Ce sont des REQUÊTES sur un seul enregistrement.

Deux autres existent déjà sans schéma : les **contrefactuels** sont écrits en prose
dans chaque décision depuis le 30/07 (« armés (a)(b)(c), résolution +30/60/90j ») ;
il manque une table, pas un moteur.

**Une primitive. Deux tables. Le reste est du SQL.**

## 1. Ce qu'on enregistre (et ce qu'on n'enregistre pas)

### `decision_provenance` (append-only)

| Colonne | Rôle |
|---|---|
| `decision_id` | FK vers `decisions` |
| `component_kind` | `assumption` · `policy` · `solver` · `sentinel` · `evidence` · `doctrine` · `override` |
| `component_id` | `H12`, `FACTOR_CAP_DOMINANT`, `allocation_solver`, `EV-2026-07-30-KLAC`… |
| `role` | **`consulted`** (regardé) · **`used`** (entré dans le raisonnement) · **`determinant`** (a changé l'issue) |
| `captured` | `auto` (le moteur l'a observé) ou `manual` (déclaré) |

La distinction `consulted / used / determinant` est le cœur : sans elle, on créditera
dans six mois des composants qui étaient « simplement dans la pièce ».

### `decision_alternatives` (append-only)

| Colonne | Rôle |
|---|---|
| `decision_id` | FK |
| `alternative` | `cash`, `no_action`, `KLAC`, `venture_1pct`, `exit`… |
| `why_not` | raison écrite du rejet |
| `measurable_by` | comment la mesurer plus tard (prix de référence, événement, ratio) |

Le **regret** est alors calculable : issue réalisée − meilleure alternative crédible.
C'est plus informatif que le gain, et ça ne coûte rien de plus à enregistrer puisque
les alternatives sont déjà écrites en prose aujourd'hui.

### Épinglage A9 (sur `decisions`)

`assumptions_hash` · `policy_hash` · `solver_version` · `data_asof`. Déjà produits par
`scripts/assumption_graph.py --hash`.

## 2. Le coût de saisie est le vrai risque (H11)

Une provenance qui exige un formulaire à chaque décision **mourra en trois semaines**.
Règle de conception : **le maximum doit être capturé automatiquement.**

- `auto` : quels monitors ont tourné, quelles politiques ont été évaluées, quels
  triggers ont été testés, quels seuils ont été franchis, quels hashes étaient actifs.
  Le moteur le sait déjà — il suffit de l'écrire.
- `manual` : **uniquement `determinant`** et les alternatives. Une ligne, deux champs.

Si la saisie manuelle dépasse ~30 secondes par décision, la spec a échoué.

## 3. Ce que ça débloque — en SQL, pas en projets

| Capacité demandée | Requête |
|---|---|
| Attribution de valeur | `GROUP BY component_id WHERE role='determinant'` joint aux résolutions |
| Règles mortes / retirement | composants à **0 `determinant`** sur N décisions ⇒ **revue obligatoire** |
| Dérive structurelle | comparaison de la distribution des `determinant` entre deux périodes |
| Entropie de décision | dérivée de la probabilité énoncée à l'ouverture (déjà requise pour Brier) |
| Angles morts | `component_id` du registre **jamais apparus** en provenance |
| Méta-calibration par couche | part des décisions où une couche donnée est `determinant` |
| Coût économique d'une règle | regret cumulé des décisions où la règle a été `determinant` bloquant |
| Influence décisionnelle (axe 2) | `count(determinant)` par composant |

**Aucune de ces vues ne persiste son résultat** (A8) : ce sont des requêtes.

## 4. Le piège mortel, déjà identifié

« 0 influence ⇒ supprimer » détruirait le backstop, les paliers, la garde T13 et
toutes les sentinelles — **aucun n'a jamais influencé une décision**, par construction.
Le typage `active` / `contingent` de `policy.yaml:pruning_policy` s'applique
intégralement ici : un composant contingent ne s'élague jamais sur l'influence,
seulement sur l'impossibilité prouvée du scénario ou sur une redondance démontrée.

## 5. Ce qu'on ne construit PAS maintenant

Les analyses exigeant N élevé : méta-calibration chiffrée, comparaison de solveurs
(shadow solver), coût économique des règles, entropie exploitable. Sur N ≈ 40
décisions résolues, elles produiraient **du bruit présenté comme de la mesure** — ce
que le système interdit partout ailleurs. Seuils d'activation :
`MIN_N_FOR_DEBIAS = 100` pour la calibration ; ≥ 200 décisions pour l'attribution
par couche ; ≥ 3 ans pour le coût économique d'une règle.

**Le seul coût irréversible est de ne pas enregistrer.** L'enregistreur se construit
maintenant ; les analyses attendront d'avoir de quoi être vraies.

## 6. Shadow solver — la seule exception à « pas de moteur maintenant »

Le solveur fantôme (calculer une seconde allocation sans l'exécuter) est **gratuit en
risque** et son historique ne peut se rattraper rétroactivement. Il s'ajoute donc dès
que le solveur principal écrit une sortie : deux lignes de plus, aucune décision
modifiée, un jeu de comparaison qui commence à s'accumuler aujourd'hui plutôt que
dans deux ans.

## 7. Ordre d'implémentation

1. Migration : deux tables + triggers append-only + 4 colonnes de pins sur `decisions`.
2. Capture `auto` dans les monitors et le solveur (le moteur écrit ce qu'il a évalué).
3. Capture `manual` minimale : `determinant` + alternatives à la clôture d'une décision.
4. Sortie du shadow solver.
5. **Rien d'autre avant N.**
