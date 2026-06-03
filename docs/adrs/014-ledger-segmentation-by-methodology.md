# ADR 014 — Ledger segmentation par methodology_version (canonical vs shadow/fallback)

**Status**: Proposed (03/06/2026)
**Related**: ADR 008 (LLM Cascade), `intelligence/scoring_orchestrator.py` (#94 a venir), `shared/storage.py:canonical_predictions_query()`, mémoires [[resilience_architecture_spine]] / [[degraded_restitution_contract]]

## Context

Spec user 03/06 (résilience LLM #93-#96) introduit des prédicteurs **multiples** sur le même signal :

| Tag `methodology_version` | Origine | Rôle épistémique |
|---|---|---|
| `v2` | LLM Sonnet (signal_scorer_v2 existant) | Prédicteur canonique courant |
| `rule_v1_shadow` | RuleScorer déterministe, LLM up | Challenger paired pour mesurer "LLM ajoute N pts Brier vs baseline gratuit" |
| `rule_v1_fallback` | RuleScorer déterministe, LLM down | Plancher de fonctionnement quand l'API ne répond plus |
| `v0`, `v1` | Cohortes archivées | Quarantaine (déjà segmentées : `methodology_version != 'v0'` partout) |

Ces prédicteurs **résolvent sur le même outcome**. Sans ségrégation explicite à la lecture, les Brier des familles différentes se mélangent dans le KPI #3 et le panneau calibration vigie → calibration headline pollute, comparaisons LLM-vs-rule devient impossible à articuler.

Le user a explicitement banni le commingling :

> "Brier calcule PAR methodology_version. Deux pistes separees. KPI #3 et calibration panel filtrent sur LLM methodo par defaut. Rule-based a sa propre ligne. JAMAIS commingled dans Brier headline."

## Decision

**Ségréger structurellement** le ledger predictions à la lecture, **pas à l'écriture**.

### 1. Source unique de vérité : `shared/storage.canonical_predictions_query()`

Une fonction unique qui retourne le SELECT canonique des prédictions qui comptent dans le Brier / KPI #3 / calibration headline. Tous les consommateurs canoniques (morning_brief KPI #2, monthly_track_record, calibration_audit, J-day batch, panneau vigie) **doivent** passer par cette fonction. Aucune query SQL parallèle qui dérive.

### 2. Définition canonique courante

```sql
WHERE methodology_version NOT IN ('v0', 'v1', 'rule_v1_shadow', 'rule_v1_fallback')
```

- `v0` : cohorte 12/05 quarantined (hardcoded horizon=30, pré-pivot)
- `v1` : pré-pivot mono-bucket (déjà filtré dans les invariants tests)
- `rule_v1_shadow` : challenger paired, mesuré séparément
- `rule_v1_fallback` : plancher dégradé, mesuré séparément

→ Reste : `v2` (LLM Sonnet) = ledger canonique 2026.

### 3. Queries dédiées par famille

`shared/storage.brier_by_methodology(methodology_version: str)` retourne le Brier moyen par famille séparément. Utilisé pour `/shadow_compare`, `/methodology_status`, et toute lecture qui veut un Brier `rule_v1_*` explicitement.

### 4. Pattern existant à étendre

Le filtre `methodology_version != 'v0'` est déjà appliqué dispersé (`tests/test_predictions_pipeline_invariants.py`, `bot/handlers/observability.py`, `intelligence/morning_brief.py`). On **centralise** dans `canonical_predictions_query()` et on supprime les filtres locaux par PR séquentiel quand les consommateurs sont migrés. Pattern symétrique à `classify_position()` (source unique de vérité pour appartenance de famille).

## Rationale

**Pourquoi structurellement et pas par revue ?**

Commingler les Brier de familles de prédicteurs différentes invalide la calibration :
- Le `rule_v1_*` a sa propre distribution de probabilités (déterministe, ~plat sur 0.3-0.7).
- Le `v2` a la sienne (LLM, parfois mono-bucket comme V1 si scorer drift).
- Mélanger les deux dilue la mesure : ni l'un ni l'autre n'est représenté correctement.

L'incident V1 mono-bucket (mai-juin 2026) prouve l'effet en miroir : le Brier headline était dominé par V1 plat → impossible de voir si V2 calibrait mieux tant que les invariants ne filtraient pas V1 explicitement. Même piège attend si shadow/fallback s'invitent dans le headline.

**Pourquoi ségrégation à la lecture, pas à l'écriture ?**

- Les prédictions de toutes familles **résolvent identiquement** (price hit target/stop, neutral, etc.). Le code de résolution est partagé.
- Stocker dans une table séparée pour shadow/fallback dupliquerait le schéma + le triggers + le wire de résolution. Coût élevé, valeur nulle.
- Une seule colonne `methodology_version` + une seule query canonique = source unique, minimum de duplication. Pattern Rails-de-vérité.

## Consequences

### Impact downstream (migration séquentielle)

| Surface | Changement | Effort | Priorité |
|---|---|---|---|
| KPI #2 morning_brief | Remplacer `methodology_version != 'v0'` par `canonical_predictions_query()` | 10 min | High (pré-J-day) |
| KPI #3 calibration_audit | Idem | 10 min | High (pré-J-day) |
| J-day batch `bot/jobs/j_day.py` | Idem | 10 min | High (10/06) |
| monthly_track_record snapshot | Idem | 10 min | Medium |
| Panneau vigie calibration | Idem | 10 min | Medium |
| `/methodology_status` Telegram | Nouveau handler exposant `brier_by_methodology()` | 30 min | Low (post-#94) |
| `/shadow_compare` Telegram | Lecture paired Brier(v2) vs Brier(rule_v1_shadow) | 1h | Low (post-#96) |

### Non-objectif

- **Pas un ranking inter-méthodologie.** Chaque famille sur sa piste. Le delta Brier(v2) - Brier(rule_v1_shadow) est un **indicateur de valeur ajoutée du LLM**, pas une compétition d'élection du "meilleur".
- **Pas de réécriture du schéma** predictions. La colonne `methodology_version` existe déjà.
- **Pas de fix retroactif** des prédictions V1/V0 archivées. La quarantaine reste.

## Implementation

### Step 1 — `shared/storage.canonical_predictions_query()`

```python
def canonical_predictions_query(extra_where: str = "", params: tuple = ()) -> str:
    """SELECT canonique pour Brier / KPI #3 / calibration headline.

    EXCLUSIONS canoniques :
    - 'v0' : cohorte quarantine 12/05 (horizon=30 hardcode)
    - 'v1' : pré-pivot mono-bucket
    - 'rule_v1_shadow' : challenger paired, mesuré séparément via brier_by_methodology
    - 'rule_v1_fallback' : plancher dégradé, mesuré séparément

    Returns le fragment WHERE composable. Caller ajoute SELECT/FROM/ORDER BY.
    """
```

### Step 2 — `shared/storage.brier_by_methodology(methodology_version)`

Retourne `{n_total, n_scored, brier_avg, brier_dedup_avg}` pour une famille spécifique. Source unique pour `/methodology_status` et `/shadow_compare`.

### Step 3 — Tests invariants

- Test : `canonical_predictions_query()` exclut `rule_v1_shadow` + `rule_v1_fallback` + `v0` + `v1`.
- Test : Brier headline (via KPI #3) ne contient AUCUNE prédiction `rule_v1_*` même si shadow_scoring_enabled=True.
- Test : `brier_by_methodology('rule_v1_shadow')` ne contient AUCUNE prédiction `v2`.
- Test : COMPUTED/RETRIEVED panneaux dashboard byte-identiques entre LLM up et LLM down (cf [[degraded_restitution_contract]] invariant 3).

### Step 4 — Migration des consommateurs

Un PR par consommateur, dans l'ordre Priorité High → Low. Le filtre local actuel `methodology_version != 'v0'` est remplacé par l'usage de `canonical_predictions_query()`. PR atomiques pour pouvoir mesurer l'impact via diff vs avant.

## Validation

- **Quand** : ADR Accepted dès que `canonical_predictions_query()` + tests invariants shippés et au moins 2 consommateurs critiques (KPI #2, KPI #3) migrés.
- **Comment mesurer** : avant/après migration, le compteur de prédictions Brier-éligibles doit être identique (zero `v0`/`v1`/`rule_v1_*` qui entraient pollutivement). Si le compteur change, c'est qu'un filtre local était plus permissif que la query canonique → décision : aligner ou documenter exception.

## Lien avec architecture résilience

Cette ADR est le **prérequis dur** de :
- **#94** (Surface mode dégradé) — RuleScorer émet `rule_v1_fallback`, doit être exclu canonique.
- **#96** (Champion-Challenger Shadow) — RuleScorer émet `rule_v1_shadow`, doit être exclu canonique + comparable via `brier_by_methodology()`.

Sans cette ségrégation explicite, #94 et #96 contamineraient le ledger canonique et invalideraient KPI #3 + J-day Brier batch.

## Future-self note

Si une nouvelle famille de prédicteur arrive (ex: `llm_v3`, `embedding_v1`, `ensemble_v1`), **ajouter à `canonical_predictions_query()` EXCLUSIONS si non-canonique**, ou la migrer comme méthodologie canonique courante (déprécation explicite de `v2` documentée dans l'ADR successeur).

## Disambiguation rule — Scope du filtre canonique (ajout 03/06)

Question découverte pendant la migration consommateurs (#95 phase 2) : la session a brièvement appliqué `canonical_predictions_filter()` au rapport J-day batch 10/06. Or **le J-day est le wrapup de la famille V1** — y appliquer le filtre canonique (qui exclut V1) le transforme en silent zero "0 prédiction résolue" alors que 35 le sont. Bug interdit par CONVENTIONS #6 et la doctrine [[degraded_restitution_contract]].

**Règle disambiguation explicite** :

| Type de surface | Filtre méthodologie | Exemples |
|---|---|---|
| **Forward-headline public** (track record public, KPI #2 forward forecast, calibration audit) | `canonical_predictions_filter()` | `intelligence/track_record_aggregator.py`, `intelligence/track_record_timeseries.py`, `dashboard/render.py:_track_record_panel`, `bot/handlers/observability.py:kpi2`, `intelligence/calibration_audit.py` |
| **Archive-report sur une famille spécifique** | `methodology_version = '<famille>'` explicite + provenance marker | `bot/jobs/j_day.py` (V1), `dashboard/render.py:_discipline_biais_panel` (V1 batch 10/06) |
| **Substance accounting interne** (outils opérationnels, scorer inputs, internal audit) | `methodology_version != 'v0'` (exclut quarantine uniquement) | `intelligence/base_rates.py`, `intelligence/outcome_context.py`, `intelligence/v2_vigilance.py`, `intelligence/portfolio_grade.py`, `intelligence/thesis_track_record.py`, `intelligence/morning_brief.py`, `bot/handlers/prediction_why.py`, `dashboard/render.py:_loop` |

**Principe** : "non-canonical" signifie **"pas dans le headline public"**, **jamais "invisible"**. Une famille archivée (V1, futur V2 → V3) garde son propre rapport explicite avec provenance marker `"famille X, exclue du headline canonique"`. Les surfaces de substance accounting voient toutes les familles non-quarantine pour ne pas trahir l'activité réelle.

**Corollaire forward-headline N=0** : quand le filtre canonique retourne 0 (typiquement v2 pas encore tiré), la surface DOIT rendre **"v2 pas encore démarré"** explicitement (status `PRE_LAUNCH` dans aggregator, message clair dans le panneau), **jamais 0/0 muet**. Sinon on déplace le bug (B) du J-day vers le headline.

**Future retirement (V2 → V3 someday)** : quand V2 sera déprécié vers V3, refaire cet exercice : ajouter V2 dans `CANONICAL_METHODOLOGY_EXCLUSIONS`, créer un V2-archive report explicite, garder `!= 'v0'` sur le substance accounting (qui inclura alors V2 + V3 actifs).
