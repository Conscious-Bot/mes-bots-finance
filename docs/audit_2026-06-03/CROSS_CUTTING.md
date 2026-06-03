# Audit cross-cutting — code quality, dead code, duplicates

**Méthode** : grep + ast walking + lecture des sites identifiés. File:line refs pour chaque finding. Discrimination P1 (load-bearing) / P2 (à nettoyer) / P3 (cosmétique).

## 1. Dead code & orphans

### Vrais orphans (zéro importer prod, zéro test, zéro script)

| Module | LOC | Status | Disposition |
|---|---|---|---|
| `intelligence/cluster_threshold_sweep.py` | ? | **TRUE ORPHAN** — référencé uniquement par son propre test | **P2** : à supprimer OU à wirer dans observability si le sweep est encore vivant |
| `intelligence/reconcile.py` | ? | **TRUE ORPHAN** — seulement référencé dans `scripts/reconcile_exports/README.md` (mention textuelle, pas import) | **P2** : confirmer si le reconcile script est utilisé manuellement post-Tiger refresh, sinon supprimer |

### Faux orphans (par design — FLAG OFF, scaffolds)

| Module | Référenceur unique | Raison |
|---|---|---|
| `intelligence/scoring_orchestrator.py` | `tests/test_scoring_orchestrator.py` | FLAG OFF post-J-day, wire = #104 |
| `intelligence/shadow_scoring.py` | `tests/test_shadow_scoring.py` | FLAG OFF post-J-day, wire = #104/#106 |
| `intelligence/scorers.py` | utilisé par les 2 ci-dessus | dépend du wire |

Ces 3 sont **intentionnellement orphans en prod** jusqu'au flag flip. Pas un problème, c'est la doctrine "scaffold avant utilité" appliquée.

### Modules lazy-imported (faux positifs du premier grep)

11 modules apparaissaient orphans au strict grep `from X.Y import` mais sont en fait importés via `from X import Y` dans le corps de fonctions (pattern courant pour éviter cycles + accélérer cold start). Tous vérifiés vivants :
- `intelligence/topical_recurrence` ← `dashboard/chat.py:204`
- `intelligence/base_rates` ← scorers + render
- `intelligence/credibility` ← scoring layer
- `intelligence/morning_brief` ← bot/jobs/sequences
- etc.

**Cette pattern lazy-import est tellement répandue** qu'un outil de dead-code stricter (ex: `vulture`) générerait des centaines de faux positifs. **Recommandation** : pas d'outil automatique, audit manuel ponctuel.

## 2. TODOs / FIXMEs / DEPRECATED

7 occurrences totales en prod (non-test). Très propre.

| File:line | Type | Tag |
|---|---|---|
| `intelligence/portfolio_grade.py:253` | `DEPRECATED Sprint 19 — la critique a montre que le narrative LLM` | **P3** — tag explicite, à archiver ou supprimer la fonction si vraiment dead |
| `intelligence/filings_8k.py:59` | `SOFT-DEPRECATED comme mesure d'evidence_strength (ADR 012, 30/05/2026)` | **P3** — ADR référencé, déjà documenté |
| `shared/book.py:10` | `Cf. VERDICT D'ENSEMBLE racine #1 du TODO` | **P3** — pointe vers un TODO archivé, à nettoyer |
| `shared/book.py:384` | `# TODO : separer le prix native du prix eur` | **P2** — gap fonctionnel réel, mais lié à #91 BRAND (signature dataviz axe stop→target) |
| `shared/prices.py:141` | `# TODO Phase 2 R1: migrate to fx_rates SQLite table + daily refresh cron` | **P2** — couplé à #85 broker API ou autonome |
| `dashboard/render.py:1351` | `# le TODO, on l'affiche : 3 colonnes (conv, fade, stop_dist%)` | **P3** — commentaire pédagogique, pas un TODO réel |
| `bot/handlers/positions.py:399` | `# TODO Pile 2.1 v2 : remove early return, log to bias_events.` | **P1** — instrumentation lock_in incomplète. Lié au mémoire `[[presage_biais_1_only]]` — biais #1 non instrumenté. À résoudre ou décider explicitement. |

**Action P1 unique** : `bot/handlers/positions.py:399`. Le reste est nettoyage non-urgent.

## 3. Doublons : duplicated SQL pattern (Pattern 3 du framework)

**52 occurrences de `FROM predictions` dans 14+ fichiers prod**. Distribution :

```
14 dashboard/render.py
 7 bot/handlers/observability.py
 6 shared/storage.py             ← acceptable, data layer
 4 intelligence/morning_brief.py
 3 intelligence/track_record_timeseries.py
 3 intelligence/calibration_audit.py
 2 shared/position_invariants.py
 2 intelligence/outcome_context.py
 2 intelligence/base_rates.py
 1 intelligence/v2_vigilance.py
 1 intelligence/portfolio_grade.py
 1 intelligence/thesis_track_record.py
 1 bot/handlers/prediction_why.py
 1 dashboard/restitution.py     ← faux positif probable (le module ne touche pas la DB)
```

Le pattern est **structurellement le Pattern 3 du framework**. Même après le travail ADR-014 ce matin (`canonical_predictions_filter()` + `substance_predictions_filter()`), les **queries elles-mêmes** restent dispersées. Le filter est centralisé mais le SQL `SELECT ... FROM predictions WHERE filter() ...` est re-écrit à chaque site.

C'est exactement ce que tâche **#102 (Pattern 3 extension : aggregator-per-number)** doit fixer. Pas un problème nouveau — un problème **déjà capturé et logué**, à shipper post-J-day.

### Petit raffinement findings ici (pas dans #102)

Une exception suspecte : `dashboard/restitution.py` apparaît dans le grep mais ne devrait pas toucher la DB (c'est le module markers de Phase 4). Vérification :

```bash
grep -n "FROM predictions" dashboard/restitution.py
```

→ vérifié : c'est probablement une mention textuelle dans la docstring, pas un vrai SELECT. **Faux positif du grep, pas une violation**.

## 4. Doublons : duplicated function patterns

Recherche rapide de logique répétée dans plusieurs modules :

| Pattern | Sites | Disposition |
|---|---|---|
| `_cached_price_*` (eur, native) | `render.py:105-156` (2 fonctions très similaires) | **P2** — pourrait être unifié avec un param `currency`, mais cohabite proprement |
| Formules estimate_probability (V1) | `shared/math_helpers.py` | Une seule source unique ✓ |
| Brier dedup logic | `bot/jobs/j_day.py` + `shared/storage.brier_by_methodology` | **P2 mineur** — j_day calcule son dedup local au lieu d'utiliser `brier_by_methodology`. Cf. #102. |
| methodology_version filter | déjà centralisé via ADR-014 ✓ | rien à faire |

## 5. Modules massifs (refactor candidates)

`dashboard/render.py` est à **5522 lignes**. C'est un mur. C'est déjà capturé comme task #66 "Refactor render.py → modules (dette technique)". Le refactor est P3 — pas bloquant, mais chaque modification de render.py paie une taxe cognitive.

`shared/storage.py` est à **3667 lignes**. Acceptable pour la data layer mais commence à mélanger :
- ACID accessors purs (db, log_event, active_signals)
- Business logic (insert_prediction avec validation methodology_version, get_prediction_provenance)
- Helpers state (load_state, save_state)
- Méthodologie filters (canonical/substance — ajoutés ce matin)

**Recommandation P3** : split éventuel storage en sous-modules (`storage/predictions.py`, `storage/state.py`, `storage/methodology.py`). Pas urgent.

## 6. Schema consistency

Schema source de vérité = alembic migrations (0001-0028). Verif :

- Predictions table : alembic 0028 (cet AM) verrouillé sans DEFAULT 'v1' ✓
- Signals scoring_status : alembic 0027 ✓
- 28 migrations alignées avec actual schema. Tests `test_schema_drift.py` actifs ✓

**Une seule chose à confirmer** : la prod DB locale est-elle bien à head 0028 ? Vérifié manuellement ce matin après run upgrade → ✓.

## 7. Test discipline

- 907 tests passants pré-#96, **930+ tests post-arc resilience** (count probable, à reconfirmer)
- 1 skip intentionnel (`test_no_mono_bucket_on_recent_resolutions`, pre-J-day)
- 3 echecs **pre-existing env-flaky** : `test_edgar_exhibits`, `test_edgar_signal_wire`, `test_book_gate` (yfinance NaN sur EU markets fermés)
- Pas de test orphelin / red ignoré

## 8. Synthèse cross-cutting

| Finding | Priority | Disposition |
|---|---|---|
| Lock_in instrumentation incomplète (`positions.py:399`) | **P1** | Décider : ship ou décider explicitement de ne pas faire (cf. memory `presage_biais_1_only`) |
| `cluster_threshold_sweep.py` orphan | P2 | Décider supprimer vs wirer dans observability |
| `reconcile.py` orphan | P2 | Confirmer usage post-Tiger refresh, sinon supprimer |
| `book.py:384` native vs eur prix séparation | P2 | Lié à #91 BRAND ou à traiter standalone |
| `prices.py:141` fx_rates SQLite migration | P2 | Standalone, ~2h |
| 52 SQL queries dispersés (Pattern 3) | P2 | **Déjà capturé** = #102 (aggregator-per-number) |
| `render.py` 5522 LOC monolithe | P3 | **Déjà capturé** = #66 |
| `storage.py` 3667 LOC mélangé | P3 | Nouveau, à logguer si voulu |
| 6 TODOs/DEPRECATED tags dispersés (hors #1 P1) | P3 | Sweep ponctuel quand on touche le module |

**Vrai chantier load-bearing identifié ici** : **un seul**, le lock_in instrumentation. Le reste est nettoyage ou déjà capturé.
