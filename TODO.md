# TODO — PRESAGE (mes-bots-finance)

**Refresh** : 13 juin 2026 close final — 10 commits propres pushés origin/main · cutover Mac→VM réussi (split-brain résolu, VM=prod, Mac=dev) · drift detector daily 07:15 UTC actif · G2 chantier #150 = vert (10 sentinelles posées avec doctrine no-anchoring amendée 4 cas) · #147 RÉSOLU (KLAC stale cache, pas ordering) · spec + squelette #152 research_brief posés (handler /research session fraîche future)
**Mode** : **FOUNDATION FIRST. AUDITABLE PAR ADVERSAIRE.** Capstone red-team nuit++ accepté.
**Historique** : `SESSION_STATE.md` (sessions chronologiques) · `/tmp/TODO_pre_pruning_*.md` (snapshots pré-élagage)

---

## 🟢 ÉTAT SYSTÈME (13/06 close final)

- **Cutover Mac→VM complet** : VM `37.27.247.126` = prod autoritaire, code `bf35546`, alembic head `0061`. Mac = dev mode (`launchctl bootout com.olivier.presage` durable). 0 Telegram Conflict post-restart 08:31:40 UTC.
- **Drift detector déployé** : systemd user timer `presage-drift-detector.timer` daily 07:15 UTC. Smoke test passé (`behind=0`). Cure structurelle anti-récurrence 292-commits-drift.
- **G2 chantier #150 = VERT** : 10 sentinelles posées (`scripts/seed_sentinels_2026-06-13.py`, pids 294-303), origin='manual' honnête. Doctrine `feedback_no_probability_anchoring` amendée avec 4 cas (calibration/sémantique/mécanique/border Claude-assisted) + fact-check Bigdata.com pré-pose obligatoire. Sum probs 1.49 hors mécaniques (S2 CXMT HBM chinois dominante 0.70).
- **Migration 0060 amendée** : 3 gardes (CHECK conditionnel + count-assert ABORT + bot-stop required). 290 lignes legacy backfillées price/signal. `claim_type` enum {price, event, data} + `resolution_source` + `origin` enum {signal, manual} + ticker NULL-able. CHECK SQL en base, pas validation app seule.
- **Migration 0061** : table `research_brief_log` append-only (triggers no_delete + no_update). Helpers storage : `insert_research_brief_log` + `check_research_brief_rate_limit` + `get_research_brief_cost_today`. Spec #152 complète posée. Reste : module Bigdata + format markdown + handler Telegram (~1h session fraîche).
- **2 gardes mécanisées en tests** : `test_chantier_150_barrier_enforced.py` (empêche création Unit A/B/C/D sans levée explicite) + `test_no_probability_anchoring_enforced.py` (regex check anti-anchoring sur scripts/seed_*.py). Discipline passe de "Claude se rappelle" à "système enforce".
- **CLAUDE.md doctrine ajoutée** : "Migration cœur sur table sous cron" (3 gardes obligatoires bot-stop + count-assert + CHECK SQL).
- **Pytest baseline 1892/1892** (+4 nouveaux tests `test_research_brief_log.py`). #147 résolu via KNOWN_DEBT_EXEMPT KLAC+SPCX.
- **Backups labellisés** : Mac `snapshot_pre_reconciliation_20260613_171803` (91MB), VM `backup_pre_cutover_macreplace_20260613_172611` (18MB côté Hetzner).

## 🟢 ÉTAT SYSTÈME (12/06 close e)

- **Consensus targets wire gratuit** : `shared/prices.py:get_analyst_consensus` via yfinance .info (100% couverture 26/26 vs FMP free tier 19%). Aucun opex data, dette F3 du scoring sortie.
- **#134 monitor enrichi** : migration 0057 + cross-check consensus chaque évaluation. Notif Telegram affiche delta vs consensus avec flag aligné/divergent. 13 tests pass.
- **7 consensus_divergent flaggés live** : KLAC (+949%, pending fix prix), TSLA/SNPS/CCJ/000660 (variant c5 assumé), ALAB/MU (refresh today EUR→USD), BESI.AS/COHR/STMPA (pas refresh → candidates #135 prochain).
- **Script `consensus_check.py`** : audit tableau target_olv vs consensus + Top 10 écarts pour priorité revue, exécutable on-demand.
- **Sources data triagées** : FMP free trop pauvre (19%), LSEG/Daloopa hors cap opex Path 6. yfinance .info couvre 95% des besoins. Memo TODO grave pour upgrade futur post N≥30.

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

~~0. **G2 du chantier #150 = ROUGE : `/predict ×10` sentinelles event-type**~~ — **RÉSOLU 13/06** : 10 sentinelles posées via `scripts/seed_sentinels_2026-06-13.py` après cure complète du schéma (migration 0060 ajoute `claim_type/resolution_source/origin` + CHECK conditionnel + ticker nullable). Distribution : 2 Olivier-seul (S1, S2), 6 Claude-assisted post-amend doctrine (S3-S5, S7-S9), 2 mécaniques 0.99 (S6, S10 déjà publiquement déclenchées trouvées via fact-check Bigdata.com). `origin='manual'` honnête. G2 ledger PASSAGE ROUGE→VERT (pids 294-303).

0bis. **🔴 P0 DETTE CURRENCY BUG : 4 trades broker import du 12/06 14:28:30 avec `price_native` en EUR mais `currency='USD'`** (cf finding session 13/06 cutover Mac→VM). Path-dependent PMP : cure par entrées de compensation POLLUE le PMP (un reversal-BUY décale l'avg cost vers le haut, le SELL correct suivant calcule P&L contre avg pollué = on déplace l'erreur sur le P&L futur entier de cette ligne). **NE PAS curer par entrées inverses.** Cure exige mécanisme de correction dédié (ou rebuild interdit append-only) à designer dans session future. **Bénin court-terme** : P&L réalisé sous-estimé sur historique, PRU sous-estimé fait paraître plus profitable → `stale_target` flague moins, direction bénigne sur sizing live. Pas de risque /exit ni decision immédiate. **Valeurs correctes documentées** :
   - tx id=198 ALAB SELL 1.242 @ **319.65 EUR (= ~$369 USD au fx 1.155)** stocké `price_native=319.65, currency='USD', fx_at_trade=1.0` → vraie valeur USD ≈ **371.4**
   - tx id=199 GOOGL BUY 1.0 @ **312.0 EUR** stocké `currency='USD', fx_at_trade=1.0` → vraie valeur USD ≈ **361**
   - tx id=200 AMD SELL 0.741 @ **445.34 EUR** stocké `currency='USD', fx_at_trade=1.0` → vraie valeur USD ≈ **515**
   - tx id=201 AMZN BUY 1.61 @ **204.97 EUR** stocké `currency='USD', fx_at_trade=1.0` → vraie valeur USD ≈ **237.2**
   Trace : `SELECT * FROM transactions WHERE id IN (198,199,200,201)`. Session dédiée requise pour design correction (ledger event d'ajustement separate ? rebuild from broker source ?).

1. **KLAC + 5 dying + 1 dead à reposer** (cf #135 méthode) : le monitor `stale_target` livré aujourd'hui (#134, commit `5f5c5a8`) remonte 5 transitions `alive_to_dying` (CCJ +0.6%, AMZN +4.0%, 6857.T +4.5%, 4063.T +3.6%, AVGO +4.1%) + 1 `alive_to_dead` (000660.KS edge -0.3%) + KLAC currency_native hors-range. Action humaine = relire chaque thèse + reposer target+stop ancrés sur prix réel actuel (cf doctrine #135 : 3 colonnes Instrument/Ancre externe live/Ressenti).

~~2. **#134 monitor `stale_target`**~~ — **RÉSOLU 12/06 (commit `5f5c5a8`)** : 3e monitor canonique livré + smoke live (19 alive, 5 dying, 1 dead, 6 notifs Telegram). Pattern figé du gabarit `monitor_pattern.md` validé une 3e fois.

---

## 🟡 P1 DIFFÉRABLE

- **#133 sweep cibles batch suivant** (~2-3h étalées) : 10 positions targets/stops révision (4063.T, AMZN, AVGO, KLAC, 7011.T, 6857.T morts ; 6920.T, TSLA, LNG, MP mourants). Méthode 3 colonnes (Instrument / Ancre externe live / Ressenti) → `docs/sweep_targets_2026-06.md`. Born-dead-check obligatoire. Pré-condition idéale : #134 livré (priorise alive→dying→dead).

- **#135 refonte complète niveaux décidés** : projet structural étalé 2-3 mois, ~1 ticker/semaine. Méthode canonique : ancre externe live consensus/multiples/52w/news + décision humaine + born-check (partial > cost ET > cur · full > partial · stop reconsidéré aussi) + trace `asof + raison 1 ligne`. Doctrine élargie : stop inclus dans la révision (pré-rally peut devenir absurde).

- **#145 LIVING_GRAPH forks `pnl_position`** : 4 tickers (000660.KS×2.5, 7011.T×1.9, AMD 16%, ASML.AS 18%) divergent helper (`value-cost`) vs view (`value/cost`). DAG fait son travail. À résoudre au prochain pivot compute-once-project (cf [[L29]]).

- ~~**#147 Tests flaky ordering-dependent**~~ — **RÉSOLU 13/06 (diag montré stale, pas ordering)** : `test_coherence_under_perturbation` passe 5/5 isolément (TODO stale, déjà curé ailleurs). `test_aggregate_sum_equals_parts` **fail en ISOLATION** aussi (pas ordering). Cause vraie = **KLAC cache stale** (bug yfinance 11/06 prix gonflé 2108€ stocké en cache `positions.last_price_eur`) → pf_value voit KLAC à ~277€ stale, views filter outlier → divergence permanente 3.78% sur book 53k€. Cure : ajout `KNOWN_DEBT_EXEMPT = {KLAC, SPCX}` dans le test (cohérent avec test_book_gate.py + test_pipeline_end_to_end.py). À retirer du KNOWN_DEBT quand KLAC cache rebuild + cure currency 4 trades (P0 dette).

- **Cure structurelle tests CI-fresh DB** : 7 tests utilisent `skip-on-OperationalError` (cure aujourd'hui pour débloquer CI). Vraie cure = migrer ces 7 tests vers fixture `migrated_db` canonique. À faire en lot. ~1h.

- **#152 Handler `/research <target>` (research_brief, posture analyste)** : feature légitime hors barrière #150 — fournir la matière factuelle structurée (Bigdata.com financials + consensus + news + cadre causal) pour calibrer les intuitions Olivier sans franchir la frontière du jugement bot. Spec complète : [`docs/research_brief_spec.md`](docs/research_brief_spec.md). 1h-1h30 session fraîche. Cap budget LLM, rate-limit 1/h, fail-closed L15, test mécanisé anti-verdict (regex). Bonus : peut servir de fact-check pré-pose obligatoire pour sentinelles futures (doctrine `feedback_no_probability_anchoring` amendée 13/06).

- **#150 Couche de redevabilité décisionnelle (chantier figé 13/06, gated)** : étage au-dessus du ledger de prédictions, 4 unités en 3 couches (nulle paresseuse → registre unifié thèses engagées+vétoées → narrative drift + P&L biais). Spec complète : [`docs/CHANTIER_REDEVABILITY_LAYER.md`](docs/CHANTIER_REDEVABILITY_LAYER.md). Decision record : [`docs/adrs/010-decision-accountability-layer.md`](docs/adrs/010-decision-accountability-layer.md). 3 décisions tranchées 13/06 (Q1 deux hashes thesis/levels, Q2 nulle 100% SOXX jamais-rebalance + métriques duales, Q3 deux labels orthogonaux + détecteur a sa propre nulle). **Barrière §0 status 13/06 fin session** : G1✅(94 résolus) G2✅(10 sentinelles ledger) G3✅(18 triggers append-only, alembic 0060) G4✅(cure pattern #133bis add_sell) G5❓(baseline pytest à confirmer). **Ne démarre pas avant** : G5 vert ET observation post-Couche 0 plusieurs semaines. Construire avant d'observer = biais #3 en livrée d'architecte.

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

**FUTURE — data sources upgrade** (memo 12/06) — triage si budget data justifié post N≥30 :
- **Daloopa** ($5-15k/an) — priorité 1 quand track record justifie. NLP-extracted KPI/segment granularité fine. Fit direct scorer V2 + #88 Brier-scorer. Déjà dans VISION_PRO Phase 3.1.
- **LSEG/Refinitiv** ($22-30k/an) — priorité 2, après tier paying customers B2B. I/B/E/S consensus gold standard. Substituts cheap : Tikr ($30/mois) ou Koyfin ($25/mois) = 80% valeur.
- **Nimble** ($500-2k/mois) — skip sauf besoin spécifique scraping. Bigdata MCP + EDGAR couvrent 90%.
- **Doctrine cap** [[business-path-6-acted]] : opex data < $300/mois tant que track-record non monétisé. Tooling actuel (Bigdata MCP + EDGAR + yfinance) suffit Phase 1-2.

---

## ⛔ HISTORIQUE FERMÉ (référence)

Sections supprimées de cette TODO (réduit le bruit, infos consolidées dans SESSION_STATE) :

- **SOCLE S0/S1a/S1b/S1c/S2/S3** (tous LIVRÉS 09-11/06) : OTS anchor, Datum primitif, gateways Datum, migration positions VUE, base_health.py vert
- **PIVOT FONDATION 08/06** : reconstruction doctrine en suspens → SOCLE livré, pivot résolu
- **5 positions KNOWN-GAP partial close** : réconciliées via `rebuild_tr_ledger_from_csv.py` (cf #127 closed) + ledger transactions append-only (#125 livré)
- **QUALITY_BAR sweep 4 axes** (07/06) : axe 3/5/4/2 livrés, axe 1 gated invariant N<100
- **CORRECTIVE QUEUE v2 (07/06)** : ré-évaluée, infos consolidées dans #134+#135

Pour le détail, voir `SESSION_STATE.md` (entries `## Close 2026-06-XX`).
