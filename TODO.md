# TODO — PRESAGE (mes-bots-finance)

**Refresh** : 12 juin 2026 close (d) — book figé 12 UPDATE par id · #134 stale_target monitor livré · freshness audit (kill_criteria + 3 weekly crons +grace_time) · tier1/tier2 cron grace_time · F3 scoring confirmé en prod
**Mode** : **FOUNDATION FIRST. AUDITABLE PAR ADVERSAIRE.** Capstone red-team nuit++ accepté.
**Historique** : `SESSION_STATE.md` (sessions chronologiques) · `/tmp/TODO_pre_pruning_*.md` (snapshots pré-élagage)

---

## 🟢 ÉTAT SYSTÈME (12/06 close d)

- **Book figé conviction-rubric** : 12 UPDATE par id (commit `511ccd6`) — 7 convictions, 3 C5 targets/stops, 2 dead refraîchis EUR→USD live (fx 1.1565). KLAC pending (prix DB cassé worldwide).
- **Stale_target monitor live** : 20 alive / 5 dying (CCJ +0.6%, 4063.T +3.5%, AMZN +4.0%, AVGO +4.1%, 6857.T +4.5%) / 1 dead (000660.KS edge -0.4% target inchangé décision). Notif Telegram auto sur futures transitions.
- **Freshness 100%** sauf normal/on-demand : 2 bugs masqués révélés et fixés (kill_criteria persist no_change + 3 weekly crons +grace_time, commits `322b1e9` + `0179306`).
- **Pattern récurrent (à graver L?)** : "cron fenêtre fixe + APScheduler default = pas robuste aux downtimes bot". 3 cures de cette famille cette session.

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

### Action humaine (pas code)

1. **KLAC + 5 dying + 1 dead à reposer** (cf #135 méthode) : le monitor `stale_target` livré aujourd'hui (#134, commit `5f5c5a8`) remonte 5 transitions `alive_to_dying` (CCJ +0.6%, AMZN +4.0%, 6857.T +4.5%, 4063.T +3.6%, AVGO +4.1%) + 1 `alive_to_dead` (000660.KS edge -0.3%) + KLAC currency_native hors-range. Action humaine = relire chaque thèse + reposer target+stop ancrés sur prix réel actuel (cf doctrine #135 : 3 colonnes Instrument/Ancre externe live/Ressenti).

~~2. **#134 monitor `stale_target`**~~ — **RÉSOLU 12/06 (commit `5f5c5a8`)** : 3e monitor canonique livré + smoke live (19 alive, 5 dying, 1 dead, 6 notifs Telegram). Pattern figé du gabarit `monitor_pattern.md` validé une 3e fois.

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
