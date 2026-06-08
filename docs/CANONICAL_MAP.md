# PRESAGE — CANONICAL_MAP (organisation navigation)

**Figé** : 07/06/2026 nuit++. Source de vérité unique pour le « où va ce nouveau code / cette nouvelle décision ». Pas de re-formulation ailleurs.

## Pourquoi cette carte existe

PRESAGE accumule des doctrines (L1-L21), des mécanismes (M1/M2/M3), des axes (1-5), des piliers (M-A/B/C/D), des composants (Integrity/Attribution/Valuation), des substrats (record/état/cache). Sans navigation canonique, on duplique, on perd 30 min à chaque "où ça va ?" et on contredit silencieusement la doctrine.

**Cette carte = 1 lieu unique** pour répondre à :
- Où va ma nouvelle fonctionnalité ?
- Quelle doctrine elle viole / sert ?
- Quel est son substrat (record / état / cache) ?
- Quels invariants doivent tenir ?

## 0. Le principe porteur — pourquoi le système est bon, et le reste en grandissant

> À relire avant **chaque** nouveau chantier. Tout le reste de cette carte n'est que l'application de cette seule idée.

Un système reste cohérent *en grandissant* uniquement si la cohérence est **structurelle** (imposée par les types + les gates + une source unique), jamais **comportementale** (tenue par la discipline). La discipline échoue — la preuve : `L1` (source unique) existe depuis le 01/06 et s'est violée quand même, sur 15 fichiers. **Un problème récurrent = une gate manquante, pas un manque de rigueur** (cf L27).

**L'image juste : une grammaire.** Règles fixes et peu nombreuses → phrases infinies, sans dérive. C'est la résolution de la tension *évolutif vs cohérent* : ce ne sont pas des opposés, **la contrainte en bas est ce qui donne la liberté en haut**.

- **Substrat rigide (la grammaire — 6 primitifs, pas 50)** : `Datum[Monetary]` (un type d'argent) · `Money.in_eur` (un convertisseur) · `book.value_eur → get_all_positions_views` (une source par fait, model + render) · `alert_vocabulary` (un vocabulaire) · `sector_profiles` (une taxonomie) · les **gates** qui rendent la violation non-compilable.
- **Surface fluide (les phrases — infinies)** : un nouveau stock JP/KR s'auto-classe et naît en Money natif qui se convertit proprement ; un nouveau panneau *compose* le vocabulaire et *projette* le cœur ; une nouvelle métrique dérive de Datums et hérite gratuitement du fail-closed + confiance. **Rien de neuf n'étend le langage ; tout compose le substrat.** La croissance ne dilue jamais la cohérence parce que chaque pierre ajoutée est faite de la même pierre (cf SPEC_SOCLE).

**Ce qui garantit que ça *reste* bon, pas seulement que ça le devienne une fois : la gate.** Sans elle, chaque feature suivante re-disperse (on rejoue le bug). Avec elle, le système **défend sa propre cohérence** — indépendamment de toute vigilance humaine ou agent.

**Les 3 mesures de « bon » (des tests, pas une impression)** :
1. **Minimal moving parts** — compte les primitifs. Si c'est 50 et pas 6, il dérive. Un fait = un endroit.
2. **Fail-closed** — droit de dire « je ne sais pas / stale / N insuffisant », jamais d'afficher un nombre plus confiant que son évidence. Un système qui ment poliment n'est pas bon, même joli.
3. **Self-defending** — l'incohérence ne *compile pas*. Si tu peux la casser sans build rouge, la gate manque.

Quand les trois tiennent, le système est bon — et le reste en grandissant, parce que la grammaire ne bouge pas pendant que les phrases se multiplient. Références : `SPEC_MONEY_INVARIANT` (§8 cœur unique) · `SPEC_ALERT_VOCABULARY` · `SPEC_SECTOR_TAXONOMY` · `SPEC_SOCLE` · LESSONS L1/L27/L28.

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
| **Polygon (ou Tiingo) wire** | Axe 5 redundancy | ⏸ **DEFER-with-triggers** (cf §5bis) | ~2h wire quand 1 des 3 triggers fire |

### 5bis. Triggers de bascule (chantiers gated par événement, pas par séquence)

Certains chantiers ne sont **pas séquencés** dans la roadmap — ils attendent un événement spécifique. Tant que le trigger ne fire pas, l'effort va ailleurs. Quand il fire, on bascule immédiatement (architecture déjà prête).

#### Polygon (ou Tiingo) — feed prix payant en fallback / redundancy

**Verdict actuel** (07/06/2026, single-user solo book 50k) : **pas maintenant**. Doctrine QUALITY_BAR Axe 5 explicite : « assumer near-live tant que single-user ; payer quand pro/multi-tenant ».

**Wire immédiat si UN de ces 3 événements arrive** :

1. **Incident yfinance ban concret** : un fetch fail prolongé (>4h sur 5+ tickers simultanés). Preuve que single-source = risque réel matérialisé, pas hypothétique.
2. **Passage multi-user / SaaS** (Phase 5 VISION_PRO §5.1-5.2) : la vérité doit être indépendante du compte gratuit d'un opérateur. La tolérance solo (« mon yfinance suffit ») ne tient pas quand on facture des clients.
3. **N_resolu > 100 + besoin spread freshness <15min prouvé** : seulement si la calibration prouve empiriquement qu'un edge dépend de freshness sub-15min. **Très improbable sur horizon long terme** (PRESAGE = 30-90j horizons), à ne pas activer en spéculation.

**Architecture déjà prête** (commit 9d8a50b et avant) : `price_history.source` field, `shared/prices.py` single gateway, data health panel affiche `Sources: yfinance×26` → affichera automatiquement `yfinance×20 polygon×6` quand wire fait.

**Effort de bascule estimé** : ~2h
- `shared/prices_polygon.py` adapter même API que `prices.py`
- `shared/prices.py::get_current_price` essaie polygon d'abord (si configuré), fallback yfinance
- Persist avec `source="polygon"` (schéma déjà supporté)
- Allowlist polygon import dans CI gate (`tests/test_doctrine_grep_gates.py`)
- Test cross-source consistency : delta >0.5% entre 2 sources → warning au panel

**Anti-pattern à refuser** : wire Polygon **proactivement** sans trigger. C'est exactement L19 violation (« sophistication tant que N<100 »).

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
