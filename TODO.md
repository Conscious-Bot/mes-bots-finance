# TODO — PRESAGE (mes-bots-finance)

**Refresh** : 06 juin 2026 (après-midi : macro panel Phase A/B/C/D + accuracy + calibration v3 hard reality)
**Mode** : Phase construction (book 53k -> 70k) + Observation Brier V1 jusqu'au 10/06 (J-4)
**Archives** : `/tmp/TODO_pre_refresh_*.md` (historique des refresh)

---

## 🟢 ÉTAT SYSTÈME (06/06 après-midi)

- **Macro stress monitor entièrement refondu** : panel `_urgence` intelligent + warning. Triage ACT/WATCH/CALM/SILENT, regime detector 5 buckets (`intelligence/macro_regime.py`), tie-to-book warnings (`intelligence/macro_book_warnings.py`), honnêteté NULL/stale visible. Migration `0029_macro_regime_alerts`. État courant : STRESS · V3 score 120 (phase 4 CRISIS) · ACT 4 / WATCH 7 / CALM 4 / SILENT 0.
- **Bands v3 hard reality** : 10 indicateurs calibrés post-3-iterations (v2 dur -> +5% margin -> hard-fix sur 4 greens trompeurs). Cross-file consistency auditée (`_MACRO_BANDS` + `_MACRO_TIPS` + `macro_regime.py` + `macro_book_warnings.py` + `phase_ranges` + `config.yaml vol_scaling_threshold_vix=21` tous alignés).
- **Freshness améliorée** : tier1 cron 4x/jour (06h/12h/18h/22h Paris) au lieu de daily. MOVE promu tier1. `persist_signal` no-stomp fix (fetch fail garde la dernière valeur valide). Tier3 retry pattern day="1,5,10,15". CoreCPI NULL chronique fixé = 2.74% en DB.
- **CI vert** (depuis session 06/06 matin) : marker `live_data` skip 13 fichiers data-dependent, mypy fix learning.py.
- **Bot + dashboard sur VM Hetzner H24** : `ssh presage@37.27.247.126`, systemd user + linger.
- **Backup offsite Storage Box BX11** : `presage-backup.timer` daily 04:00 UTC.
- **`/audit` + `/review` Telegram handlers actifs**.
- **26 thèses refondues tailor-made** (commit 06/06 matin), gate currency_native étendu 5 champs.
- **J-day 10/06 prep** : reading contract pré-registered (N=20, M=0.03), healthchecks armed.
- **45+ commits cumulés sur 05+06/06** (10 commits macro panel après-midi). Tennis-bot intact.

## 🟢 ÉTAT SYSTÈME (05/06 soir) [PREVIOUS REFRESH]

- **Bot + dashboard sur VM Hetzner H24** : `ssh presage@37.27.247.126`, systemd user + linger, APScheduler 26 jobs, Restart=always.
- **DB** : migree Mac→VM (parite 420 signals / 30 positions / 53 theses / 219 predictions). alembic head 0028.
- **Backup offsite Storage Box BX11** (Falkenstein, €3.84/mo) : `presage-backup.timer` daily 04:00 UTC. Premier run auto : **Sat 2026-06-06 04:04 UTC**.
- **LLM cost optimise** : tier `narrate` Sonnet pour 3 sites Opus narrative ; crons espacés (classify 30min→2h, mat_v2 + recompute_boost 1h→6h). Decision_copilot + dashboard chat restent Opus.
- **6 outils analyse data** : `thesis_clusters_brier` · `source_attribution_brier` · `calibration_plot` · `bias_ledger` · `decision_audit` · `materiality_validation`. Tous scripts CLI standalone, doctrine CI-based + dedup signal_id.
- **/audit Telegram handler** : surface decision_audit dans le flow quotidien. Tape `/audit` / `/audit 14` / `/audit MU`.
- **J-day 10/06 prep** : reading contract pre-registered (N=20, M=0.03, **verdict CI-based**), healthchecks armed.
- **26 commits aujourd'hui** (matin + extension soir). Tennis-bot intact (binaire `bot.py`).
- **Backlog ouvert** : essentiellement gated par calendrier 10/06 + 27-28/06. Pas de chantier libre actionable ce soir.

---

## ⚠️ Risques silencieux — désormais couverts par 3 vigilances auto

Les 3 patterns surveillés via `intelligence/v2_vigilance.py` (cron weekly lundi 7h, push Telegram UNIQUEMENT si ALERT/WARN) :
1. **`watch_rate`** : si > 85% sur 28j = ancrage refus / si < 20% = sur-commitment
2. **`directional_spread`** : si < 3 buckets uniques sur 120j = mono-bucket déménagé
3. **`insider_clusters_alive`** : si 0 cluster + 0 buy snapshot = job cassé ; si 0 cluster + buys existants = INFO normal large-cap (pas push)

**Risque MU-style (DB vs broker drift)** : pas encore mécanisé. À envisager post-10/06 si un autre drift apparaît. Pour l'instant : audit manuel ad-hoc.

---

## 🟡 P1 — Observation usage

**Discipline = usage > code.** J-11 jusqu'au batch resolution Brier.

- [ ] **Daily check log bot** : `tail bot.log` confirme morning_chain (6h) + evening_chain (23h) tournent OK
- [ ] **Daily gate** : doit rester 🟢 0 violations (toute violation = régression)
- [ ] **VALUE_LOG** : remplir chaque jour ce que PRESAGE t'a appris (mesure réelle de valeur, pas commits)
- [ ] **CHANTIER 06/06 — Refonte targets/stops par thèse + outil /review** :
   Tous les stops actuels à exactement -25%, targets à +50/+60% par conviction =
   générique-aveugle, pas thèse-specific.

   **⚠️ Bug urgent à fixer en premier** : 6857.T entry 24215 JPY vs target 234.82 =
   -99% (probable mismatch JPY/USD ou décimale ratée). Le gate currency_native
   aurait dû l'attraper — investiguer pourquoi il est passé.

   **Session A (~2h, code)** : build handler Telegram `/review TICKER` qui sort :
     - PnL depuis achat (positions.avg_cost vs current)
     - Perf 1y / 2y du ticker (yfinance)
     - Perf relative au sector index (SOXX/XLE/etc., besoin mapping ticker→sector)
     - Valorisation P/E + P/S vs sector median (FMP API déjà dans .env)
     - Ressenti modèle : agrégat impact_magnitude + sentiment signaux 30j
     - Phase cycle sectoriel : config user-defined (ta vue signée), pas LLM
     - News récentes par ticker (signals matched cashtag/name)
     - Cibles actuelles + asymmetry calculée

   **Session B (~1h par 2-3 thèses)** : conversationnelle, tu reviews chaque
   thèse séquentiellement avec /review output. Tu proposes nouveaux niveaux
   target_partial / target_full / stop. Je valide via thesis_invariants
   (currency_native + ratio sain) avant update DB.

   Ordre suggéré (priorité) : 6857.T (bug), puis conviction 5 (CCJ), puis c4
   (AMZN/MP), puis c3 (ENTG/LNG/MU).

---

## 📅 Calendrier dur

| Date | Item | Action |
|---|---|---|
| **31/05** | Hetzner migration (ADR) | **Différer post-10/06** — pas attaquer cloud d'un système pas-encore-Brier-validé |
| **10/06** D-11 | Batch resolution 49 predictions | Vague résolution + 1ère mesure Brier dédupliquée. **Moment de vérité.** |
| **29/06** D+30 | Mesure boucle-de-soi V0 | 7 ancres contrefactuelles ALAB/MU/LNG/CCJ/MP atteignent J+30. `aggregate_brier_dedup()` + `measure_bias()` produiront premiers chiffres signés du biais "vend_winners_trop_tot". |
| **Post-10/06** | Path 6 / Niveau 2 | Conditionnel sur Brier — si validé, slice publication. Sinon retour fondations. |

---

## 🎯 NIVEAU 2 — quand fondations validées (post-10/06)

À attaquer **uniquement** si Brier 10/06 valide. **Résister à construire avant.**

Ordre :
1. **#5 jauge composite AI capex** (~1j, consolide la surface)
2. **#4 + #2 jumeaux** : pré-registration immutable + contrefactuel intent-aware
3. **#1 adversaire** : bear case + sell-friction informative
4. **#3 process score** : optionnel long-tail (rubric pré-signée requise)

Cf mémoire `niveau_2_adversary_and_proof` pour le détail.

---

## 🔒 SÉCURITÉ — auditée 30/05/2026, binairement OK

Audit complet 30/05 (chantier #12 de la session) :
- Repo GitHub **PRIVÉ** (`Conscious-Bot/mes-bots-finance`) ✓
- `.gitignore` couvre : `.env*`, `*.token`, `token.json*`, `credentials.json`, `oauth_tokens/`, `client_secret*`, `service-account*` ✓
- Tous fichiers sensibles locaux (`.env`, `credentials.json`, `token.json`, `.env.backup_*`, `.env.save`) sont **IGNORED** par git (vérifié via `git check-ignore`) ✓
- `.env.example` tracké comme template avec placeholders (`sk-ant-xxx`, `000000:xxx`, etc.) ✓
- Git history scan 7 patterns : `sk-ant-` (2 = placeholders template), `ghp_` (0), `xoxb-` (0), `BEGIN PRIVATE KEY` (0), `Bearer + 30+ chars` (0), `ya29.` (0), `AKIA` (0) — **aucune vraie clé exposée** ✓
- [ ] **Rotation OAuth Google** — runbook prêt, déclencheurs inactifs (pas encore lancé)

L'item "hygiène secrets faite une fois" du PLAN_ACQUIHIRE est validé binairement. Re-audit si on ouvre le repo en public.

---

## 🚀 PATH 6 — quand calibration prouvée (post-10/06)

- [ ] **Calibration plot home** (money-shot Path 6) : ≥10 prédictions résolues prob-différenciée requis
- [ ] **Substack premier article** : fact-check SK Hynix $1,216 + reliability diagram + ledger résolu
- [ ] **presage.fi** : acheter (~10€/an, défensif)
- [ ] **Panneau biais sous surveillance** : surface dashboard quand n_resolutions ≥ 5

---

## ✅ DÉJÀ FAIT (29/05 + 30/05 matin)

### 06/06 après-midi — Macro stress monitor refonte complète

- **Phase D (honnêteté state)** (`88e5b09`) : NULL → `—` + class mute + badge `no data` rouge. Stale > tier threshold → badge `stale Nd`. Sort secondaire stale-after-fresh.
- **Phase C (triage)** (`acd3302`) : remplace tier flat list par buckets `ACT/WATCH/CALM/SILENT` ordonnés par stress. Tier chip (M&L/BANK/SLOW) préservé sur chaque row.
- **Phase A (regime detector)** (`24256e9`) : `intelligence/macro_regime.py` + migration `0029_macro_regime_alerts` + storage helpers + 9 tests dont L4 idempotence. Classifier déterministe 5 buckets (COMPLACENT/RISK_ON/LATE_CYCLE/FRAGILE/STRESS), indépendant V3 composite.
- **Phase B (tie-to-book)** (`d899d44`) : `intelligence/macro_book_warnings.py` + 9 tests. 5 règles déterministes regime × book composition. Bloc "Macro impact on book" sous indicator grid.
- **Bands v2 dur + rename CALM + tooltips resync** (`5afd248`) : 10 indicateurs durcis, tooltips audit complet (zero mismatch restant), UI label ASLEEP→CALM.
- **Accuracy** (`186406b`) : cron tier1 4x/jour, MOVE promu tier1, persist_signal no-stomp, tier3 retry day="1,5,10,15", CoreCPI NULL chronique fix (2.74% maintenant).
- **V3 phase_ranges align + VIX vol_scaling 25→21** (`266b28e` + `de8c48c`) : INDICATOR_CONFIG phase_ranges alignées bands, vol_scaling threshold descendu.
- **v3 +5% margin** (`de8c48c`) : loosen v2 dur après user "peut-être allé un peu fort". 10 indicateurs +5%.
- **v3 drift fix R1/R2/R5** (`e8dbc98`) : audit cross-file → 3 thresholds bookwarnings non syncs corrigés (TYX 4.5→4.2, USDJPY 158→154, VIX 13→12).
- **v3 hard reality** (`7d0f683`) : 4 greens trompeurs → WATCH. T10Y2Y warn 0.28→0.5, DXY warn 103→98, CopperGold band ajouté (0.0015, 0.0008), BankReserves band ajouté (3.2T, 2.5T). Score V3 98→120 (phase 4 CRISIS dans frise).
- **Cross-file consistency auditée** : tous fichiers alignés v3-fix (render.py bands + tips, macro_regime classifier, bookwarnings, debt_monitor phase_ranges, config.yaml vol_scaling).

### 06/06 matin — CI fix + /review + refonte targets 26 thèses

- **CI vert 1ère fois** : `d3b23bf` test_resolution_rules caplog flake fix, `64e4d64` mypy learning.py, `fe0238c` marker `live_data` + skip 13 fichiers, `aac6f72` ruff cleanup. Post #06 draft "trois jours de CI rouge invisible".
- **Currency_native gate étendu** (`e18ff54`) : check sur stop_price + target_price + target_partial + target_full + entry_price (avant : stop seul). Bug 6857.T target=-99% l'avait révélé.
- **Handler `/review TICKER`** (`29dc215` + `9d83446` + `0ecfb0d`) : fact-sheet contextuel zéro LLM. Config sectors.yaml (5 secteurs × cycle phase user-signed). PnL EUR (fix : positions.avg_cost = EUR convention legacy). Tested NVDA + CCJ.
- **Refonte cibles 26 thèses tailor-made** : 9 patterns selon analyse perf vs sector / valo / cycle / PnL / signaux. Strong A renforce (-15/+20/+40) sur 7 tickers, ALAB bump +60%, energy commodities -20/+15/+25, 6857.T tight -9/+10/+17, etc. Stop -25% générique aveugle remplacé partout.
- **Trailing stops profit-protection** : AMD 396 EUR (-15% from current 466 USD), STMPA.PA 53.40 EUR.
- **Data fixes positions.avg_cost** : 6857.T 4238→143 EUR (legacy pre-split), 000660.KS 1163→1060 EUR (user-provided buy 2000 EUR à 1060 - sell 490 EUR). TSLA conviction 2→4 (call personnel).
- **Audit avg_cost 26 positions** clean (3 PnL +100%+ vérifiés = vrais gains AMD/HO.PA/STMPA.PA, pas bugs).
- **11 commits** cumulés sur la journée 06/06.

### 05/06 soir — Analytics push + /audit en flow (extension)

- **LLM cost optimization** : tier `narrate` Sonnet pour 3 sites Opus narrative (portfolio_grade_llm, bot_conceptions, user_profile) + crons espacés. Decision_copilot + dashboard chat preservés Opus.
- **J-day reading contract pre-registered** : N=20, M=0.03, verdict CI-based (pas point estimate franchissant M).
- **6 outils data livrés** : thesis_clusters_brier · source_attribution_brier · calibration_plot · bias_ledger · decision_audit · materiality_validation. Tous CI-based + dedup signal_id.
- **`/audit` Telegram handler** : per-decision view dans flow quotidien (group date, verdicts mots, branches FR, markers 💸).
- **Test isolation source-direct** : fixture `isolated_full_db` pour les 2 tests INSERT → pollution TEST_E2E_DEC stoppée.
- **measure_bias TEST_* filter** : ledger boucle-de-soi etait 100% pollue (30/30 résolutions TEST). Fix source-direct + bias_ledger.py outil.
- **Fix orphan decisions 03/06** : positions.py manquait record_anchor + auto-close thèse sur full_exit. Source-direct + backfill 5 counterfactuals + SNOW thèse close.
- **Fix currency_native NaN gate** : math.isnan check ajouté.
- **PROVISION.md retrospective** : 200+ lignes catalogues tous les gotchas migration.
- **18 commits supplémentaires** (cumulé 26 jour).

### 05/06 — Migration Hetzner full + backup offsite (chantier marathon, cf SESSION_STATE close)

- **Fix mode vacances digest** (`327e1ea`) : retire double-gate `pending_llm`. 70 signaux unstuck, recovery automatique au prochain cron quand LLM revient. Memoire `pending_llm_no_double_gate`.
- **Migration full Mac→VM Hetzner CX22** (Helsinki, Ubuntu 26.04, IPv4 37.27.247.126) : user `presage` + pyenv 3.14.4 + venv + 115 packages + DB scp + OAuth rotation + cutover bot launchd-unloaded.
- **Backup offsite Storage Box BX11** (Falkenstein, €3.84/mo) : 2e ed25519 sur VM, subaccount `u608897-sub1`, systemd timer daily 04:00 UTC, dry-run pousse 6.4MB + 14MB OK.
- **4 commits pushes** : materiality_v2 fix + backup.sh portable + heimdall→presage rename + systemd backup timer.
- **2 memoires** : `pending_llm_no_double_gate` (feedback), `hetzner_migration_triggered` (project, override `migration_solofounder_only`).

### 29/05 — Brief 10 points implémenté
- ① Passerelle dérivée unique (`storage.get_position_view`)
- ② Digest book-anchored (kill-criterion + validation + margin urgency)
- ③ Invariant décision→outcome (predictions OR decision_counterfactual)
- ④ Crons séquencés (morning_chain / evening_chain / weekly_chain)
- 3 couches Position canonique (FAIT/JUGEMENT/DÉRIVÉ + HISTORY append-only)
- `run_static_gate(conn)` avec InvariantViolation strict
- Boucle-de-soi V0 : `intelligence/self_loop.py` + migration 0018
- P0 sécurité repo privé vérifié
- P1 #1 Drawdown tolerance 75 → **70%** validée
- P1 #2 MU trim 50% (×2) + kill_criteria refondus
- P1 #3 SNOW thèse structurée
- P1 #4 LNG maintenu + tag refiné
- CCJ : reverse scale_in + re-tag PPA-correlated + thesis fixée USD natif
- Phase 4 gate currency + kill_criteria substance (11 violations dette catalog)
- 2 mémoires : `adversarial-pushback-explicit` + `currency-native-invariant`
- Backup + cleanup + push (348M snapshot + 400M libérés)

### 30/05 (session unique 42 commits, 20 chantiers, 10 itérations arc V2)

**MATIN — Dette P0 résorbée + MU fix** (commits ...→49acd34) :
- Fix trigger ORPHAN trop large, SAF.PA thèse réécrite, Batch A (5 kill-criteria substance) + Batch B (5 currency native), fix daily_backup_job cwd, KNOWN_DEBT vidé, recalcul cluster cap CCJ.
- Phase 4 colmatage (migration 0020 drop 4 tables fossiles, alerte Telegram gate-red startup, asym rounding 2→3, 7 tests e2e pipeline).
- MU fix : qty 0.119 → 1.224 (€99.5 → €1020.10), trim fantôme #4 supprimé, decision #23 [VOIDED], filtre dans `measure_bias`. Bot redémarré caffeinate.

**APRÈS-MIDI/NUIT — Arc V2 calibration** (commits 4f34584→0108b3a) :
- **10 itérations sur l'élicitation/sourcing/tests** : audit pré-batch 10/06 révèle mono-bucket [0.608-0.658] → SIGNAL_SCORER_V2 prompt 3 étapes → bug source_name → enforcement weak→watch → sémantique P(call correct) → wire sourcing → extraction exhibits → pollution prod via tests → consolidation DB_PATH → dry-run J-11.
- **Code prod déployé** : V2 scorer (`intelligence/signal_scorer_v2.py`), wire 8-K + insider clusters (`intelligence/edgar_signal_wire.py` + `shared/edgar_exhibits.py`), `storage.DB_PATH` consolidé via `__getattr__`, hook sync `EightKSource.persist()` + `BuyClusterSource.persist()`. Forward-only strict.
- **Source unique de vérité** : V2 sur contenu réel (vs V1 estimate_probability cap [0.50, 0.72] mono-bucket). DoD e2e vérifiée : NVDA Q1 FY27 8-K → V2 prob=0.750 bullish strong. Smoke prod testé.
- **ADR 012** soft-deprecate classifieur 8-K severity. ADR README à 19 entrées.
- **3 vigilances mécanisées** (`intelligence/v2_vigilance.py` + cron weekly lundi 7h) : watch-rate, prob spread cohorte directionnelle, insider clusters alive. Push Telegram UNIQUEMENT si ALERT/WARN. **13 tests unit** + smoke run.
- **Dry-run résolution J-11 (iter 10)** : Brier 0.295 attendu (pire qu'un prior 0.5 trivial), accuracy 38%, mécanisme tourne (40/40 prix fetched). V1 mauvais comme prédit. À ne PAS publier comme track record.
- **Script `post_resolution_brier_report`** : standalone, comble le gap Telegram du 10/06 (Brier moyen + dedup cluster + WARNING mono-bucket auto). À lancer manuellement 10/06 9h05.
- **4 posts canoniques bilingues** (`posts/post_01_*..post_04_*`) : arc V2, SK Hynix bug, dry-run J-11, méta-bug iter 9. Phase A juillet du PLAN en ~60j d'avance.
- **Brand line verrouillée** : *"La vérité dans le bruit / Truth in the noise"*. README hero, AGENT_HANDOFF mention, mémoire `presage_brand` distinction substance/slogan.
- **CI fix** : `pytest -m "not slow"` (les 4 slow tests ne crashent plus la CI car secrets absents).
- **Audit security 7 patterns** : 0 vraie clé exposée. Item "hygiène secrets" validé binairement.
- **Bot.log rotation manuelle** (`scripts/rotate_bot_log.sh`) : MANUEL uniquement, jamais automatique.
- **TODO + SESSION_STATE + FICHE_TECHNIQUE + AGENT_HANDOFF + CONVENTIONS §5** refresh complet. 4 mémoires Claude sync.
- **Pattern itéré 10 fois** : *« la conclusion est toujours en avance d'un cran sur la preuve »*. Y compris sur le fix lui-même (iter 9 alias statique → test régression a montré immédiatement que ce n'était pas un fix).
- **2 tags git** : `eod-30-05` (14:00) + `eod-30-05-full` (16:20). **3 backups** locaux. **427 fast + 4 slow tests verts**. Bot PID 84607 caffeinate.

**Decision log complet** : `docs/decision_logs/01_calibration_unanchored.md` (10 itérations + 3 vigilances + draft v5 publishable).

### Trades du jour (29/05 chat-driven)
- ALAB 616€ → LNG 616€ (profit-take winner)
- MU 940€ + 920€ (trim ×2, quasi-out) → LNG 250€ + CCJ 667€ → reverse CCJ → LNG 434€ + MP 233€
- 7 ancres contrefactuelles capturées

---

## 🧭 Cadre maître (rappel)

### Les 4 racines (verdict 29/05) — état actuel

1. **Source de vérité unique du book** — ✅ Soudé (book.py + position.py + storage.get_position_view)
2. **Features qui combattent la discipline** — ✅ Soudé (gate fundamental-only + kill-criteria substance)
3. **Mode maintenance permanent** — ⚠️ Phase construction active jusqu'à ~65k€ book (= ~13k€ encore à déployer)
4. **Métriques calibrées pour le confort** — ✅ Soudé (note 88 honnête, drawdown CTA verte, ballast haircut, Solidité refondue)

### Principe directeur

**Tout output non instrumenté est gaspillé.** Chaque output doit recevoir un outcome mesurable qui se réinjecte. La moitié des 15 vues échouent ce test. À couper progressivement post-10/06 quand on aura la mesure pour arbitrer.

### Calendrier discipline (REVISED 30/05 post-dry-run)

- **Maintenant → 10/06** : usage > code. **MAIS** : V1 mauvais déjà mesuré (dry-run Brier 0.295). Le 10/06 n'apporte pas de validation calibration positive — sert de baseline V1 figé pour future comparaison V2. Le "moment de vérité" devient **« est-ce que je publie quand même le mauvais chiffre comme prévu, ou je me trouve une excuse »**.
- **10/06** : batch resolution V1. À publier honnêtement (post_03 déjà drafté pour ça). Brier ~0.295 attendu, ne PAS maquiller. Le **mécanisme** tourne (vérifié dry-run), c'est V1 qui est mauvais comme prédit.
  - **9h00** : `daily_resolve_job` tourne automatiquement. Telegram envoyé avec counts (correct/incorrect/neutral) mais SANS Brier moyen.
  - **9h05** : lancer manuellement `python -m scripts.post_resolution_brier_report 2026-06-10` pour obtenir Brier + dedup cluster + warning mono-bucket. C'est ce chiffre qui compte pour la calibration.
- **Post-10/06** : observer les cohortes V2 qui s'accumulent (wire 8-K + insider clusters actifs). Première comparaison V1 vs V2 nécessitera ~2-3 mois de N V2 suffisant.
- **Path 5 / 6** : différer jusqu'à avoir N V2 suffisant pour calibration plot publishable (post-août probablement, pas 10/06).
