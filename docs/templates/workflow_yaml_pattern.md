# Workflow YAML pattern — canonical template

**Refresh** : 2026-06-07
**Source** : qlib `examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml` + Phase 1.5 absorption_roadmap.
**Doctrine** : `docs/LESSONS.md` L16 (splits temporels) + L17 (declarative configs en YAML, live state en DB, ne jamais mélanger).

## Quand utiliser ce pattern

Tout fichier qui :
- Influence des décisions du bot (caps, thresholds, watchlist, target allocation, kill-criteria)
- N'est PAS muté par un cron (= state déclaratif user, pas state live système)
- Mérite des commentaires inline pour audit humain (le pourquoi, pas le quoi)

Tout fichier qui EST muté par un cron → ne pas migrer en YAML. Soit garder JSON (round-trip mécanique), soit splitter en deux : YAML déclaratif + DB live state.

## Anatomie d'un workflow YAML

```yaml
# config/<nom>.yaml
#
# 1-3 lignes : à quoi sert ce fichier (rôle dans le système).
# Source de vérité (single point), lecteurs, fréquence de mise à jour user.

_meta:
  schema_version: 1                          # bump si breaking change
  declared_at: '2026-06-07'                  # date de déclaration initiale
  last_modified: '2026-06-07'                # date du dernier user-edit
  next_review_due: '2026-09-30'              # quand le user doit re-checker
  doctrine_refs:                             # liens vers règles transversales
    - 'docs/LESSONS.md L16 (splits temporels)'
    - 'docs/LESSONS.md L17 (declarative en YAML)'
  schema_module: 'intelligence.target_allocation_schema'  # Pydantic gate

# Bloc(s) métier. Commentaires inline pour audit.
positions:
  - ticker: 'ASML.AS'
    # Pourquoi ce ticker ici : 1 phrase qui survit aux 6 prochains audits.
    wrapper: 'PEA'
    amount_eur: 3930
    pct: 5.6
```

## Invariants verrouillés

1. **`_meta` block obligatoire** : `schema_version`, `declared_at`, `last_modified`, `next_review_due`, `schema_module`.
2. **Pydantic schema en module dédié** (ex `intelligence/target_allocation_schema.py`) avec `model_config = {"extra": "forbid"}`.
3. **Loader unique** : `shared/<nom>.py` `load_<nom>()` qui parse YAML + valide via Pydantic + cache + reset_cache helper.
4. **Test de régression** : un test `test_<nom>_yaml_schema.py` qui charge + valide + checke chronologie `next_review_due ≥ last_modified`.
5. **Pas d'écriture programmatique** : si un cron doit muter, c'est qu'on est dans le cas L17 « live state », pas dans ce pattern. Splitter.

## Workflow d'évolution

Quand le user veut modifier une valeur :
1. Éditer le YAML directement (ou via UI Telegram → écriture déclarative).
2. Bump `last_modified` à la date du jour.
3. Reset `next_review_due` à +6 mois par défaut.
4. Commit avec message `[config] <nom> : <delta court>` + bullet justification dans body.
5. CI valide via le test de schéma (sinon merge bloqué).

Quand le schéma lui-même change :
1. Bump `_meta.schema_version`.
2. Update Pydantic model + migration loader (compat schema_version: 1 et 2 le temps de la transition).
3. Drop la compat n−1 après ≥ 1 mois.

## Anti-patterns à refuser

- **JSON sans `_meta`** : impossible de savoir quand le fichier a été touché et par qui (au-delà de git blame).
- **YAML sans Pydantic** : commentaires soignés mais valeurs hors-bornes passent silencieusement.
- **Schema partagé entre fichiers** : couplage caché, un re-design d'un YAML casse l'autre. 1 fichier = 1 schema = 1 loader.
- **Loader qui « tolère » l'absence du fichier** : sauf si optionnel par contrat, l'absence doit raise fail-fast (L15).
- **Mutation par cron** : voir L17. C'est un live state, va dans une table DB append-only.

## Templates disponibles

| Fichier | Pattern | Schema | Loader |
|---|---|---|---|
| `config/calibration.yaml` | Thresholds + tooltips + classifier params | (legacy, dict access via `shared.calibration`) | `shared/calibration.py` |
| `config/target_allocation.yaml` | Allocation cible book | `intelligence.target_allocation_schema` | `shared/book.py::_load_target` |

Pour ajouter un nouveau workflow YAML, copier `config/target_allocation.yaml` + schema + loader + test, et adapter.

## Référencer

Depuis `CLAUDE.md` § "Catches récurrents" pointant vers L17 LESSONS. Pas de re-formulation ailleurs.
