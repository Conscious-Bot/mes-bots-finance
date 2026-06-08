# Handoff — Cycle Calibrator (brief pour Claude Code)

> Brief d'implémentation. Lis d'abord le contexte, applique les règles dures, vérifie les seams (verify-before-patch) AVANT de patcher. Ce doc dit le QUOI et le POURQUOI ; toi tu confirmes le COMMENT contre le vrai code.

## 0. Contexte à charger (lire dans l'ordre)

- `AGENT_HANDOFF.md` — contrat de travail (verify-before-patch, safe-fail, fail-closed, reversible).
- `QUALITY_BAR.md` — M1 (triple valeur/as-of/source), M2 (claim pré-enregistrée), M3 (sizing edge), méta fail-closed.
- `docs/LESSONS.md` — **L15** (fail-closed scoring : jamais de nombre fabriqué), **L16** (splits temporels datés avant tout tuning), **L17** (config déclarative YAML / live state DB).
- `IDEAS_BACKLOG.md` — I2 (l'horloge de cycle, son insight et son caveat).

## 1. Ce qu'on construit — et ce qu'on NE construit pas

Une **horloge de cycle macro** = un *prévisionniste qui gagne sa position au cadran par track-record*, PAS un widget réglé à la main. Elle **conditionne** le book (ballast monte à late-cycle, sizing cycliques baisse, seuil d'érosion se durcit) — elle ne *décide* pas, elle ne *time* pas.

Le plafond à respecter dès la conception : on calibre sur **~10 cycles** (N petit, non-stationnaire). Donc l'objectif n'est pas « précis » mais **« aussi précis que l'évidence le permet, pas un cran de plus »**. Une horloge honnêtement *coarse* (distingue early/late) bat une horloge faussement *précise* (« 10h47 »).

## 2. Règles dures (non-négociables — un test verrouille chacune)

1. **Inputs signés par la théorie.** Le SIGNE de chaque input vers late/contraction est *fixé par l'économie*, jamais ajusté par les données. On n'estime que la **magnitude**. Un calibrage qui peut *retourner* un signe = bug. (Anti-overfitting macro : la théorie contraint la direction, les données ne touchent que le dosage.)
2. **Calibrer contre l'outcome, pas l'apparence.** La lecture se **pré-enregistre comme prédiction falsifiable** et se score (Brier). L'horloge n'est pas exemptée de M2. L'aiguille n'a le droit de pointer « late » que si « late » a une validité prédictive *mesurée*.
3. **Splits temporels (L16).** Tout tuning de magnitude daté AVANT le tuning. Le label « on était en late-cycle » à l'instant T n'utilise **aucune** donnée > T (pas de hindsight).
4. **Bande = erreur OOS réalisée + désaccord inputs.** Jamais un chiffre tapé. La bande EST la mesure de confiance, pas un ornement.
5. **Ré-estimation roulante.** Poids jamais figés (non-stationnarité). Fenêtre glissante recency-pondérée ou poids conditionnels au régime.
6. **N emprunté en largeur.** 10 cycles ne suffisent pas en longueur → vole du N au cross-sectionnel (pays/secteurs/histoires longues).
7. **Coarse-not-precise.** Granularité = phases larges, bande honnêtement large. Interdiction de simuler une précision intra-phase.
8. **Fail-closed.** <2 inputs frais → pas d'aiguille, phase = « insufficient ». Jamais une fausse précision.

## 3. Artefacts à créer

- **`config/cycle.yaml`** (déclaratif, L17) : liste des inputs, leur **signe théorique figé**, leurs magnitudes (estimées, versionnées), les bornes de phase (angles), et `audit_metadata.temporal_splits` (mirror de `calibration.yaml`).
- **`intelligence/cycle_calibrator.py`** :
  ```
  compute_cycle_reading() -> {
    angle: float|None,           # None si fail-closed
    band_lo, band_hi: float,     # bande d'incertitude (degrés)
    phase: str,                  # 'recovery'|'expansion'|'late'|'peak'|'slowdown'|'contraction'|'trough'|'insufficient'
    confidence: float,           # dérivé de la bande, pas tapé
    effective_asof: str,         # as-of de l'input le plus vieux contributeur (M1)
    inputs: [{name, raw, z, sign, weight, asof, source}],
    degraded: bool
  }
  ```
- **table `cycle_readings`** (append-only) : `id, computed_at, angle, band_lo, band_hi, phase, confidence, effective_asof, inputs_json, prediction_id, degraded`. → trajectoire + lien vers la prédiction d'auto-scoring.
- **hook self-scoring** : à chaque compute non-dégradé, pré-enregistrer 1 prédiction falsifiable conditionnée à la phase (ex. `late → defensives surperforment cycliques sur 6m`) via le funnel `insert_prediction`, `methodology_version='cycle_v0'`. Résolue par le resolver existant → Brier de l'horloge.
- **panel render** : aiguille + bande + inputs auditables (déjà mocké dans la conversation — bande translucide, flèche de direction, jauges d'inputs avec as-of).

## 4. Inputs v0 (signe FIXÉ — ne jamais l'estimer)

| Input | Source probable | Signe vers late/contraction | Rationale |
|---|---|---|---|
| Courbe 2s10s | macro | inversion → late→contraction | classique fin-de-cycle |
| Spreads crédit HY (OAS) | macro | tight → late ; widening → contraction | compression = complaisance tardive |
| Largeur révisions BPA | révisions estimations | décélération de la largeur → pic | momentum fondamental qui roule |
| Conditions financières / liquidité | macro_state | resserrement → late | le robinet se ferme en fin de cycle |

Chaque input : z-score (vs son historique), multiplié par son **signe fixe**, pondéré par sa magnitude (estimée OOS), agrégé → angle. La magnitude est le SEUL degré de liberté estimé.

## 5. Logique de bande (le cœur honnête)

`band_width = f(désaccord entre inputs signés, erreur OOS réalisée à cette lecture)`. Large si les inputs divergent (courbe dit late, révisions disent pic) OU si l'historique montre un mauvais hit-rate à cette config. La confiance affichée = dérivée de la bande, jamais saisie.

## 6. Séquence de build (fait-pas-à-refaire d'abord)

1. `config/cycle.yaml` — signes + magnitudes v0 conservatrices + temporal_splits. (Standalone, immuable une fois figé.)
2. `cycle_calibrator.py` — compute + fail-closed + bande. (Pur, testable.)
3. table `cycle_readings` + helpers storage (append-only).
4. hook self-scoring (pré-enregistrement via funnel existant).
5. wire render panel.
6. tests verrouillants (§8).

## 7. Seams à VÉRIFIER avant de patcher (ne PAS deviner)

- **Inputs macro réels** : `grep` `macro_state.py` / `macro.py` — quels champs (courbe, spreads, liquidité) existent vraiment ? Si un input manque, le marquer `degraded` plutôt que l'inventer.
- **Funnel `insert_prediction`** (`shared/storage.py:850`) — réutiliser pour le self-scoring. Vérifier la signature (keyword-only `methodology_version`).
- **`config/calibration.yaml`** — copier la structure `audit_metadata.temporal_splits` (L16), ne pas réinventer.
- **Panel render** — repérer l'ancre/section où l'horloge s'insère (Vue d'ensemble ?), réutiliser les conventions OKLCH/`_styles`.
- **Resolver** — confirmer que `intelligence.learning resolve` résout les prédictions `cycle_v0` sans cas spécial.

## 8. Tests verrouillants (un par règle dure)

- `band` s'élargit quand les inputs divergent (construis 2 jeux : concordant → bande étroite ; divergent → bande large ; assert).
- **fail-closed** : <2 inputs frais → `angle is None`, `phase == 'insufficient'`, jamais d'aiguille.
- **pas de look-ahead** : le label de phase à T n'utilise aucune donnée datée > T (assert sur les splits).
- **signe contraint** : quelle que soit la magnitude estimée, un input ne peut pas inverser sa contribution directionnelle (assert sur le signe).
- **self-scoring wired** : un compute non-dégradé crée bien une ligne `predictions` `methodology_version='cycle_v0'` liée dans `cycle_readings.prediction_id`.

## 9. La phrase à garder en tête

Calibrer intelligemment cette horloge = lui **retourner la discipline déjà bâtie pour l'opérateur** : signes contraints par la théorie, magnitudes scorées contre l'outcome, splits temporels, bande gagnée, ré-estimation roulante, N emprunté en largeur, fail-closed sur désaccord. Pas un réglage manuel parfait — **un prévisionniste qui mérite son cadran.**
