# Méthode de calibration du cornerstone — au cordeau

> La partie la plus risquée à laisser à un agent. Comment valider qu'un indicateur (ou le composite) prédit *réellement* le mauvais outcome, sans se mentir. Hérite de `CALIBRATION_DOCTRINE` + `SPEC_CORNERSTONE`. Discipline : `L16` (splits temporels), fail-closed, anti-look-ahead.

## 0. La posture (à lire avant tout — elle change tout)

**Sur les crises, tu ne pourras JAMAIS prouver statistiquement que ton indicateur marche.** ~10-12 cycles dans l'ère des bonnes données, ~3-5 vrais drawdowns « crise ». Aucune puissance statistique pour *confirmer*. Donc :

> Le rôle premier du backtest n'est pas de **certifier** un bon indicateur — c'est de **falsifier** les mauvais. Tu peux *réfuter* un crying-wolf (la matrice de confusion le tue immédiatement). Tu ne peux pas *prouver* qu'un gauge calme prédit la prochaine crise.

Conséquence : la crisis gauge restera **un prior faiblement validé**, et doit se présenter comme tel (méta-calibration, §9). La calibration sert surtout à **élaguer le bruit et borner les faux positifs**, pas à décerner un brevet de prescience.

## 1. Définir le label (l'outcome opérationnel) — AVANT de calibrer

Pas « une crise » (flou, incalibrable). Un événement **binaire, daté, seuillé** :

```
y[t] = 1 si max_drawdown( cible , [t, t+H] ) ≤ −θ   sinon 0
```

Choix à figer (et à versionner dans `divergence.yaml`) :
- **cible** : son book (semis-heavy → ≠ SPY) ET un proxy large (SPY) ET un proxy facteur (SMH). Calibrer plusieurs.
- **θ** : plusieurs seuils (−10% correction / −20% bear sont des régimes différents → multi-label).
- **H** : 3M (tactique) ; un horizon long séparé pour le cycle.

Le label utilise le futur (c'est normal — c'est la réalité réalisée). Le *no-look-ahead* porte sur les **features** (§2) et sur le **fit du modèle** (§3), pas sur le label.

## 2. Features point-in-time — le piège du vintage

Chaque feature à la date `t` = la valeur **connue à `t`**, pas la valeur révisée d'aujourd'hui.
- **Données de marché** (spreads, MOVE, prix) : pas de révision → OK.
- **Macro** (production indus, bilan Fed, emploi) : **révisées**. Utiliser le **vintage** (as-released) ou accepter le biais et le **flaguer explicitement**. Utiliser la valeur finale = look-ahead silencieux.
- Deltas calculés depuis les valeurs point-in-time antérieures.
- N'utiliser que les indicateurs à historique point-in-time suffisant.

## 3. Le split — purged walk-forward (PAS du k-fold)

Le piège #1 de la ML financière. La cible à `t` utilise des données jusqu'à `t+H` → un échantillon de train proche de la frontière de validation **fuit**.

- **JAMAIS de k-fold aléatoire** (fuite via autocorrélation).
- **Walk-forward / fenêtre expansive** : train [start, T] → val [T, T+Δ] → roule.
- **Purge + embargo** (López de Prado) : retirer du train tout échantillon dont la fenêtre de label `[s, s+H]` chevauche la validation, + un gap d'embargo. Sans ça, ton OOS est contaminé.
- **N effectif = nombre d'épisodes indépendants (~10-20), PAS le nombre de jours.** Les jours sont massivement autocorrélés. Toute stat de significativité se calcule sur les épisodes, jamais sur les milliers de lignes quotidiennes. C'est *la* réalité statistique à ne jamais oublier.

## 4. Le modèle — brutalement simple (petit N + humilité équipondérée)

- **Régression logistique à coefficients signés-théorie** (le signe figé, seule la magnitude estimée), **fortement régularisée** (L2/L1). Ou simplement : score = somme pondérée de z-scores signés → lien logistique.
- **JAMAIS un gradient-boosting / forêt** sur ~15 épisodes → overfit catastrophique.
- **Peu de features** (les tier-S/A), shrinkage fort, et l'équipondéré comme baseline à battre.

## 5. Calibration de la sortie (score brut → probabilité)

- Le score brut n'est pas une probabilité. Mapper via **isotonic ou Platt** (tu as les deux), fit sur une tranche de calibration séparée (ou cross-fitting), pour que **stated = realized**.
- **ECE** (Expected Calibration Error) : binner les prédictions, comparer proba moyenne prédite vs fréquence réalisée par bin, écart moyen pondéré. + **reliability diagram**.
- **Brier décomposé** : reliability / resolution / uncertainty. Maximiser la reliability précisément, la resolution autant que l'évidence permet.

## 6. La matrice de confusion — le verdict, lu avec ton asymétrie de perte

- À un seuil de proba (au-dessus duquel on alarme), sur l'**OOS** : TP / FP / FN / TN.
- **Seuil choisi par l'asymétrie de perte**, pas par l'accuracy : `coût(FN) >> coût(FP)` → minimiser `coût(FN)·P(FN) + coût(FP)·P(FP)`. Pousse vers le **recall** (attraper les crises) au prix de plus de fausses alarmes = ta « vigilance > complaisance ». **MAIS** (doctrine alarme) les faux positifs acceptés sont sur le **composite high-skill**, jamais sur le bruit.
- **Métriques robustes à l'imbalance** (les crises sont rares) : **PR-AUC** (pas ROC-AUC, trompeur sous imbalance), **Brier skill score** vs base-rate, precision/recall **comparés au taux de base**.
- L'état actuel passé à cette moulinette : beaucoup d'alarmes, peu de crises → FP élevé, précision basse → crying-wolf **chiffré**. (« CRISE 4/4 » avec spreads à 274bp = FP que la matrice expose en une ligne.)

## 7. Les baselines à battre (les gates d'humilité)

Le composite calibré DOIT battre, OOS :
1. **Le taux de base** (toujours prédire P(crise) inconditionnel) → Brier skill score > 0.
2. **L'équipondéré** (gate de `CALIBRATION_DOCTRINE`).
3. **Le meilleur indicateur seul** (ex. spreads HY seuls). **Brutal et essentiel** : si le cocktail ne bat pas « surveille juste les spreads HY », le cocktail est sur-ingénieré → fallback au single indicator.

Ne bat aucun → fallback au plus simple. C'est l'anti-overfit rendu opérationnel.

## 8. Emprunter du N en largeur (cross-sectionnel) — casser le plafond ~10 épisodes

Le temps ne donne que ~10 crises US. Vole du N à la **largeur** : calibrer la *relation* indicateur→outcome sur un **panel cross-pays / cross-actifs / histoires longues** (les mêmes dynamiques late-cycle-complaisance à travers marchés et décennies). On calibre la **relation** sur le panel, pas les niveaux spécifiques. C'est l'outside-view appliqué à la calibration.

## 9. Méta-calibration (honnêteté sur la confiance-dans-la-confiance)

Toute probabilité livrée porte : le **N** sur lequel elle repose, l'**ECE OOS + son IC**, la **couverture** de la bande. « P=28%, mais ECE sur n=12 épisodes, IC [0,03 ; 0,14] → traite le 28% comme 28% ±beaucoup. » **Conformal prediction** pour la garantie de couverture de bande.

## 10. Le protocole (la procédure exacte)

1. Matrice de features point-in-time (vintage macro + marché) + labels drawdown-forward binaires multi-seuils.
2. Walk-forward **purgé + embargo** autour de l'horizon de label.
3. Logistique **signée-régularisée**, peu de features, shrinkage.
4. Par fold : fit sur train → calibre (isotonic) sur tranche calib → prédit sur test.
5. Agréger les prédictions OOS → matrice de confusion (seuil coût-optimal), ECE, reliability diagram, Brier skill, PR-AUC.
6. Comparer vs base-rate / équipondéré / **single-best-indicator**.
7. Bat tout → déploie avec la map de calibration + la bande ; sinon → fallback.
8. **Ré-exécuter en roulant** (la calibration n'est jamais figée).

## 11. Les pièges que Claude Code va frapper (garde-fous)

| Piège | Symptôme | Fix |
|---|---|---|
| k-fold aléatoire | OOS trop beau | purged walk-forward + embargo |
| données macro révisées | look-ahead silencieux | vintage / as-released, ou flag |
| ROC-AUC sous imbalance | « AUC 0,9 ! » trompeur | PR-AUC + Brier skill |
| N = jours | fausse significativité | N = épisodes (~10-20) |
| gradient-boosting | overfit total | logistique signée régularisée |
| calibration figée | dérive non détectée | ré-estimation roulante |
| pas de baseline single-indicator | cocktail sur-ingénieré | gate « battre les spreads seuls » |
| « le modèle marche » | sur événements rares | posture falsification, pas confirmation (§0) |

## 12. Tests verrouillants

- **no-look-ahead** : un test injecte une feature future → la perf OOS doit s'effondrer si la purge marche (sentinelle).
- **N effectif** : la significativité est calculée sur épisodes, pas lignes (assert sur le compteur).
- **imbalance** : la métrique rapportée est PR-AUC/Brier-skill, jamais accuracy nue (assert).
- **baseline single-indicator** : le pipeline calcule et logge la perf du meilleur indicateur seul ; si le composite ne le bat pas, il fallback (assert).
- **ECE** : fixture calibré → ECE≈0 ; fixture surconfiant → détecté.
- **falsification** : sur l'historique, la matrice de confusion du monitor *actuel* (BTC/VIX) montre FP élevé → le test documente le crying-wolf comme baseline-à-battre.

> En une phrase : on calibre pour **réfuter le bruit et borner les faux positifs**, pas pour certifier la prescience ; sur peu d'épisodes, avec splits purgés, modèle signé-régularisé, calibration isotonic, matrice de confusion lue à l'asymétrie de perte, baselines bêtes à battre, N emprunté en largeur, et honnêteté brutale sur le peu qu'on sait.
