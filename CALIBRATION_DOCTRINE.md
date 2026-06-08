# PRESAGE — Doctrine de calibration (sous le capot)

> Doctrine **transversale** : s'applique à TOUT indicateur composite (horloge de cycle, thermomètre de consensus, lentille de fragilité, érosion, futurs). Règle cardinale : **l'importance d'un indicateur n'est jamais tapée — elle est calculée, gagnée, auditée, et shrinke vers l'humilité quand l'évidence manque.** Dès qu'un poids est écrit en dur, c'est un bug doctrinal.

## 0. Les deux précisions (ne pas confondre)

- **Précision du POINT** (l'aiguille nette) — *fausse* précision sur un petit-N non-stationnaire. Interdite. Le point reste une bande honnête.
- **Précision du SUBSTRAT** (pondération, qualité/véracité/fraîcheur des sources, calibration) — *hyper-précise et obligatoire*. C'est l'objet de ce doc.

## 1. Poids d'un indicateur (côté input) — produit de 4 quantités mesurées

`w_i ∝ skill_i × orthogonalité_i × fiabilité_source_i × stabilité_i`, normalisé `Σ w_i = 1`.

| Composante | Définition | Mesure concrète |
|---|---|---|
| **skill_i** | contribution prédictive OOS réelle | `1 − Brier_avec_i / Brier_sans_i`, ou coef standardisé dans un modèle régularisé (ridge/lasso) prédisant la cible. ~0 si l'indicateur n'a jamais prédit. |
| **orthogonalité_i** | information *unique* (anti-double-comptage quantifié) | `1 − R²(i | autres)` — pénalise la redondance avec le set existant |
| **fiabilité_source_i** | track-record de la source de l'indicateur | depuis `sources` : credibility (Brier-dérivé), shrink Wilson par `n_correct/n_signals` |
| **stabilité_i** | stationnarité du lien prédictif | `1 − variance normalisée(skill_i)` sur fenêtres roulantes / régimes. La courbe post-QE voit son poids décroître ici |

Ré-estimé **en roulant**, jamais figé.

## 2. Confiance accordée à un *datum* (qualité × véracité × fraîcheur) — produit de 4

`c_{i,t} = provenance_i × fiabilité_gagnée_i × fraîcheur_{i,t} × corroboration_{i,t}`

- **provenance** : tier {primaire-dur (chiffre SEC) > dérivé > opinion}. Lit `source_metadata_json` / `methodology_version`. Le mou est escompté.
- **fiabilité_gagnée** : hit-rate réalisé de la source (Brier), borné Wilson petit-n. *Existe déjà* : `sources.credibility/n_correct/half_life_days`.
- **fraîcheur** : `decay(âge / demi-vie naturelle de l'item)`. 13F à J-45 = frais vs cadence trimestrielle mais stale pour le positionnement ; prix à J-15 = mort. Calculé exactement depuis l'as-of (triple M1).
- **corroboration** : confirmé par une source *orthogonale* (pas corrélée) > outlier isolé.

## 3. Poids effectif dynamique (par calcul)

`w_eff_{i,t} = w_i × c_{i,t}`, renormalisé sur les indicateurs disponibles.

→ Un indicateur à fort skill mais dont la lecture *du jour* est stale ou louche **s'auto-down-weighte pour ce calcul-là**. Le poids respire avec la qualité de la donnée présente.

## 4. Shrinkage à petit N (le garde-fou anti-overfit)

`w_i^shrunk = λ · w_i + (1 − λ) · (1/k)` où `k` = nb d'indicateurs, `λ ∈ [0,1]` = force d'évidence (taille d'échantillon effective).

- λ → 0 à petit N → **équipondéré** (on n'ose pas différencier).
- λ → 1 à mesure que N grandit → les poids se séparent **quand ils le méritent**.

Miroir exact du sous-Kelly : à faible certitude, on ne différencie pas fort.

## 5. Le test d'humilité (obligatoire) — battre l'équipondéré OOS, sinon l'utiliser

Résultat le plus documenté de la finance quant (Markowitz vs 1/N) : la pondération « optimale » bat *rarement* l'équipondéré naïf hors échantillon (elle overfit l'estimation des poids). Donc :

> La machinerie de pondération raffinée n'est **déployée que si elle bat l'équipondéré OOS au-delà du bruit**. Sinon → équipondéré. Souvent elle ne le bat pas — c'est une **découverte**, pas un échec.

Gate dur : `skill_OOS(poids appris) > skill_OOS(équipondéré) + marge`, sinon fallback 1/k.

## 6. Calibration de la sortie (côté output) — la fiabilité, pas la netteté

Le composite brut → **recalibré** (isotonic/Platt, déjà dans ta stack) pour que `stated = realized` : quand le système dit 60%, il a raison 60% du temps.

- **Cible mesurable : ECE (Expected Calibration Error) → 0**, mesuré OOS.
- **Décomposition de Brier** : reliability (calibration) / resolution (discrimination) / uncertainty. Maximiser la reliability *précisément* ; pousser la resolution autant que l'évidence permet ; **jamais troquer l'une contre l'autre**.
- **Bande coverage-calibrée** (conformal) : la bande « 60% » contient la vérité *exactement* 60% du temps OOS. Si elle déborde plus souvent → trop étroite → élargir jusqu'à couverture exacte. On calibre l'incertitude au degré près.
- **Méta-calibration** : la précision de la calibration est fonction de N. À petit N → bande large par prior + honnêteté sur la confiance-dans-la-confiance (« ECE estimé sur n=12, IC large → calibration non garantie »).

## 7. Fail-closed & auditabilité (non-négociable)

- **Tout poids est décomposable à la demande** : « pourquoi l'indicateur X pèse 0,18 maintenant ? » → `[skill 0,6 × orth 0,4 × source 0,8 × stab 0,9] × confiance-datum 0,7`. Jamais un nombre opaque.
- **Aucun poids tapé en dur dans le code.** Les poids vivent comme quantités *calculées* + leurs composantes versionnées dans `calibration.yaml`.
- **Fail-closed** : évidence sous seuil → shrink vers équipondéré ou dégrade ; jamais une différenciation fabriquée.

## 8. Grounding (tu as déjà 80% des briques)

| Brique doctrine | Existe dans |
|---|---|
| fiabilité-source gagnée | `sources.credibility / n_correct / half_life_days / half_life_n_samples` |
| skill par source (Brier) | `predictions.brier_score` + `scripts/source_attribution_brier.py` |
| fraîcheur (as-of) | triple M1 (value, as-of, source) — Axe 5 |
| recalibration isotonic/Platt | stack `scikit-learn` + `calibration.yaml` |
| splits temporels (anti-look-ahead) | `calibration.yaml audit_metadata.temporal_splits` (L16) |
| provenance | `source_metadata_json` / `methodology_version` |

La doctrine = **composer ces quantités mesurées en poids dynamiques**, pas en taper.

## 9. Seams à vérifier (Claude Code, verify-before-patch)

- Structure exacte de `sources` (champs credibility/half_life) + comment ils sont recalculés aujourd'hui.
- `source_attribution_brier.py` — réutiliser pour le `skill_i`, ne pas réécrire.
- `calibration.yaml` — où loger les composantes de poids + leur versioning.
- Confirmer la dispo d'un modèle régularisé (sklearn ridge/lasso) pour skill + orthogonalité.

## 10. Tests verrouillants

- **poids jamais en dur** : grep — aucun `weight = <float>` littéral dans les modules d'indicateurs (gate CI possible).
- **shrinkage** : à N faible simulé, les poids convergent vers `1/k` (assert).
- **humilité** : si les poids appris ne battent pas l'équipondéré OOS sur un fixture, le système retourne l'équipondéré (assert).
- **down-weight dynamique** : un datum stale réduit le poids effectif de son indicateur pour ce calcul (assert).
- **auditabilité** : `explain_weight(indicator)` retourne la décomposition complète (assert non-vide).
- **ECE** : sur un fixture calibré, ECE ≈ 0 ; sur un fixture surconfiant, ECE > seuil détecté (assert).

> En une phrase : **« cet indicateur matters more » est une quantité calculée — skill × information unique × fiabilité-source-gagnée × stabilité, modulée par la fraîcheur du datum, shrinkée vers l'équipondéré quand l'évidence manque, et déployée seulement si elle bat le baseline bête.** Hyper-précis sous le capot ; honnêtement coarse en sortie.
