# PRESAGE — CANONICAL_MAP (organisation navigation)

**Figé** : 07/06/2026 nuit++. Source de vérité unique pour le « où va ce nouveau code / cette nouvelle décision ». Pas de re-formulation ailleurs.

## Pourquoi cette carte existe

PRESAGE accumule des doctrines (L1-L21), des mécanismes (M1/M2/M3), des axes (1-5), des piliers (M-A/B/C/D), des composants (Integrity/Attribution/Valuation), des substrats (record/état/cache). Sans navigation canonique, on duplique, on perd 30 min à chaque "où ça va ?" et on contredit silencieusement la doctrine.

**Cette carte = 1 lieu unique** pour répondre à :
- Où va ma nouvelle fonctionnalité ?
- Quelle doctrine elle viole / sert ?
- Quel est son substrat (record / état / cache) ?
- Quels invariants doivent tenir ?

## 1. Les 4 niveaux d'abstraction

Du plus haut au plus opérationnel :

| Niveau | Source | Question répondue |
|---|---|---|
| **QUALITY_BAR** | `docs/QUALITY_BAR.md` | Quelle est la base non-négociable ? |
| **Mécanismes M1/M2/M3 + meta** | `docs/QUALITY_BAR.md` + L21 LESSONS | Comment opérationnaliser la base ? |
| **Axes 1-5** | `docs/QUALITY_BAR.md` | Quel chantier traiter quand ? |
| **Doctrines L1-L21** | `docs/LESSONS.md` | Quelle règle de réflexe sur ce point précis ? |

## 2. Les 3 substrats de données (par sémantique de mutabilité)

| Substrat | Caractère | Exemples | Storage pattern |
|---|---|---|---|
| **Record immuable** | append-only, jamais updated | `predictions`, `thesis_integrity_log`, `prediction_integrity_log`, `bias_events`, `conviction_history`, `llm_calls`, `price_history`, `fx_history`, `macro_regime_alerts`, `risk_signal_evaluations` | `INSERT only`, indexed `ORDER BY id DESC` ou `asof DESC` pour latest |
| **État courant mutable** | latest-wins, historique va ailleurs | `positions` (qty/avg_cost + M1 columns), `theses` (conviction → conviction_history append) | `UPDATE WHERE id=` + write to append-only history table |
| **Cache live / éphémère** | régénéré, TTL, jamais vérité | `_PX_CACHE`/`_FX_CACHE` RAM, dashboard.html | TTL ou mtime-based reload, jamais source |

**Règle de placement** : si une donnée est `f(prix)` → c'est **cache éphémère**, jamais persisté en colonne. Si c'est une décision T0 → **record immuable**. Si c'est l'état courant qui bouge sur événement → **état mutable + history**.

## 3. Les 5 axes QUALITY_BAR + leurs composants

| Axe | Composants livrés | Modules / configs | Doctrine principale |
|---|---|---|---|
| **1. Analyses & timing** | thesis_integrity_log + predictions chain + sondes 7j (TODO) | `shared/integrity.py` + `track_record/attribution.py` | L19 (N < 100 invariant) + L20 (scorer la décision) |
| **2. Lecture du marché** | sources monoculture flagged (TODO) | `intelligence/credibility.py` + `data_sources/` | L4 anti-double-instrumentation |
| **3. Positions / historique / futurs** | positions M1 columns + reconcile job + valuation function + integrity chain | `shared/storage.py` + `shared/valuation.py` + `scripts/reconcile_positions_prices.py` | **L21 M1 triple** + L17 declarative/live |
| **4. Concentration / sizing / ballast** | factor_exposures (déjà wired) + stress-test gate (TODO) | `intelligence/factor_exposures.py` + `config/target_allocation.yaml` | **L21 M3 sizing edge prouvé** |
| **5. Métriques & data** | freshness SLA + price_history + fx_history + CI gates | `config/freshness.yaml` + `shared/freshness.py` + `shared/prices.py` + `tests/test_doctrine_grep_gates.py` | **L21 M1 triple + L15 fail-closed généralisé** |

## 4. Décision : où va MA nouvelle fonctionnalité ?

Arbre de décision séquentiel :

```
1. Quel axe QUALITY_BAR est servi ? (1-5)
   ↓
2. Quel mécanisme ? (M1 datum / M2 claim / M3 sizing / meta fail-closed)
   ↓
3. Quel substrat ? (record / état / cache)
   ↓
4. Quelle doctrine ? (L# le plus spécifique)
   ↓
5. Où dans le code ?
   - `shared/`   : infra commune (storage, integrity, freshness, valuation, prices)
   - `track_record/` : DECISION_QUALITY_ENGINE (A integrity / B attribution / C base-rate)
   - `intelligence/` : business logic monitors / scorers / detectors
   - `config/`   : declarative YAML (L17)
   - `scripts/`  : one-shot / cron jobs / bootstrap
   - `dashboard/`: surface UI read-only
   - `tests/`    : test verrouillé pour chaque doctrine critique
```

## 5. Catalogue des chantiers actifs

| Chantier | Phase QUALITY_BAR | Statut | Suite |
|---|---|---|---|
| **DECISION_QUALITY_ENGINE A** integrity | Axe 1+3 | ✅ A0-A5 + bootstrap 26+219 | OTS install + cron daily anchor |
| **DECISION_QUALITY_ENGINE B** attribution 2x2 | Axe 1 | ✅ scaffold + 13 tests | wire `RealizedView` quand C ready |
| **DECISION_QUALITY_ENGINE C** base-rate Bigdata | Axe 1 | ✅ scaffold L15 gated | wire daloopa/bigdata connecteur |
| **M1 substrat positions** | Axe 3 + 5 | ✅ price_history + fx_history + columns + reconcile | cron 15min APScheduler + drop notes regex |
| **Sondes 7j calibration** | Axe 1 (P0.3) | ❌ pas lancé | front-load latence 8 semaines |
| **CI grep gates** | Axe 5 | ✅ yfinance + sqlite3 | doc-drift check P0.1 |
| **Doc-drift check** | Phase 0.1 | ❌ pas livré | regen LOC + tests count auto |
| **Stress-gate Axe 4** | Axe 4 (P0.4) | 🟡 calcul existe pas alerte | wire monitor pattern à transition |
| **Ballast cible** | Axe 4 | ❌ pas défini | définir % cible + flag si < |
| **Sondes monoculture sources** | Axe 2 | ❌ pas wire | corrélation inter-sources |
| **OTS install + cron daily anchor** | Axe 1 (A4 trustless) | ❌ scripts livrés, pas opérationnel | pip install opentimestamps-client |

## 6. Catalogue des doctrines (L1 - L21)

Vue rapide pour grep transversal. Source détaillée : `docs/LESSONS.md`.

| L# | Titre | Domaine |
|---|---|---|
| L1 | Source unique de vérité | Architecture |
| L2 | Ne pas bâtir affichage avant la donnée | UI |
| L3 | État honnête > contenu inventé | UI |
| L4 | Anti-double-instrumentation | Architecture |
| L5 | Fail-safe strict sur effets de bord | Architecture |
| L6 | Rituel de clôture | Process |
| L7 | Side-effects post-commit avec silent-miss explicite | Architecture |
| L8 | Test fixtures DB ≠ schema prod | Tests |
| L9 | Aucun comportement prod sans backtest | Validation |
| L10 | Débloquer friction visible avant rigueur différée | Sequencing |
| L11 | Anchors a priori = hypothèse à valider | Calibration |
| L12 | Devise native vs EUR interdit mélanger | Currency |
| L13 | Backtest rétrospectif plafonné par construction | Validation |
| L14 | Anti-patterns frameworks LLM-trading | OSS audit |
| L15 | **Fail-closed scoring** | Universel |
| L16 | **Splits temporels in-file** | Calibration |
| L17 | **Declarative YAML + live state DB** | Architecture |
| L18 | Munger latticework cross-disciplinaire | Doctrine pure |
| L19 | **Sophistication doit être justifiée par fondation** | Sequencing |
| L20 | **Outcome-graded ne suffit pas, scorer la décision** | Scoring |
| L21 | **QUALITY_BAR M1/M2/M3 + fail-closed généralisé** | **Meta-base** |

**En gras = doctrines structurelles, à consulter pour TOUT chantier non-trivial.**

## 7. Catalogue des templates / patterns canoniques

| Pattern | Source canonique | Quand l'appliquer |
|---|---|---|
| **Monitor pattern** | `docs/templates/monitor_pattern.md` | Nouveau detector à transition (over_cap, lock_in, factor concentration, stress) |
| **Workflow YAML déclaratif** | `docs/templates/workflow_yaml_pattern.md` | Nouveau config user-edited (target_allocation, risk_watch, freshness) |
| **Append-only journal** | Migration alembic + indices DESC | Tout event journal (alerts, integrity, evaluations) |
| **Triple M1 (value, asof, source)** | `shared/prices.py` + `shared/freshness.py` + colonnes typées | Tout input observable (prix, FX, fundamentals, macro) |
| **Pre-engagement hash chain** | `shared/integrity.py` | Toute claim future scorable (theses, predictions) |
| **Attribution 2x2** | `track_record/attribution.py` | Toute évaluation post-résolution |
| **OTS anchor trustless** | `scripts/integrity_anchor.sh` | Tout chain integrity qui doit être auditable par tiers |

## 8. Catalogue des invariants verrouillés en tests

Tests qui catch les violations structurelles (à NE JAMAIS laisser régresser) :

| Test | Catch | Doctrine |
|---|---|---|
| `test_positions_schema_has_no_eur_value_column` | bug fondateur eur_value en colonne | L21 M1 |
| `test_coherent_rebuild_caught_ONLY_by_external_anchor` | A4 OTS non-optionnel | L21 M2 |
| `test_verify_chain_detects_payload_mutation` | tamper-evidence niveau 1 | L21 M2 |
| `test_no_new_yfinance_bypass` | shared/prices.py single gateway | L21 M1 axe 5 |
| `test_no_new_sqlite3_bypass` | shared/storage.py passerelle | L1 + L21 |
| `test_calibration_temporal_splits_present` | re-tune anti in-sample | L16 |
| `test_canonical_raises_on_non_primitive` | hash reproducible | L21 M2 |
| `test_unattributable_blocks_fabricated_skill` | refus story fabriquée | L20 + L21 meta |
| `test_luck_quadrant_outcome_good_but_wrong_reason` | LUCK distinct SKILL | L20 |

## 9. Workflow standard pour ajouter une nouvelle fonctionnalité

```
1. RELIRE docs/QUALITY_BAR.md (la base)
2. IDENTIFIER axe + mécanisme + substrat (cf section 4)
3. CHERCHER doctrine L# applicable (cf section 6)
4. CHERCHER pattern canonique (cf section 7)
5. CHERCHER test verrouillé existant (cf section 8) -- évite régression
6. CODER conforme + test invariant nouveau si applicable
7. COMMIT message inclut : doctrine référencée + axe + substrat
8. METTRE À JOUR ce CANONICAL_MAP.md si nouveau pattern / chantier
```

## 10. Règle de mise à jour de cette carte

Cette carte est **vivante**. Mise à jour requise quand :
- Nouvelle doctrine L# inscrite dans LESSONS.md
- Nouveau pattern canonique dans `docs/templates/`
- Nouveau chantier majeur démarre
- Test invariant structural ajouté

**Pas de mise à jour requise** pour : commits ad-hoc, refactors locaux, bug fixes.

## Référencer

Source unique : `docs/CANONICAL_MAP.md`. Pointage depuis `CLAUDE.md` § "Navigation". Pas de re-formulation ailleurs.
