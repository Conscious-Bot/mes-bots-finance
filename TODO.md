# TODO — PRESAGE (mes-bots-finance)

**Refresh** : 12 juin 2026 close (c+) — élagage intelligent : #133bis + #146 + #132 + #128 + #121 + #148 tous fermés (la moitié étaient déjà faits, TODO périmée)
**Mode** : **FOUNDATION FIRST. AUDITABLE PAR ADVERSAIRE.** Capstone red-team nuit++ accepté.
**Historique** : `SESSION_STATE.md` (sessions chronologiques) · `/tmp/TODO_pre_pruning_*.md` (snapshots pré-élagage)

---

## 🟢 ÉTAT SYSTÈME (12/06 close c+)

- **CI green sur `7094ba6`** — premier success depuis 08/06
- **Bot launchd** : `com.olivier.presage` auto-restart `KeepAlive=true` (PID 51942, plist depuis 31/05) → #148 déjà résolu, watchdog en place
- **Seam gauge** : `_position_axis_price` est l'unique canonique (4 callers migrés). Plus de `_position_axis` legacy → #121 déjà résolu
- **SQL-direct positions sweep** : `get_open_positions()` migré BookLine, fix les 3 callers (snapshot quotidien + position_view + portfolio_views handler) d'un coup → #132 fermé
- **M10 Taleb barbell** : vivant 33.4% mou (après cure source `book.get_held_lines()`) → #133bis fermé
- **Telegram parse_mode** : `_underscores_` plus de parsing fail sur 2 push erosion → #146 fermé
- **SK Hynix banner proxy** : `pc-proxy-banner` déjà wired dans card + book row → #128 fermé
- **Track-record alpha** : 10 paris posés, résolution 1re due 2027-06-10 (CCJ)
- **KLAC** : yfinance restauré (241 USD = ÷10 du bug 2411). Cure outlier reste comme filet.

---

## 🔴 P0 ACTIONNABLES

### Fresh-head requis

1. **#134 monitor `stale_target`** (~1h30) : 3e monitor via `docs/templates/monitor_pattern.md`. Trigger sur dégradation : `classify` retourne `dead` si `cost ≥ target`, `dying` si `(target − cost)/cost < seuil_edge`, `alive` sinon. Surface alerte sur transition. NE PAS auto-recompute target ([[L30]] anti-piège). Le 3e monitor doit être 3× plus rapide que le 2e parce que le pattern est figé.

2. **KLAC niveaux à reposer** : entry/stop/targets posées pendant bug yfinance 11/06 (prix 1626 USD = 6× le réel 241). Le gate `currency_native` détecte hors-range [0.3, 3.0]. Action humaine, pas code — relit thèse + repose niveaux ancrés sur 241 USD réel. Cas-école pour la méthode #135.

---

## 🟡 P1 DIFFÉRABLE

- **#133 sweep cibles batch suivant** (~2-3h étalées) : 10 positions targets/stops révision (4063.T, AMZN, AVGO, KLAC, 7011.T, 6857.T morts ; 6920.T, TSLA, LNG, MP mourants). Méthode 3 colonnes (Instrument / Ancre externe live / Ressenti) → `docs/sweep_targets_2026-06.md`. Born-dead-check obligatoire. Pré-condition idéale : #134 livré (priorise alive→dying→dead).

- **#135 refonte complète niveaux décidés** : projet structural étalé 2-3 mois, ~1 ticker/semaine. Méthode canonique : ancre externe live consensus/multiples/52w/news + décision humaine + born-check (partial > cost ET > cur · full > partial · stop reconsidéré aussi) + trace `asof + raison 1 ligne`. Doctrine élargie : stop inclus dans la révision (pré-rally peut devenir absurde).

- **#145 LIVING_GRAPH forks `pnl_position`** : 4 tickers (000660.KS×2.5, 7011.T×1.9, AMD 16%, ASML.AS 18%) divergent helper (`value-cost`) vs view (`value/cost`). DAG fait son travail. À résoudre au prochain pivot compute-once-project (cf [[L29]]).

- **#147 Tests flaky ordering-dependent** : `test_aggregate_sum_equals_parts` + `test_coherence_under_perturbation` passent isolément, fail au full-run. Pollution état partagé. Diagnostic : probablement DB temp réutilisée ou cache statique non-clean. ~1h diag.

- **Cure structurelle tests CI-fresh DB** : 7 tests utilisent `skip-on-OperationalError` (cure aujourd'hui pour débloquer CI). Vraie cure = migrer ces 7 tests vers fixture `migrated_db` canonique. À faire en lot. ~1h.

---

## 🎯 VISION_PRO LONG-TERME

Roadmap chronologique complète : cf `docs/VISION_PRO.md` + `docs/DECISION_QUALITY_ENGINE.md`.

**Critère nord unique** : auditable par un adversaire. Une due-diligence hostile peut-elle falsifier ou vérifier chaque nombre ?

**Wedge actuel** (cf [[business-path-6-acted]]) : Path 6 lifestyle solo + track record public + petite audience. Discipline mécanisée (pas alpha prédictif). Phase actuelle = nourrir l'instrument (poser plus de paris, accumuler résolutions), pas raffiner la mesure (cf [[feedback_instrumentation_vs_decision]]).

**3 plafonds structurels à percer** (calibration sur outcomes ne les perce pas) :
- Auto-référentiel (l'opérateur note l'opérateur) → pré-engagement tamper-evident OTS-ancré ✅ LIVRÉ
- Petit-n (N=35, latence 30j) → process-grading + outside-view
- Outcome-graded (Brier ignore quadrant LUCK) → attribution causale 2×2

**FUTURE backlog vague** (réactivé si signal externe explicite) : #73 Cap par conviction post-N≥30 · #74 Drawdown gate cluster · #88 M2 Brier-scorer thesis_erosion · #89 Skip-already-classified · #92 consensus projection · #94 Cornerstone C5 divergence · #99 Update HANDOFF_MASTER · #119 switch currency UI

---

## ⛔ HISTORIQUE FERMÉ (référence)

Sections supprimées de cette TODO (réduit le bruit, infos consolidées dans SESSION_STATE) :

- **SOCLE S0/S1a/S1b/S1c/S2/S3** (tous LIVRÉS 09-11/06) : OTS anchor, Datum primitif, gateways Datum, migration positions VUE, base_health.py vert
- **PIVOT FONDATION 08/06** : reconstruction doctrine en suspens → SOCLE livré, pivot résolu
- **5 positions KNOWN-GAP partial close** : réconciliées via `rebuild_tr_ledger_from_csv.py` (cf #127 closed) + ledger transactions append-only (#125 livré)
- **QUALITY_BAR sweep 4 axes** (07/06) : axe 3/5/4/2 livrés, axe 1 gated invariant N<100
- **CORRECTIVE QUEUE v2 (07/06)** : ré-évaluée, infos consolidées dans #134+#135

Pour le détail, voir `SESSION_STATE.md` (entries `## Close 2026-06-XX`).
