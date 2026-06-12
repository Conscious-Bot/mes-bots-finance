# TODO — PRESAGE (mes-bots-finance)

**Refresh** : 12 juin 2026 close (c) — quick wins #133bis (M10 Taleb cure source) + #146 (Telegram parse_mode) + #128 verified · TODO élaguée 1245→94 · CI restauré green (commit 7094ba6 — premier success depuis 08/06)
**Mode** : **FOUNDATION FIRST. AUDITABLE PAR ADVERSAIRE.** Capstone red-team nuit++ accepté.
**Historique** : `SESSION_STATE.md` (sessions chronologiques) · `/tmp/TODO_pre_pruning_*.md` (snapshots pré-élagage) · sections SOCLE/PIVOT FONDATION supprimées (livrées 09-11/06, cf SESSION_STATE Close 11/06)

---

## 🟢 ÉTAT SYSTÈME (12/06 close c)

- **CI green sur `7094ba6`** — premier success depuis 08/06 (4 commits successifs : ruff lint sweep + mypy typing + 7 tests data-dependent skip-on-fresh-DB)
- **Quick wins #133bis livré** : M10 Taleb barbell redevient vivant (33.4% mou, c5=33% c1=0%) après migration SQL-direct → `book.get_held_lines()`. Diagnostic : 26/26 positions ont `avg_cost_eur=NULL` (normal post VUE), seul M10 lisait SQL-direct.
- **Quick wins #146 livré** : 24× Telegram entities parsing fix via `parse_mode=None` sur 2 push erosion.
- **#128 SK Hynix banner proxy** : déjà wired (`pc-proxy-banner` + chip `·proxy` visibles dans HTML rendu).

## 🟢 ÉTAT SYSTÈME (12/06 close b)

- **alembic_version** : 0055 (registre append-only per-classe figé session 12/06 matin)
- **Tests** : 1840 passed, 2 flaky ordering-dependent (`test_aggregate_sum_equals_parts::test_portfolio_value_aggregate_equals_sum_views` + `test_coherence_under_perturbation::test_other_tickers_unaffected_by_perturbation` — passent isolément), 2 skipped
- **Bot status** : tourne (PID 51942 depuis 12/06 08:13)
- **Dashboard live** : `http://127.0.0.1:8000/dashboard.html` — 100% EN strings (sweep commit `b444e67` + `lang="en"` commit `7736d86`)
- **SOCLE base_health** : GREEN (M1 blindé contre outliers feed via cure #144 v2 boundary `prices.get_current_price`)
- **Track-record alpha** : 10 paris posés (SK + CCJ + 8 du 12/06 matin), résolution 1re due 2027-06-10 (CCJ)
- **KLAC fail-closed actif** : ~~yfinance feed cassé 11/06~~ → restauré ~3h après mes cures (241.16 USD = ÷10 du 2411.64 bug). Cure 2 source reste comme filet pour la prochaine fois.

---

## 🔴 P0 ACTIONNABLES

### Quick wins (~15-30min chacun, fresh-head pas requis)

~~1. ~~**#133bis CCJ trous DB**~~ — RÉSOLU 12/06 (commit `c91c364`) : NULL en DB est par construction depuis migration positions VUE. Vrai bug = `thesis_health_metrics.M10_Taleb_barbell` lisait SQL-direct et retournait toujours "book vide". Cure : migrer M10 vers `book.get_held_lines()`. M10 désormais vivant (33.4% mou).

~~2. ~~**#146 Telegram entities parsing**~~ — RÉSOLU 12/06 (commit `d50633b`) : 2 push erosion (`thesis_erosion.py:334+490`) passés en `parse_mode=None` plain text. Cause = `_underscores_` dans `EROSION_DETECTED`/`INVALIDATION_HIT`/`integrity_seq` que Telegram parsait comme italic non fermé.

### Fresh-head requis

3. **#121 seam gauge 4e caller (theses panel L5936)** (~30min) : dernier caller `_position_axis` non migré. Récupère `book_idx`, adapte construction `t["_entry"]/t["_stop"]/t["_tgt"]/t["_cur"]` pour lire BookLine EUR. Diff = finding. Ferme la fenêtre d'incohérence inter-panneaux.

4. **#134 monitor `stale_target`** (~1h30) : 3e monitor via `docs/templates/monitor_pattern.md`. Trigger sur dégradation : `classify` retourne `dead` si `cost ≥ target`, `dying` si `(target − cost)/cost < seuil_edge`, `alive` sinon. Surface alerte sur transition. NE PAS auto-recompute target ([[L30]] anti-piège). Le 3e monitor doit être 3× plus rapide que le 2e parce que le pattern est figé.

---

## 🟡 P1 DIFFÉRABLE

- **#133 sweep cibles batch suivant** (~2-3h étalées) : 10 positions targets/stops révision (4063.T, AMZN, AVGO, KLAC, 7011.T, 6857.T morts ; 6920.T, TSLA, LNG, MP mourants). Méthode 3 colonnes (Instrument / Ancre externe live / Ressenti) → `docs/sweep_targets_2026-06.md`. Born-dead-check obligatoire. Pré-condition idéale : #134 livré (priorise alive→dying→dead).

- **#135 refonte complète niveaux décidés** : projet structural étalé 2-3 mois, ~1 ticker/semaine. Méthode canonique : ancre externe live consensus/multiples/52w/news + décision humaine + born-check (partial > cost ET > cur · full > partial · stop reconsidéré aussi) + trace `asof + raison 1 ligne`. Doctrine élargie : stop inclus dans la révision (pré-rally peut devenir absurde).

- **#132 sweep modules `intelligence/*` + `bot/`** : SELECT directs positions → migrer vers `book.get_held_lines()` ou VUE direct. Non-urgent.

- **#145 LIVING_GRAPH forks `pnl_position`** : 4 tickers (000660.KS×2.5, 7011.T×1.9, AMD 16%, ASML.AS 18%) divergent helper (`value-cost`) vs view (`value/cost`). DAG fait son travail. À résoudre au prochain pivot compute-once-project (cf [[L29]]).

- **#147 Tests flaky ordering-dependent** : `test_aggregate_sum_equals_parts` + `test_coherence_under_perturbation` passent isolément, fail au full-run. Pollution état partagé. Diagnostic : probablement DB temp réutilisée ou cache statique non-clean. ~1h diag.

- **#148 Bot uptime monitoring** : bot redémarré 08:13 sans alerte. Pas de watchdog. Style launchd auto-restart comme tennis-bot (cf [[parallel_projects_tennis_bot]]) pourrait résoudre. ~1h.

---

## ⚪ FUTURE (laissé en attente jusqu'à signal)

- **#73 Cap par conviction = résultat mesuré post N≥30 J+90 (partie 2/2)** : dépend accumulation données track-record. Pas avant fin 2026.
- **#74 Drawdown gate découplée par cluster** : design task post-10-juin, vague — attend signal book qui justifie.
- **#88 M2 self-application — Brier-scorer le moteur thesis_erosion** : attend N≥30 verdicts résolus.
- **#89 Skip-already-classified dans compute_thesis_erosion** : optim coût event-driven. Pas pressant tant que budget LLM OK.
- **#92 post-cornerstone-macro : consensus projection per SPEC_CONSENSUS_FRAGILITE** : bloqué tant que cornerstone macro pas mûr.
- **#94 Cornerstone C5 `config/divergence.yaml`** : moteur partagé macro+micro, dépend de la suite cornerstone.
- **#99 Update 00_HANDOFF_MASTER pile §2 + séquence §5** : maintenance doctrine, fait quand le HANDOFF redevient nécessaire (handoff réel).
- **#119 switch currency UI + 4e concept checker (weight_pct/fragility)** : quand vécu (pas avant qu'on ait besoin).

---

## 🎯 VISION_PRO LONG-TERME

Roadmap chronologique complète : cf `docs/VISION_PRO.md` + `docs/DECISION_QUALITY_ENGINE.md`.

**Critère nord unique** : auditable par un adversaire. Une due-diligence hostile peut-elle falsifier ou vérifier chaque nombre ?

**Wedge actuel** (cf [[business-path-6-acted]]) : Path 6 lifestyle solo + track record public + petite audience. Discipline mécanisée (pas alpha prédictif). Phase actuelle = nourrir l'instrument (poser plus de paris, accumuler résolutions), pas raffiner la mesure (cf [[feedback_instrumentation_vs_decision]]).

**3 plafonds structurels à percer** (calibration sur outcomes ne les perce pas) :
- Auto-référentiel (l'opérateur note l'opérateur) → pré-engagement tamper-evident OTS-ancré ✅ LIVRÉ
- Petit-n (N=35, latence 30j) → process-grading + outside-view
- Outcome-graded (Brier ignore quadrant LUCK) → attribution causale 2×2

---

## ⛔ HISTORIQUE FERMÉ (référence)

Sections supprimées de cette TODO (réduit le bruit, infos consolidées dans SESSION_STATE) :

- **SOCLE S0/S1a/S1b/S1c/S2/S3** (tous LIVRÉS 09-11/06) : OTS anchor, Datum primitif, gateways Datum, migration positions VUE, base_health.py vert
- **PIVOT FONDATION 08/06** : reconstruction doctrine en suspens → SOCLE livré, pivot résolu
- **5 positions KNOWN-GAP partial close** : réconciliées via `rebuild_tr_ledger_from_csv.py` (cf #127 closed) + ledger transactions append-only (#125 livré)
- **QUALITY_BAR sweep 4 axes** (07/06) : axe 3/5/4/2 livrés, axe 1 gated invariant N<100
- **render.py decomposition** (Intra-2 v2) : différé, non pressant
- **CORRECTIVE QUEUE v2 (07/06)** : ré-évaluée, infos consolidées dans #134+#135+#146

Pour le détail, voir `SESSION_STATE.md` (entries `## Close 2026-06-XX`).
