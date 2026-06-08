# Spec north-star — Indicateur cornerstone : moteur divergence-réflexivité

> Le document le plus important de la pile. Le cycle, le consensus et la crisis gauge ne sont pas trois indicateurs — ce sont les **projections d'un seul moteur** qui mesure la tension entre la croyance collective et la réalité livrable, et qui *gouverne* le comportement au lieu de prédire l'avenir. Hérite de `QUALITY_BAR`, `CALIBRATION_DOCTRINE`, `PLAN_REFONTE_ALERTES`.

## 0. Ce que c'est — et ce que ce n'est PAS

- **N'est pas** un prédicteur de cycle (commoditisé — tout le monde lit la même courbe). 
- **Est** un mesureur de la **divergence croyance ↔ réalité livrable**, conscient de sa **phase réflexive**, qui **gouverne** (gate ce que tu as le droit de faire), et qui **se méfie le plus de lui-même quand il est le plus confiant**.
- Pourquoi c'est central : le « behavior gap » (l'investisseur moyen perd ~3-4%/an en achetant l'euphorie late-cycle crowdée, vendant le désespoir early-cycle) **est** structurellement une erreur cycle×consensus. C'est la racine de la plupart des problèmes de traders, et de tes deux biais (lock-in, FOMO).

## 1. La primitive (le geste de construction qui fait la différence)

Une seule grandeur, calculée **au niveau de la primitive**, pas en combinant deux scores post-hoc :

```
Divergence  D = weighted_mean(z_signed) sur (croyance pricée + réalité livrable)
Phase       Φ = weighted_mean(z_signed) sur (phase réflexive)
Fragilité   F = |D| * (1 + max(0, Φ))
```

**Erratum 08/06 (tracer-bullet C6)** : la formulation initiale `D = (croyance pricée) − (réalité livrable)` est conceptuellement juste mais arithmétiquement fausse. Les `sign_theory` figés du YAML pointent **déjà tous** vers "divergence positive". Soustraire deux buckets dont les inputs sont alignés = compter le signal en double. La forme exécutable agrège globalement les contributions z-signed des deux buckets de divergence (cf `L24` LESSONS — walking skeleton catches abstraction bugs early).

Le bucket sert à **organiser/auditer/pondérer**, pas à inverser la sommation. Phase réflexive reste séparée (mesure dynamique distincte : auto-renforçant > 0 > auto-défaisant).

- **Macro projection** → la *crisis gauge* / le cycle (croyance macro vs croissance/liquidité livrable).
- **Micro projection** (par ticker) → le *consensus* (croyance sur un nom vs fondamentaux/révisions).
- **Interaction** → la *lentille de fragilité* (le danger est dans l'alignement des deux échelles, jamais dans l'une seule).

**Règle d'or de construction : inputs disjoints entre les deux échelles** (macro = croissance/liquidité ; micro = positionnement/crowding ; zéro input partagé) → pas de double-comptage. L'association est dans la primitive, pas dans un produit final.

## 2. Les inputs — taxonomie 3 buckets × 2 échelles (signés-théorie, prior-tiers)

### Macro (crisis gauge / cycle)
| Bucket | Input | Tier | Signe (figé) |
|---|---|---|---|
| Croyance pricée | Spread HY (OAS) | **S** | tight → étiré |
| | Valorisation / ERP | B | élevé → étiré |
| | Courbe 2s10s/3m10y | A (stabilité↓ post-QE) | inversion → étiré |
| Réalité livrable | Liquidité nette / impulsion crédit | **S** | resserrement → divergence |
| | Largeur révisions BPA agrégée | A | décélère → divergence |
| | Nowcast croissance (composite) | B | ralentit → divergence |
| Phase réflexive | Largeur de marché (%>200dma, A/D) | A | narrowing → auto-défaisant |
| | **Delta** impulsion crédit | **S** | delta<0 → bascule |
| **Rejets** | BTC drawdown, VIX-niveau, sondages sentiment, proxies redondants | — | bruit / non-pertinent stock-only |

### Micro (consensus par nom)
| Bucket | Input | Tier | Signe |
|---|---|---|---|
| Croyance pricée | Crowding passif (ETF SMH/SOXX) | **S** | float passif↑ → étiré |
| | Borrow fee | A | élevé → short crowdé |
| | Multiple vs propre historique | B | élevé → étiré |
| | Dispersion/niveau analystes | B | serré+bullish → crowdé |
| Réalité livrable | Largeur révisions BPA (nom) | **S** | roule → divergence |
| | Momentum drivers de thèse | A | dégrade → divergence (lit le moteur érosion) |
| Phase réflexive | **Delta** de crowding | **S** | accélère→renforce / ralentit→épuise |
| | Divergence prix-vs-croyance | A | prix ne confirme plus → bascule |
| **Rejets** | sentiment social, Trends, gamma/max-pain, SI brut | — | bruit / trop tactique |

## 3. Calibration (hérite `CALIBRATION_DOCTRINE`)

- Poids = `skill × orthogonalité × fiabilité-source × stabilité`, **shrink vers le prior-tier** à petit-N, **doit battre l'équipondéré OOS**. Jamais tapé.
- Chaque niveau → `P(outcome | niveau)` backtesté, **splits temporels L16, zéro look-ahead**.
- Recalibration isotonic/Platt → **ECE→0** (stated=realized) ; **bande coverage-calibrée** (conformal).
- **Méta-calibration sur N** : à N≈10 cycles, bande large par prior + honnêteté sur la confiance-dans-la-confiance.

## 4. Alarme (hérite `PLAN_REFONTE_ALERTES`)

- **Le droit d'alarmer se gagne** : seuil calibré qui prédit au-dessus du base rate **ET** déclenché sur le *delta*, pas l'état persistant.
- **Vigilance concentrée** (ta préférence asymétrique) : hair-trigger sur les tier-S high-skill (recall haut, faux positifs tolérés là), **silence total sur le bruit**. Plus vigilant ET moins alarmiste.
- **Défaut = calme.** >~20% en alarme simultanément = calibration cassée, test qui échoue le build.
- États persistants (cycle LATE) → contexte book-level, retirés des lignes.

## 5. Sortie & présentation (tuer le rouge/jaune/vert)

- **Composite = PROBABILITÉ CALIBRÉE + TRAJECTOIRE**, jamais une couleur. Ex. `P(régime de stress, 3M) = 28% ↑ (de 19%)`. Tu poses TON seuil d'action selon ton asymétrie de perte.
- **Par indicateur = jauge fine** : position sur sa propre distribution calibrée (percentile/z → outcome forward) + **flèche de delta** + **poids visuel = skill×fraîcheur**. Pas un point coloré.
- **Le gouverneur** (MACRO IMPACT ON BOOK) reste — c'est l'actionnable. Son urgence se recalibre sur la lecture honnête.
- La couleur, si gardée, encode **l'asymétrie de conséquence** (downside catastrophique reste visible), pas l'état — secondaire.

## 6. La crisis gauge spécifiquement (amélioration)

Aujourd'hui : « CRISE 4/4 score 120 » piloté par **BTC drawdown + VIX 21** alors que **spread HY 274bp et MOVE 75 sont calmes** = faux positif manifeste (les vrais gauges disent calme, le bruit crie crise).

Refonte :
- Drop BTC/VIX-primary ; les tier-S (spreads, MOVE, banques, courbe, liquidité) dominent → la lecture **bascule de "CRISE" à "late-cycle complaisant, fragile, pas de stress aigu"** — plus utile et plus honnête.
- Présentation : `P(stress, 3M) = X% ↑/↓` + les **2-3 drivers high-skill qui bougent réellement** (percentile + delta) + la **confiance** (N-dépendante) + la **trajectoire propre** (pas le sparkline boueux).
- Sémantique honnête : tu n'es pas dans la crise, tu es dans le calme-avant fragile où une crise *démarrerait* — et le déclencheur serait l'élargissement des spreads, à **surveiller**, pas « ACT NOW ».
- **Test de validation = matrice de confusion sur l'historique** : combien de fois crié crise vs combien de crises réelles. C'est le verdict, pas une opinion.

## 7. Architecture code

```
intelligence/divergence_engine.py
  compute_divergence(scale: 'macro'|'micro', entity: str|None) -> {
    D: float, phase: float, fragility: float,
    p_outcome: float|None,          # probabilité calibrée (None si fail-closed)
    band_lo, band_hi: float,        # coverage-calibrée
    drivers: [{name, percentile, delta, weight, asof, source}],
    confidence: float, effective_asof: str, degraded: bool
  }
  # macro projection -> crisis gauge ; micro(ticker) -> consensus ; interaction -> fragilité
```

- Tables (append-only, L17) : `divergence_readings` (trajectoire + self-scoring) ; réutilise `consensus_snapshots` / `cycle_readings` comme stores d'inputs par échelle.
- **Self-scoring** : chaque lecture non-dégradée pré-enregistre une implication falsifiable via le funnel `insert_prediction` (`methodology_version='divergence_v0'`), résolue par le resolver existant → Brier du moteur. L'indicateur le plus important porte la calibration la plus lourde.
- **Inputs disjoints** : module `macro_inputs.py` / `micro_inputs.py` séparés, aucun champ partagé (test verrouillant).

## 8. Build sequence

1. `config/divergence.yaml` (L17) — inputs, signes figés, prior-tiers, magnitudes v0, temporal_splits.
2. `divergence_engine.py` — primitive D/Φ/F + fail-closed + bande. (pur, testable)
3. Inputs macro (réutilise le macro stress monitor existant, **nettoyé** : drop BTC/VIX-primary).
4. Inputs micro (réutilise `consensus_thermometer` v0).
5. Calibration : backtest niveau→P(outcome), recalibration, ECE, matrice de confusion.
6. Self-scoring hook + table.
7. Présentation : crisis gauge (proba+trajectoire+drivers) → puis fragilité 2D → puis wire position-card.

## 9. Seams à vérifier (Claude Code, verify-before-patch)

- Le macro stress monitor existant (`CALIB V5`) — quels inputs, comment scoré ? **Réutiliser en nettoyant, pas réécrire.** Identifier où BTC/VIX pilotent le score.
- `consensus_thermometer` (en cours) — brancher comme projection micro.
- Funnel `insert_prediction` (storage.py:850) pour le self-scoring.
- `calibration.yaml` temporal_splits + la stack isotonic/Platt.

## 10. Tests verrouillants

- **inputs disjoints** : aucun champ macro∩micro (assert).
- **signes figés** : aucune magnitude n'inverse une contribution (assert).
- **fail-closed** : <2 inputs frais par échelle → `p_outcome=None`, pas de lecture.
- **alarme rare** : sur fixture calme, le moteur ne crie pas ; matrice de confusion sur historique → faux-positifs bornés.
- **self-scoring wired** : lecture non-dégradée → ligne `predictions` `divergence_v0`.
- **ECE** : fixture calibré → ECE≈0 ; fixture surconfiant → détecté.
- **gouverneur cohérent** : le book-impact dérive de la lecture, pas d'un seuil indépendant.

## 11. Le fil (à ne jamais perdre)

> La pierre angulaire n'est pas un prédicteur — c'est un mesureur de la tension croyance↔réalité, conscient de sa phase réflexive, qui **gouverne ton comportement** au lieu de prétendre voir l'avenir, **se méfie le plus de lui-même quand les deux échelles hurlent la même chose**, et dont le rouge est **rare et mérité**. Construire ça brillamment, c'est graver l'humilité dans le marbre de l'indicateur le plus important.
