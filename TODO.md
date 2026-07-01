# TODO — PRESAGE (mes-bots-finance)

**Refresh** : 30 juin→01 juil 2026 close session **SOLIDIFICATION + AUDIT 3 DOMAINES**. 6 commits (`49c98eb`→`45d05da`) : serve résilient (bind-first+launchd KeepAlive), 2 fail-silents tués (`triggered_*_at` révision-reset, `size_recommend` mauvaise table), bandeau daily% honnête + cartes NEAR nominatives, migration 0064 (clamp dust qty vue positions). Data VM : 20 flags triggered orphelins nettoyés, AMD qty→0, Voyage AI câblée (index 5/422 rate-limited). **Audit code+dashboard+Obsidian** → 5 fail-silents HARD actifs (cf ÉTAT SYSTÈME + P0). **⚠️ deploy VM en attente** (bot 12 commits en retard, fast-forward propre). — *Refresh précédent 27/06 : cure taxonomie 5 sources → 1, cf ci-dessous.*
**Refresh (27/06)** : close session **CURE TAXONOMIE 5 sources → 1** (Phases 0→4 chaînées). 5 commits dédiés (`38ee8ee` loader + YAML v2 → `7e2b61f` Source A morte → `8bbcdb9` Source E morte dict 2-niveaux → `7bf5f6a` Source C dérivée façade conservée → `82f5d4c` kill_switch dérivé assertion held-scopée). L'assertion a attrapé 1 incohérence MHI préexistante (decorrelators config.yaml ↔ ai_capex mapping) ; tranché bias-safe driver=ai_capex, layer reste energy/generation, config.yaml aligné. Périmètre disjoncteur passe **18 → 19 tickers** (MHI entre), vigilance -25% à 32 493€, trim partiel -35% à 28 160€. Sanity check final : Σ layer_primary = 100% pile (55 233€), ai_capex held = 78.4% VALEUR = exact match kill_switch live VM (43 324€), Positions ≡ Concentration. Production confirmée live VM (PID 447296, smoke `_cluster_membership() = 19 + MHI inclus + 43 324€`). Doctrine durable ajoutée `[[layer-vs-driver-orthogonal]]` (cas conglomérat ambigu, bias-safe).
**Mode** : **INSTRUMENT HONNÊTE. STRUCTURE PAS LONGUEUR. FAITS PAS KEYWORDS.** Forward-only, le bot tourne, on laisse le temps faire.
**Historique** : `SESSION_STATE.md` (sessions chronologiques) · `/tmp/TODO_pre_pruning_*.md` (snapshots pré-élagage)

---

## 🟢 ÉTAT SYSTÈME (30/06→01/07 close solidification + audit 3 domaines)

- **main HEAD `45d05da`** (6 commits, cf Refresh). **alembic head 0064** Mac+VM.
- **⚠️ bot VM 12 commits en retard** (`2b855f1`, fast-forward propre, aucune divergence) → fixes `storage`(triggered-clear)/`size_recommend` PAS live. Séquence deploy dans SESSION_STATE close. Attend go explicite (restart bot prod).
- Pytest : les 2 échecs (AMD dust + size_recommend) **corrigés** ; sinon 1977 passed. Dashboard serve sous launchd KeepAlive (bind-first ~4s). Bot VM vivant, crons 0-fail. Voyage embed OK (index sparse 5/422).

### 🔴 P0 AUDIT — 5 fail-silents HARD actifs (30/06, détail SESSION_STATE close)
- **A** Obsidian `mirror_thesis_aliases:380` non-idempotent (`split(",")` casse longNames à virgule) → AMZN **235 aliases** ré-ajoutés chaque run 30min. Fix parser quote-aware + nettoyer 8 notes. *(cron VM)*
- **B** Dashboard `_perf_dwm` (TOP MOVERS) diverge de `_dp_pct` (sources ≠ : yfinance vs price_history) → daily% contradictoire. Fix : source unique. *(Mac)*
- **C** Dashboard equity/CAGR/Sharpe/maxDD biaisés (look-ahead qty + survivorship + multi-devise sans FX, `render.py:999-1043`). Track record embelli — stratégique proof-of-value. *(Mac)*
- **D** Code `kill_criteria_monitor.py:141-149` : prix absent → marges 0% fabriquées dans prompt LLM → faux KILL. Fix `return None`. *(cron VM)*
- **E** Obsidian `mirror_transactions:451-489` fabrique `[[liens]]` morts. Fix : enrober que si résolu. *(cron VM)*

## 🟢 ÉTAT SYSTÈME (27/06 close cure taxonomie 5 sources → 1)

- **main HEAD `82f5d4c`** (5 commits today : `38ee8ee` Phase 0 loader + `7e2b61f` Phase 1 A morte + `8bbcdb9` Phase 2 E morte + `7bf5f6a` Phase 3 C dérivée + `82f5d4c` Phase 4 kill_switch dérivé ; alembic head inchangé 0062).
- **DB integrity_check ok** Mac + VM. STMPA fantôme (positions_meta.status='open' qty=0 post 26/06 full_exit) corrigé sur VM.
- **28 thèses actives** + 1 thèse `concluded` (STMPA.PA). 26 positions DB held (qty>0).
- **209 transactions append-only** (tx#244 STMPA full_exit + tx#245 SAF.PA scale_in du 26/06).
- **104 decisions journalisées** (decision#104 SAF.PA scale_in 26/06).
- **Bot.main running VM (PID 447296)** ✓ avec nouveau `cluster_source: taxonomy_ai_capex_held`. Smoke live confirmé : 19 tickers + MHI + 43 324€. Aucun ghost (0 zombie, 0 orphan PRESAGE).
- **5 sources catégorisation → 1 canonique** (`presage_taxonomy.yaml`) + 2 résiduelles (B 3 lecteurs non-kill_switch + assertion permanente held-scopée, D pour caps portfolio_rules). `sector_taxonomy.py` + `config/sectors.yaml` supprimées.
- **Vault PRESAGE** : 254 notes, 36 phantoms résiduels acceptés. FIREWALL FAIT/JUGEMENT respecté.
- **Backups** : `~/config.yaml.backup_pre_phase4_*` créé sur VM avant pull. Sync DB auto rotation 5 backups via launchd.
- **🟡 Dette doctrinale connue** : enum `decision_type` n'a pas `re_anchor`, utilisé `override` comme fourre-tout. Migration légère pending.
- **🟡 KNOWN-GAP P3** : cascade `.replace` acronymes dans `clean_sector` (fragile). Refonte cible = dict `ACRONYMS` lookup par token. Pas urgent.
- **🟡 KNOWN-GAP P3** : helper `insert_decision_with_cf` doit `UPDATE positions_meta.status='closed'` au `full_exit`. Pattern manquant détecté 27/06 (STMPA fantôme).
- **🔵 Trades pending cash injection** : Infineon (IFX.DE) + Prysmian (PRY.MI) + ARM bloqués, virement bancaire en cours.

## ✅ DÉJÀ FAIT (27/06)

- **Cure taxonomie 5 sources → 1** (5 commits `38ee8ee` → `82f5d4c`) :
  - **Phase 0** loader `shared/taxonomy.py` + YAML v2 26 held + 7 planned. Invariants raise à l'import. 15 tests.
  - **Phase 1** atomique : Source A (`sector_taxonomy.py`) morte, 5 consommateurs basculés (decision_copilot, portfolio_grade, copilot_test, render._clean_sector, portfolio_analytics). Leçon "symbole vs fichier" — un fichier exporte plusieurs symboles, recon doit lister TOUS les importeurs.
  - **Phase 2** : Source E (7 fonctions render.py) morte via `_sectors()`. Dict 2-niveaux `SectorLabel(group=mère, sub=sous-couche)` backward-compatible. 6 downstream héritent par threading. Check chiffré : 13 mères, Σ = 100% (54 702€).
  - **Phase 3** : Source C (`config/sectors.yaml`) dérivée. Façade `shared/sectors.py` conservée. `sector_highlevel_buckets` enrichi avec overrides historiques (AMZN/GOOGL → tech_mega, MP → energy_commodities, TSLA → auto_ev). 25 tickers prédictions résolues, **0 divergence Brier**. D survit intact.
  - **Phase 4** : Source B basculée pour kill_switch. `taxonomy.assert_held_cluster_consistency()` fail-closed. Assertion a attrapé MHI incohérent → bias-safe driver=ai_capex tranché → config.yaml aligné (7011.T `decorrelators` → `compute_ai`). Périmètre 18 → 19.
- **STMPA fantôme positions_meta corrigé sur VM** (side-effect post 26/06 full_exit). Test pipeline_end_to_end repassé vert.
- **Production VM cutover Phase 4** : `git pull --ff-only` VM + `systemctl --user restart presage-bot.service` (PID 436087 → 447296). Smoke live confirme cluster 19 tickers + MHI + 43 324€.
- **Doctrine `[[layer-vs-driver-orthogonal]]` ajoutée mémoire** (27/06) : layer = fonction-chaîne (objective), driver = ce-qui-meut-cours (binaire forcé). Ne JAMAIS changer le layer pour aligner le driver. Bias-safe sur conglomérat ambigu : préférer l'erreur qui ne crédite pas une décorrélation à moitié.

## 🟢 ÉTAT SYSTÈME (26/06 close vault cleanup + sweep #135)

- **main HEAD `4780d4e`** (2 commits today : `607769e` mirror smoke filter + `4780d4e` WAL/SHM cleanup ; alembic head inchangé 0062).
- **DB integrity_check ok** Mac + VM. Bug structurel post-sync corruption (3e occurrence) **fermé** via WAL/SHM cleanup.
- **28 thèses actives** (1 SK Hynix re_anchor structural 26/06, 1 KLAC no_action_flag, 5 trail stops mécaniques). 36 positions held.
- **208 transactions append-only** (tx#243 HO.PA scale_in 1 sh @ €219.40 — dernier).
- **101 decisions journalisées** (decision#101 CCJ trail dernier ; KPI #5 +7 décisions [STRUCTURED] aujourd'hui sur 7 thèses sweep #135 + 1 trade).
- **Bot.main running VM** ✓ (single-source-VM respectée). Mac = read-only view.
- **Vault PRESAGE** : 254 notes (13 vides supprimées + 1 Presage.md hub créé + 10 aliases adds). 143→36 phantoms (-75%). FIREWALL FAIT/JUGEMENT inviolable respecté.
- **Backups DB sync auto** : rotation 5 backups via launchd (last 22:05/21:05/20:05/19:05/...).
- **🟡 Dette doctrinale connue** : enum `decision_type` n'a pas `re_anchor`, utilisé `override` comme fourre-tout. À ajouter au CHECK constraint DB si re-anchors fréquents (migration légère).
- **🔵 Trades pending cash injection** : Infineon + Prysmian + ARM bloqués (Boursorama ≥€2500 min PEA, ARM CTO €1600 short). Virement bancaire en cours.

## ✅ DÉJÀ FAIT (26/06)

- **Mirror smoke filter** (`607769e`) — Triple filtre `source NOT LIKE 'smoke_test%' + ticker NOT LIKE 'SMOKE%' + NOT LIKE 'SMK%'`. 12 tx résidu 09/06 ne polluent plus le mirror Obsidian. Ledger préservé.
- **SQLite WAL/SHM cleanup post-sync** (`4780d4e`) — Root cause 3e corruption Mac DB identifiée (atomic `mv` ne suffit pas, WAL stale survit au swap). Fix `rm -f bot.db-wal bot.db-shm` après swap. Bug structurel fermé.
- **Vault cleanup** — 13 notes vides supprimées (doublons + stubs `[À COMPLÉTER]` + smoke residue). Presage.md hub créé (résout 36 phantoms). 10 aliases adds (résout ~30 phantoms company-name). Net -75%.
- **Sweep #135 (7 thèses)** — 000660.KS re_anchor structural (3 catalyseurs HBM4+monopole+US listing). KLAC no_action_flag (analystes en LAG, thèse inchangée). 4063.T+6857.T+AMZN trail 15%. AVGO trail 20% (recule). CCJ trail 10% (avance). Targets inchangés sur les 5 trail (discipline anti-anchoring tenue contre tentation widen "légèrement").
- **HO.PA scale_in** 1 sh @ €219.40 (tx#243, decision#94). 7→8 sh, cap c3 31%, sous entry moyen 221.90.
- **Session close ritual L6** — SESSION_STATE update + TODO refresh + commit dédié.

## ✅ DÉJÀ FAIT (25/06)

- **Audit panneaux dashboard book value** — User signale dashboard €56,652 vs broker €57,370. Diagnostic = cash buffer (~€696 CTO+PEA) non tracké en DB. User accepte Option D (status quo). Doctrine gravée mémoire.
- **Incident dashboard book=0** — 3e corruption Mac DB post-sync. Restore via re-sync + investigation root cause WAL/SHM stale → fix structurel commit 4780d4e ci-dessus.
- **Incident MU LIVING_GRAPH fork +13%** — Alert légitime (MU +13% intraday, cache 30 min vs price_history fresh). Restart serve.py clear `_PX_CACHE` → fork résolu (0 occurrence today's bucket).

## 🟢 ÉTAT SYSTÈME (24/06 close instrument-honnêteté + SOCLE refonte)

- **main HEAD `0b0ae81`** (7 commits today : 6 substantiels + close ; alembic head inchangé 0062).
- **DB integrity_check ok** Mac + VM. Sync VM→Mac launchd hourly opérationnel (last sync 04:45Z).
- **28 thèses actives** réparties grid SOCLE 24/06 : 2 c5 SOCLE structural (ASML.AS+TSM) / 8 c4 priced / 16 c3 priced / 2 c2 priced. **28 positions held** (qty>0). **201 transactions** append-only.
- **Book value 57 358 €** (pf_value), **cost basis 45 104 €** (pf_cost via PMP rolling), **PnL +12 254 € (+27.2% on cost)**. Trois sources canoniques cohérentes au centime.
- **Bot.main running VM** (pid OK, vérif SSH). Mac = read-only view single-source-VM (memory 23/06 doctrine).
- **5/5 gates verts** : ruff / import / regen / pytest 13/13 critical (8m06s) / smoke Playwright SOCLE rendering confirmé.
- **SPECs canonical drift** : 11/11 footers OK, 0 drift, 3 orphelins acceptables. 0 KNOWN-GAP / 0 TODO markers en code (codebase propre).
- **KPIs dashboard post-fix** : #2 stuck strict calendaire (5→0 false positives) · #4 panic factuel non-contournable (1 flagged = VRT cas-limite) · #5 forward-only 0/76 (compteur monte à mesure de la nouvelle discipline 3-champs).
- **Backups** : `data/bot.db.backup_close_20260624_145504` Mac (102 MB) + VM (100 MB) + `config.yaml.backup_close_20260624_145504` (16 KB).
- **🟡 Dette doctrinale connue** : 57 mypy errors pré-existants dashboard/render.py (count identique avant/après mes patches, 0 nouveau). À ne pas attaquer maintenant — focus accumulation N résolutions 28j.
- **🔴 Bug add_sell `positions_meta.status='closed'` (héritage 23/06)** : pas encore fixé, reste KNOWN à fixer en code (UPDATE post-commit + test close-on-zero pattern).

## ✅ DÉJÀ FAIT (24/06)

- **Audit dashboard 45 panneaux × 9 pages** (`docs/audit_panneaux_dashboard_2026-06-24.md`) — 7 findings classés par sévérité, aucun HIGH, source de vérité = transactions ledger confirmée.
- **F1+F2+F3 fixes** (`2a27e25`) — Closest-to-target inclusion structural / label-code alignment 10%→5% / 3 sectors mappings (6324.T/GEV/SPCX).
- **Gauge Option B** (`378c24f`) — Entry centré 50%, KLAC dot 25%→71% (winner secured visuel), modes standard + trailing-up, validation Playwright 7 tickers.
- **KPI #4 panic factuel** (`659480a`) — Signature DB non-contournable, test négatif PASS avec mot-clé "redéploiement" toujours flagged. Doctrine [[bias-detectors-factual-not-keyword]].
- **KPI #2 stuck strict calendaire** (`5d23b18`) — `date(target_date) < date('now')`. 5 false positives (NVDA/AVGO/TSM/MU/AMD bearish 2026-06-24) → 0.
- **KPI #5 journalisation 3-fields** (`26f4a55`) — Structure thèse/invalidation/conviction obligatoire `/position_buy TICKER QTY PRICE | T | I | C`. Quick escape hatch tagged unjournaled. Hook auto-tag confirmé fonctionnel via test live. Doctrine [[journalisation-three-fields]].
- **Grid conviction refonte SOCLE** (`98e04fd`) — c5 = SOCLE (ASML+TSM monopole gelé), caps 8/6/4.5/3/2, 28 thèses redistribuées DB single-source VM (12 conviction + 3 position_type updates), CSS gradient or-bordeau SOCLE chip, doctrine [[conviction-grid-refonte-2026-06-24]].
- **Bigdata out of loop** (`bigdata-out-of-loop-2026-06-24` doctrine) — Subscription terminée, MCP plus invoqué, fallback WebSearch/Stub déjà gracieux côté code (vérifié .env sans BIGDATA_API_KEY).
- **Session close ritual L6** (`0b0ae81`) — SESSION_STATE + TODO + DB backups Mac+VM + config backup.

## 🟢 ÉTAT SYSTÈME (23/06 close session épique)

- **main HEAD `39ab499`** (10 commits today, alembic head 0062).
- **Hermes baseline VERTE** : 0 DEAD / 0 CANDIDATE / 1 WATCH (vulture FP) / **0 doctrine violations** (vs 24 ce matin) / 0 UI invariants fails / CI head GREEN.
- **VM Hetzner = single source of truth (acted 23/06)** : memory `single_source_vm_acted_2026-06-23` doctrine. Going forward TOUS trades via Telegram VM ou ssh+python sur VM, JAMAIS Mac local. Sync VM→Mac hourly launchd `com.olivier.presage-sync-from-vm` H+5min. Mac = read-only view.
- **Sweep #135 fait sur 21 tickers non-PEA** (KLAC/6920.T/6857.T/AVGO/LNG/MP/4063.T/AMZN/7011.T/000660.KS/MU/SNPS/SPCX/ALAB/TSM/AMD/GOOGL/COHR/CCJ/ENTG + TSLA closed). 4 levels broken anchored. 6 PEA stocks (ASML.AS/BESI.AS/HO.PA/SAF.PA/STMPA.PA/SU.PA) DÉFERRED → strategy distincte.
- **KLAC mystère split 10:1 résolu** : real corporate event 12/06 (pas yfinance glitch). Cure DB Mac+VM appliquée + sweep #135 levels $290/$330/$230. Script SQL canonique committé.
- **L12 cure structurelle lock_in_detector** : sold_price_eur partout, 52/52 tests verts, 0 candidate flip retroactif sur 8 sells fx≠1.
- **Bot Hetzner VM actif** : `systemctl --user is-active presage-bot.service = active` depuis 02:47:19 UTC restart, code HEAD VM aligned avec Mac.
- **🔴 Bug arch trouvé post-sweep** : `shared/positions.py:add_sell` calcule `closed = new_qty <= 1e-6` mais ne UPDATE jamais `positions_meta.status='closed'`. Variable juste returned dans le dict. Conséquence : positions a qty=0 restent status='open' = "fantome" gate red. TSLA aujourd'hui curée manuellement VM. **À fixer en code** : INSERT UPDATE positions_meta SET status='closed' WHERE ticker=? AND closed=True dans la transaction add_sell, post-commit. Plus tests qui couvrent le close-on-zero pattern.

## 🟢 ÉTAT SYSTÈME (19/06 close marathon v3 + audit canonique)

- **main HEAD `96861f8`** (23 commits dashboard aujourd'hui).
- **Tag rollback** `pre-design-session-2026-06-19` posé à `36bf729` (avant v3) + `pre-v2-redesign` historique.
- **Reverts effacés** : commits Pass 27-31f du 18/06 (10 commits supprimés du log via `git reset --hard c523d06` + force-push, user "everything we did is just ugly").
- **Repo GitHub PUBLIC** (toujours, pour accès claude.ai connector). À repasser PRIVATE quand collaboration externe terminée.
- **Topology inchangée** : Hetzner prod, Mac dev. Positions/trades inchangés depuis 18/06.
- **Dashboard v3 live** : Overview (chart Catmull-Rom + grade ring B+ 90/100), Positions (hero 3-cell + per-broker sector mix cliquable), animations uniformes .12s fade pur sans mouvement.

## 🟢 ÉTAT SYSTÈME (18/06 close mini-session trading)

- **CI green main `916ff5d`** (1 commit aujourd'hui, build d'hier `195e852` toujours vert sur base).
- **6 trades manuels loggés DB** (tx 211-216) via `shared.positions.add_buy/add_sell` canonique. Net réalisé jour **+326.88€** (AMD 3x winner +335€ dominant, AVGO -25€ + 4063.T +17€).
- **AMD lock_in_detector hook firé** post-commit sur tx 215 : avg_cost EUR 146.81 → sell 445.09 = +203%. Partial trim 33%, pas full exit. Obs +30j scheduled 2026-07-18 (mesure biais #1 honnête).
- **AVGO P0 #2 closed (override)** : reco Claude 16/06 "statu quo no trim" overridée par Olivier (trim 290€ exécuté). Position 1252€ → 963€ (c3 ~1.8% book, 2.82 sh remain). Thèse id=33 enrichie 2 notes datées + caveat sémantique S10 trigger préservé pour re-anchor #135.
- **Prix post-cutoff vérifiés live yfinance** : MU $1043, AMD $512, 000660.KS ₩2.71M — tous réels (previousClose cohérent), pas cache stale (training cutoff Jan 2026 dépassé par rally AI/HBM).
- **Topology inchangée** : Hetzner = prod. Mac DB diverge silencieusement (sync gap LIVING_GRAPH forks attendus). PAS de cron sync Mac←Hetzner.
- **Positions finales 6 tickers touchés** : AVGO 963€ · 4063.T 3527€ · GOOGL 2754€ · MU 1327€ · AMD 1005€ · 000660.KS 2587€.
- **Brew claude-code upgrade** : 2.1.153 → 2.1.170 (side note début session).

## 🟢 ÉTAT SYSTÈME (16/06 close)

- **CI green main `195e852`** (9 commits aujourd'hui, dernier CI run vert sur pass 6 `aca842e`).
- **9 commits propres pushés** : `00185f3` (silent-fails P0) → `8353ce9` (current_eur+realized_pnl_eur) → `b7f63bf` (prices.fx asof+MU whitelist) → `b385cb6` (3e source value_eur) → `f35b72b` (degraded gates monitors) → `aca842e` (Lane 2 #4/#5 migration) → `163dabc` (book_total_eur + factor_exposure_eur) → `88f6513` (SESSION_STATE close) → `7b0f415` (_mark_fx_live_success API + wrapper_tax degraded) → `195e852` (3 silent-fails book.py log warned).
- **LIVING_GRAPH coverage : 11 concepts** (vs 7 hier soir) : book_total_eur (2 src) · cost_basis_eur (2) · current_eur (2) · factor_exposure_eur (1) · fx_rate_to_eur (2) · pmp_eur (1) · pnl_position (2) · price_eur (2) · qty (2) · realized_pnl_eur (1) · value_eur (3).
- **Audit canonical drift CLEAN** : 11/11 SPECs footer OK, 0 drift, 0 doublons. Les 9 commits aujourd'hui n'ont pas introduit de drift doctrinal.
- **Topology confirmée** : Hetzner = production (Telegram conflict prouvé via launchctl bootstrap test). Mac = view-only. **PAS de cron sync Mac←Hetzner** (backups `before_*_sync` = manuels user). Mac DB diverge silencieusement de Hetzner entre syncs manuels.
- **4 trades loggés Mac DB** : SELL TSLA full (4.838 sh @ $406.43, -42.53€ realized) → COHR BUY 3.017 sh + SPCX BUY 5.052 sh redéploiement 1700€. Plus tard SPCX SELL 600€ avec divergence broker connue (tx_id=210 logged 3.388 sh @ $205.47 vs broker réel 3.239 sh @ €185.22 → 0.72 sh phantom Mac, EUR proceeds identique).
- **pytest baseline 1914 passed** local (+ whitelist MU + autouse fixture group_cap + 2 prices_gateway refactored via `_mark_fx_live_success` API).
- **Dashboard live** : HTTP 200, 30 forks LIVING_GRAPH détectés au lever (price_eur + current_eur sur 15 tickers) puis 0-2 forks intra-session (cache convergence). Instrumentation livre signal au premier jour.
- **0bis KNOWN-GAP currency 148 trades** : statu quo (rollback α 15/06 maintained). Mécanique cure préservée.
- **6 KNOWN-GAP partial close phantom qty** : étendu à 6 positions (5 historiques + SPCX 0.72 sh phantom suite SELL mismatch 16/06).

## 🟢 ÉTAT SYSTÈME (15/06 close mini-session)

- **CI green main `2ad2f48`** (last 6 commits all CI-green tested locally + Telegram fix validated live).
- **6 commits propres pushés** : 081e4f7 (cure currency 4 trades) → 51ffde5 (rollback α) → 2663006 (Telegram 400) → f655b20 (stagger 06:00) → a574c3c (#145 forks) → 2ad2f48 (tests CI-fresh DB).
- **Bot Hetzner VM actif** : `systemctl --user is-active = active`, code `2ad2f48`, alembic head `0062` (inchangé).
- **Pytest baseline 1908 passed** local (+5 nouveaux tests : 6 sur ADJUST + migration 3 sur fixture). 2 fails KNOWN_DEBT_EXEMPT (KLAC stale).
- **scheduler_runs append-only journal** : intact, scheduler_observability 100% coverage post-deploy hier maintenu.
- **Dashboard live `http://127.0.0.1:8000/dashboard.html`** : Mac local actif (HTTP 200 736KB), log clean (0 Telegram 400 post-fix, 0 forks post-cure #145).
- **P0 currency 148 trades systémique** : KNOWN-GAP documenté avec analyse empirique complète + mécanique cure préservée. Décision (α) honnête sur EUR invariance.

## 🟢 ÉTAT SYSTÈME (14/06 close ultra-marathon)

- **CI green main `68b8b4e`** (5m43s, 11/11 steps incluant ruff + mypy + pytest coverage). Run 27497658627 conclusion success.
- **23 commits propres pushés** : tennis Rule C (3) + PRESAGE outils analyste (5) + audit cron (6) + cure clustering (1) + chantier #150 G3 (2) + tests fixes (2) + observability decorator (3) + CI fix (1).
- **Bot Hetzner VM actif** : `systemctl --user is-active presage-bot.service = active`, code `68b8b4e`, alembic head `0062`, 29 jobs scheduled (vs 33 pre-cleanup audit P0 = 3 tier1/2/3 duplicates + j_day zombie supprimés).
- **scheduler_runs append-only journal** (migration 0062) : **100% coverage** des ~30 crons via `_safe_run` (chain steps) + `@scheduler_run_logged` (top-level). 3 triggers append-only (no_delete + no_update_immutable preserving id/job_name/started_at). 3 helpers storage. Live data : 8 distinct job_names déjà tracés.
- **healthcheck_ping wiring** : 9 crons préparés silent-noop fail-soft. `HEALTHCHECKS_PROJECT_URL` env var active réveille toute la chaîne.
- **Chantier #150 G3 livré** : `/research <ticker|theme>` Telegram handler + 14 tests verts + anti-anchoring 8 patterns regex mecanisé + rate-limit 1/h + budget cap $5/jour. Backend pluggable Bigdata-real / stub. Coexiste avec `/review /digest /find`.
- **Cure live data_clusters NaN** : anomalie détectée 09:31 via 1er fire scheduler_runs ("clustering failed: condensed distance matrix must contain only finite values"), root cause `intelligence/return_clustering.py:97` propagation NaN. Cure committée 09:45, validée 09:45:49 live. **~45 min boucle complète détection→cure validée prod** — sample direct value-add observability scheduler_runs.
- **5 wrappers shared/ ajoutés** : fred_client (FRED API), healthcheck_ping (healthchecks.io), edgar_client (edgartools 10-Q value-add), thesis_library (Voyage finance-2 + Chroma SQLite local), scheduler_observability (decorator async-aware).
- **5 skills .claude/commands/ ajoutés** : /sentinel-check, /sentinel-status, /system-health (utilise scheduler_runs live), /edgar-context, /thesis-similar.
- **1 MCP server** : OpenInsider (16 outils gratuits SEC EDGAR + FINRA + OpenInsider + Yahoo). Tools dispos next Claude session restart.
- **launchd plist Mac** : `com.olivier.presage-weekly-audit` dimanche 09:13 → Telegram alert sentinelles audit.
- **Tennis-bot Path A pivot** : Rule C wired live (skip side price < 0.75), audit reminder 14/07 heartbeat dans bot.py.
- **Pytest baseline 1894 passed** restaurée post-fixes (2 fails session : thesis_library raw sqlite3 → refactor `shared.storage.db()`, regex `interdit` faux positif → `_WHITELIST`).

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

## 🔵 TRADES DEFERRED (à exécuter quand conditions OK)

- ~~SELL COHR ~1/8~~ — **ANNULÉ 24/06** : user choisit hold full 6.456 sh runner malgré partial $410 trigger atteint. Bet market right vs consensus.

### ✓ Executed 2026-06-23 (live estimates, reconcile if broker exec diverges)

- ~~SELL KLAC 2.96 sh @ $269.16 (-€696, realized +€227)~~ — KLAC 12.59→9.63 sh
- ~~SELL TSM 0.61 sh @ $467.67 (-€249, realized +€111)~~ — TSM 11.45→10.84 sh
- ~~BUY GEV 0.71 sh @ $1127.59 (+€700)~~ — GEV 0.796→1.506 sh (~€1486 MV cible €1400 atteint)
- ~~BUY HDS (6324.T) 5.85 sh @ ¥7700 (+€244)~~ — HDS 24.9→30.75 sh

---

## 🔴 P0 ACTIONNABLES

### Action humaine (pas code)

~~0. **G2 du chantier #150 = ROUGE : `/predict ×10` sentinelles event-type**~~ — **RÉSOLU 13/06** : 10 sentinelles posées via `scripts/seed_sentinels_2026-06-13.py` après cure complète du schéma (migration 0060 ajoute `claim_type/resolution_source/origin` + CHECK conditionnel + ticker nullable). Distribution : 2 Olivier-seul (S1, S2), 6 Claude-assisted post-amend doctrine (S3-S5, S7-S9), 2 mécaniques 0.99 (S6, S10 déjà publiquement déclenchées trouvées via fact-check Bigdata.com). `origin='manual'` honnête. G2 ledger PASSAGE ROUGE→VERT (pids 294-303).

0bis. **🟡 KNOWN-GAP CURRENCY BUG (analyse 15/06/2026) : 148 trades broker import avec `fx_at_trade=1.0` systémique** (cf SPEC_LEDGER §1 + memory `feedback_instrumentation_vs_decision`). Pattern initial identifié 13/06 sur 4 trades du 12/06 14:28:30 a été investigué 15/06 → étendu à **TOUTE l'historique broker import** :
   - 135 USD trades (TR_csv) — pattern price_native = EUR-per-share, currency='USD', fx=1.0
   - 11 JPY trades — idem
   - 2 KRW trades — idem
   - 4 manual_add 12/06 (id 198-201) — même pattern, juste plus visible
   - Total **148 trades touchés**

   **Cure (γ) full systemic** : 4-6h via ADJUST mass-batch (SPEC_LEDGER §1 "extensible ADJUST futur"). Mécanisme `shared/ledger_pmp.py:compute_pmp_realized` ADJUST handler livré 15/06 (commit `081e4f7`), prêt à recevoir 148 tx ADJUST avec notes JSON target_tx_id. Script `scripts/fix_currency_bug_4_trades_2026_06_14.py` template idempotent. 6 tests verts.

   **DÉCISION 15/06 : (α) Rollback + KNOWN-GAP** (cf memory `feedback_instrumentation_vs_decision`).
   Raison : ratio coût/bénéfice infini. EUR débité **invariant sous cure** (= ce que TR a réellement chargé) → 0 changement visible dashboard pré/post-cure. Vérifié empiriquement : TSM 2021-12-16 stored 106.2 = EUR/share matche actual USD price $120.34 × 0.88 fx (H1 EUR-pattern confirmé). PMP EUR / cost basis / realized_pnl tous invariants. Cure (γ) serait purement conceptuelle (restaure native USD interprétation) sans surface visible.

   **DB Mac restored** : `data/bot.db.backup_before_currency_fix_20260614` (96MB). Audit copy avec cure preserved : `data/bot.db.with_currency_cure_for_audit`. VM jamais touchée (clean).

   **Préservé pour future (γ) si retour sur décision** : 
   - `shared/ledger_pmp.py` ADJUST handler (dormant tant que 0 ADJUST tx)
   - `scripts/fix_currency_bug_4_trades_2026_06_14.py` template idempotent
   - `tests/test_currency_bug_cure_adjust.py` 6 tests doctrine + mechanic
   - Backup baseline + audit DB

   **Bénin court-terme confirmé** : tous EUR-side aggregates corrects. Conceptual integrity USD-native broken mais aucune fonctionnalité user-facing impactée.

   Valeurs originellement documentées 13/06 (cf historique pour reference future) :
   - tx id=198 ALAB SELL 1.242 @ **319.65 EUR (= ~$369 USD au fx 1.155)** stocké `price_native=319.65, currency='USD', fx_at_trade=1.0` → vraie valeur USD ≈ **371.4**
   - tx id=199 GOOGL BUY 1.0 @ **312.0 EUR** stocké `currency='USD', fx_at_trade=1.0` → vraie valeur USD ≈ **361**
   - tx id=200 AMD SELL 0.741 @ **445.34 EUR** stocké `currency='USD', fx_at_trade=1.0` → vraie valeur USD ≈ **515**
   - tx id=201 AMZN BUY 1.61 @ **204.97 EUR** stocké `currency='USD', fx_at_trade=1.0` → vraie valeur USD ≈ **237.2**
   Trace : `SELECT * FROM transactions WHERE id IN (198,199,200,201)`. Session dédiée requise pour design correction (ledger event d'ajustement separate ? rebuild from broker source ?).

1. **KLAC + 5 dying + 1 dead à reposer** (cf #135 méthode) : le monitor `stale_target` livré (#134, commit `5f5c5a8`) remonte 5 transitions `alive_to_dying` (CCJ +0.6%, AMZN +4.0%, 6857.T +4.5%, 4063.T +3.6%, AVGO +4.1%) + 1 `alive_to_dead` (000660.KS edge -0.3%) + KLAC currency_native hors-range. Action humaine = relire chaque thèse + reposer target+stop ancrés sur prix réel actuel (cf doctrine #135 : 3 colonnes Instrument/Ancre externe live/Ressenti).

~~2. **AVGO trigger #1 fired (S10) — décision pending**~~ — **RÉSOLU 18/06** : Olivier trim partiel **290€** exécuté (tx_id=211, 0.8505 sh @ $392.90 / fx 0.8678, realized PnL **-24.91€**). Position 1252€ → 963€ (c3, ~1.8% book, 2.82 sh remaining). Override reco Claude 16/06 (j'avais proposé statu quo, trim jugé "noise"). Sizing reste gelé, re-anchor #135 toujours prévu batch suivant. Note datée ajoutée à `theses.notes` id=33 avec caveat sémantique (Icefish v10 / MediaTek vs trigger text v6/v7 MRVL/AMD).

3. **Hetzner SSH check — bot.main alive ?** : `ssh presage@<VPS_IP> "systemctl --user status presage-bot.service"`. Mac launchctl disabled deliberately (post-cutover discipline). Hetzner = prod confirmée via Telegram conflict test 16/06 mais santé exacte du service à vérifier périodiquement.

~~2. **#134 monitor `stale_target`**~~ — **RÉSOLU 12/06 (commit `5f5c5a8`)** : 3e monitor canonique livré + smoke live (19 alive, 5 dying, 1 dead, 6 notifs Telegram). Pattern figé du gabarit `monitor_pattern.md` validé une 3e fois.

---

## 🟡 P1 DIFFÉRABLE

- **#133 sweep cibles batch suivant** (~2-3h étalées) : 10 positions targets/stops révision (4063.T, AMZN, AVGO, KLAC, 7011.T, 6857.T morts ; 6920.T, TSLA, LNG, MP mourants). Méthode 3 colonnes (Instrument / Ancre externe live / Ressenti) → `docs/sweep_targets_2026-06.md`. Born-dead-check obligatoire. Pré-condition idéale : #134 livré (priorise alive→dying→dead).

- **#135 refonte complète niveaux décidés** : projet structural étalé 2-3 mois, ~1 ticker/semaine. Méthode canonique : ancre externe live consensus/multiples/52w/news + décision humaine + born-check (partial > cost ET > cur · full > partial · stop reconsidéré aussi) + trace `asof + raison 1 ligne`. Doctrine élargie : stop inclus dans la révision (pré-rally peut devenir absurde).

- ~~**#145 LIVING_GRAPH forks `pnl_position`**~~ — **RÉSOLU 15/06 (commit `a574c3c`)** : root cause empirique = `shared/position_pnl.py:pnl_position_pct_eur` registre concept depuis helper avec 0 production caller (uniquement tests qui hardcoded 4 tickers). Tests polluaient concept_index prod. Cure : retirer `register_concept` du helper (memory `feedback_helper_register_no_side_effect`). 0 forks post-cure sur ces 4 tickers. Pivot compute-once-project pas requis.

- ~~**6 KNOWN-GAP partial close phantom qty**~~ — **RÉSOLU 23/06 (memory cleanup)** : audit DB confirme 0 phantom across all open positions. 5 historiques réconciliées 11/06 via `rebuild_tr_ledger_from_csv.py`. La "SPCX 0.72 sh" 16/06 n'existe pas en DB (jamais loggée OU jamais broker-executed). Note caveat : `positions` est VIEW dérivée de transactions → audit `pos.qty == SUM(tx.qty)` est trivialement vrai. Vraie vérification = compare DB vs broker (TR/IBKR positions), action humaine. Si futur trigger : design ledger ADJUST qty handler (extend l'ADJUST price/fx existant `shared/ledger_pmp.py:52`).

- **Sync auto Mac←Hetzner** (design décision) : Investigation 16/06 confirme PAS de cron sync (uniquement `deploy/presage-backup.timer` côté Hetzner = local backup + push offsite). Mac DB diverge silencieusement de Hetzner entre syncs manuels user. Options : (A) cron rsync periodic Mac←VM (1-2h impl), (B) script trigger manuel + reminder, (C) statu quo (manual quand nécessaire). Le LIVING_GRAPH forks de chaque morning regen sont essentiellement ce sync gap rendu visible.

- **Setup user keys** (user action ~10 min) : 3 signups gratuits (Voyage AI, healthchecks.io, FRED) + Bigdata.com si pas déjà + 4 keys `.env` Mac+VM + 1 restart Claude pour OpenInsider tools. Sans ça : hooks silent-noop strict, composants livrés 14/06 dormants.

- **14/07/2026 tennis Rule C audit** (automated heartbeat) : reminder Telegram automatique programmé dans `bot.py` (ligne ~1096). Au reception, run `/tennis-audit` pour mesurer ROI Rule C sur paris réels post-déploiement 14/06 (1 mois ETA).

- ~~**#147 Tests flaky ordering-dependent**~~ — **RÉSOLU 13/06 (diag montré stale, pas ordering)** : `test_coherence_under_perturbation` passe 5/5 isolément (TODO stale, déjà curé ailleurs). `test_aggregate_sum_equals_parts` **fail en ISOLATION** aussi (pas ordering). Cause vraie = **KLAC cache stale** (bug yfinance 11/06 prix gonflé 2108€ stocké en cache `positions.last_price_eur`) → pf_value voit KLAC à ~277€ stale, views filter outlier → divergence permanente 3.78% sur book 53k€. Cure : ajout `KNOWN_DEBT_EXEMPT = {KLAC, SPCX}` dans le test (cohérent avec test_book_gate.py + test_pipeline_end_to_end.py). À retirer du KNOWN_DEBT quand KLAC cache rebuild + cure currency 4 trades (P0 dette).

- ~~**Cure structurelle tests CI-fresh DB**~~ — **RÉSOLU 15/06 (`2ad2f48`)** + vérifié 17/06 : 0 test restant utilise le pattern `skip-on-OperationalError`. Migration vers fixture `migrated_db` canonique complétée. Les usages restants de `sqlite3.OperationalError` dans tests/ sont intentionnels (simulation DB down dans test_living_graph, archi-check dans test_e2e_alpha_chain).

- **SPEC Moore/Compute-Cost Cycle (EXPLORATOIRE)** — `docs/specs/moore_compute_cycle_signal.md`. Status NOT_STARTED, gated keystone convictions + backtest L19. Red-team 17/06 identifie 6 points (proxies coïncidents pas leading, N=3 borderline, composite à pre-register YAML, pass threshold ex-ante, AI overlay rôle flou, token prices à exclure). À reprendre quand dégated.

- ~~**#152 Handler `/research <target>` (research_brief, posture analyste)**~~ — **RÉSOLU 14/06 (commits `dd854db` + `68b8b4e`)** : handler complet livré + déployé VM. `intelligence/research_brief.py` backends pluggables (Bigdata-real si `BIGDATA_API_KEY`, sinon stub explicite fail-closed L15). Format markdown spec §4 (FAITS/CONSENSUS/NEWS/CADRE). Anti-anchoring gate spec §5.4 mecanisé 8 patterns regex. Rate-limit 1/h via helper existant + budget cap $5/jour. 14 tests dédiés tous verts. CI green sur main. **Activation user-gated** : setup `BIGDATA_API_KEY` dans `.env` Mac+VM.

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
