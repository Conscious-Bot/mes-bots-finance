# SESSION_STATE — mes-bots-finance

> Last updated: 2026-05-11 evening (Korea time)
> Bot owner: Olivier
> Working dir: /Users/olivierlegendre/mes-bots-finance

---

## 🟢 Current State (bot live)

- **33 Telegram handlers**, **9 crons** running
- Watchlist: 76 tickers (AI/semis core, tech mega-cap, crypto proxies, commodities, financials, ADRs)
- Active thesis: **NVDA long** (entry $130 / partial $250 / full $400 / stop $170)
- Active positions: **NONE** ← user must bootstrap via /position_set
- LLM cost ongoing: ~$0.50/mo enriched digest + ~$0.04/call /analyze

**Crons schedule** : heartbeat 1h • gmail 1h • calendar 5h • insider 6h • digest 7h • resolve 9h • price_monitor 15min mkt hours • crypto 10h • buy_cluster_scan 6:20

**Singleton run** : `nohup python -m bot.main > bot.log 2>&1 &`

---

## 📦 Last Session (2026-05-11 evening, ~8h)

### Shipped
- **Phase 5** Price Monitor + Thesis Triggers (already)
- **Phase 6** Crypto Top-Zone (already)
- **Phase 7** Position Tracking (already)
- **Phase 11** Materiality scoring + LLM why_matters (THIS SESSION)
- **Phase 12.1** Insider Cluster Detection (THIS SESSION)
- **Phase 16** Credit Markets HY/IG OAS via FRED (THIS SESSION)
- **/analyze TICKER** deep fiche (yfinance + EDGAR + LLM) (THIS SESSION)

### New modules
- `intelligence/analyze.py` — deep company fiche generator
- `intelligence/materiality.py` — 4 sub-scorers (novelty/cross-conf/market_impact/regime_relevance) + composite
- `intelligence/why_matters.py` — LLM 1-sentence annotator
- `shared/macro.py:get_credit_regime()` + helpers
- `shared/edgar.py:get_insider_cluster()` + classification + format
- DB table: `conviction_history` + 3 indexes

### Empirical insights révélés
- **HY OAS 279bp = TIGHT** (sub-300bp) = complaisance crédit historique, late-cycle
- **AVGO insider** $356M sells / **70% c'est Samueli** (co-fondateur routine), **ex-top concentration 32%** = ISG President + SSG President + CFO + Legal = vraie distribution operational leadership
- **NVDA insider** $164M / **67% c'est Puri** (sales head, $109M, anormal), 5 autres sellers à $54M = routine 10b5-1
- **/analyze NVDA** verdict : pas d'add à $215, WAIT for $170-185 post-earnings 21/05
- Yield curve +0.48% (re-steepened post-inversion) + HY 279bp + insider distribution AI/semis = **late-cycle confirmé sur tous les axes**

### Bugs fixed
1. Orphan functions définies après `if __name__ == "__main__"` (cmd_macro, cmd_insider_digest, scheduled_insider_refresh_job)
2. send_telegram → notify.send_text
3. FRED SSL cert macOS Python 3.14 (certifi installer)
4. .env FRED_API_KEY dedup (3 lignes empilées)
5. Phase 12.1 threshold calibration (is_buy_cluster requires moderate+ classification)
6. Materiality schema mismatch (entities/narratives/sentiment not ticker/claim_type/polarity)
7. Tickerless signals getting max novelty (false positives)
8. TICKER_BLACKLIST (IA, HTML, JSON) + LARGE_CAP expansions
9. Cluster cron registered to non-existent `scheduler` (renamed `sched`)
10. Phase 11 dedup query (SELECT MAX(id) GROUP BY signal_id)
11. Phase 11 persist ordering (why_matters BEFORE persist)
12. `/analyze` double cluster_section ref (idempotency)
13. edgar_mod alias (not `edgar`) in handler refs

---

## ⏳ Pending User Actions

1. **Bootstrap positions réelles via Telegram** (débloque personalization Phase 5/6/7) :
/position_set NVDA <qty> <avg_cost>
/position_set BTC-USD <qty> <cost>
/position_set ETH-USD <qty> <cost>
2. **Observer 10 jours** : CPI 13/05 (J+2), NVDA earnings **21/05 (J+10)** — catalyseur clé, NFP 5/06, FOMC 17/06
3. **Demain matin 7h Paris** : vérifier le 1er digest enrichi avec section TOP MATERIAL SIGNALS
4. **Smoke test `/analyze AVGO`** sur Telegram pour valider la perception LLM sur AVGO vs NVDA insider patterns

---

## 🎯 Next Session Priorities (par ROI décroissant)

### High
1. **Phase 12.2** Supplier confirmation : TSMC + ASML + SK Hynix capex consistency cross-check (2-3h)
2. **Phase 13** Guidance language tracking : parse "raised/cautious/visibility" earnings transcripts Motley Fool (2-3h)
3. **/analyze** : étendre le LLM prompt pour utiliser plus profondément le cluster + credit data (15min polish)

### Medium
4. **Phase 14** Evidence graph per thesis : table evidence(thesis_id, signal_id, polarity, weight), conviction auto-updates (3-4h)
5. **Cron** : auto-trigger /analyze sur tickers thesis active après earnings (event-driven) (1-2h)
6. **Decision Journal** : log thesis decisions + why + outcome (J+90 review) (2-3h)

### Backlog (≥4-6 semaines de data)
7. **Phase 8** Cross-source consensus (50+ signals accumulés requis)
8. **Phase 10** BiasDetector review (J+90 = 2026-08-09)
9. **Phase 17** Second-order effects impact graph (heavy maintenance, gain marginal)

### ❌ Rejected
- OpenBB (300MB vendor lock)
- Finnhub (worse insider data than EDGAR direct)
- PyPortfolioOpt (anti-pattern pour thesis-driven concentré)
- vectorbt (wrong tool)
- sec-edgar-downloader (redundant)
- Coverage Europe insider data (low ROI vs 90% watchlist US/ADR)

---

## 🛠 Setup & Recovery

- bot.db at `data/bot.db`, sqlite, ~50MB
- FRED_API_KEY in `.env` (user a refusé rotation, "n'a aucune importance")
- Gmail OAuth tokens in `.tokens/`
- Latest backup: `.backups/20260511_evening/`
- `bot.log` rotates manually; `tail -100 bot.log` pour debug

**Restart sequence si bot crashe** :
pkill -f bot.main && sleep 3 && nohup python -m bot.main > bot.log 2>&1 &
sleep 4 && tail -10 bot.log

**Resume next session** : lire ce fichier en premier, puis vérifier `ps aux | grep bot.main` que le bot tourne toujours.


---

## 🏁 Phase 18 closed (12/05/2026 ~ 8h KST)

**Batches 1+2+3 livrés et validés** :
- **B1** : schema `decisions` (12 cols + 4 idx), 7 storage helpers, `intelligence/journal.py` (auto_classify_mistake + thesis_relative_position + format_decision_summary).
- **B2** : 4 handlers Telegram (`/journal`, `/journal_review`, `/journal_unresolved`, `/journal_tag`) avec auto-injection price/regime/credit/thesis/materiality.
- **B3** : cron `resolve_journal_decisions_job` 8h Paris quotidien — auto-resolve J+30 + J+90 avec mistake tagging. Smoke test 100% green: NVDA entry $200 → resolved at $219.44 (+9.72%) → `between_entry_and_partial` + `entry_correct`.

Bugs corrigés : `await notify.send_text` (4 occurrences, dont 2 latentes Phase 17/early), `thesis_relative_position` priority order pour structure stop>entry (NVDA), indent dynamique pour add_handler, credit_str nested dict access.

**Boucle d'apprentissage fermée** : log → 30j/90j auto-resolve → `/journal_review` agrège patterns → révèle biais asymétriques (vend trop tôt AI/semis vs tient trop long crypto).

## 🧭 Nouveau framework architectural (12/05/2026)

Cf `ARCHITECTURE.md` (nouveau doc racine). Le système se pense désormais en **7 stages**: Structure → Data → Entonnoir → Signaux → Reflection → Appropriation → Restitution.

**Diagnostic** : système lourd aux extrémités (1, 2, 7), léger au centre (3, 4). Goulot = Stage 3 (entonnoir de qualité). Roadmap stage-weighted dans `TODO.md`.

**Next action recommandée** : Action 1 = Brier calibration (Stage 3, ~1h). En pause: user upload de nouvelles idées à classifier par stage avant de reprendre.


---

## 🧭 Re-priorisation tranches A-E (12/05/2026 ~ 9h KST)

User a uploadé doc externe ~30 ideas Bloomberg-adjacent. Critique + ranking + intégration dans `ARCHITECTURE.md` section "Tranches actives" + `TODO.md` Tranches A-E détaillées (15 tâches concrètes).

**Contraintes binding** : capacité cognitive système (pas de bloat features), budget data ~$75/mo max.

**Plan exécution** :
- **Tranche A** (4 tâches, ~9h) : Stage 3 musclage — Brier + cascade LLM routing + echo chamber + half-life
- **Tranche B** (3 tâches, ~7h) : Stage 6 — position book + bias tagging + pre-mortem
- **Tranche C** (4 tâches, ~9h + $14/mo FMP) : Stage 5 cross-stitching — EPS revisions + adversarial + asymmetry + confidence intervals
- **Tranche D** (4 tâches, ~11h) : Stage 4 — LanceDB + case-based + anti-narrative + corroboration

**Leviers stratégiques identifiés** :
- **A2 cascade LLM routing** — débloque budget de tout le reste (-60 à -80% coût)
- **B7 Pre-Mortem auto-gen** — seule feature forçant exit discipline pre-commit

**Skip définitif** : Causal DAG Pearl, paralinguistic earnings, Pydantic+mypy strict, Postgres migration, Ortex/WhaleWisdom, property-based tests exhaustifs.

**Next action concrete** : A1 Brier calibration (~1h, déjà dans TODO depuis hier soir).


---

## ✅ A1 Brier calibration shipped (12/05/2026 ~ 8:35 KST)

**Livrables** :
- Schema migration : `predictions.probability_at_creation`, `predictions.brier_score`, `conviction_history.source_credibility_at_persist`
- `storage.insert_prediction` enrichi : snapshot `source.credibility` via JOIN signals→sources au moment de création
- `learning.py:resolve_due_predictions` : compute `brier_score = (probability - outcome_binary)^2` au moment résolution. Binary mapping : correct=1.0, incorrect=0.0, neutral=0.5
- `storage.recalibrate_source_credibility_from_brier(min_n=10)` : helper de recalibration mensuelle
- `storage.get_brier_stats_by_source()` : helper d'aggregation pour display
- Cron `recalibrate_credibility_brier_job` programmé 1er de chaque mois à 6h Paris
- Handler `/sources_brier` : affiche per-source brier + cred + n_correct/neutral/incorrect

**Coexistence avec delta-based system** : Le mécanisme `update_source_credibility` (±0.05 par outcome dans learning_mod) tourne toujours en parallèle. Brier recalibration mensuelle override quand N>=10. Décider plus tard si on désactive delta-based.

**Smoke test** : (0.50 - 1.0)² = 0.2500 brier validé math + persistance + stats helper + cleanup tous OK.

**Status** : A1 closed. Tranche A reste : A2 cascade LLM routing + prefix caching (~3h, levier stratégique #1) → A3 Echo Chamber Resolution (~3h) → A4 Information Half-Life (~2h).


---

## ✅ A2a Cascade LLM wrapper shipped (12/05/2026 ~ 8:42 KST)

**Livrables** :
- Table `llm_calls` : log de chaque call (tier, model, task, in/out/cached tokens, cost_usd, elapsed_ms, error)
- `config.yaml` enrichi : section `tiers:` (extract→Haiku, enrich→Sonnet, synthesize→Opus) + section `pricing:` (per-1M input/output/cached_input USD)
- `shared/llm.py` réécrit : nouveau param `tier='extract|enrich|synthesize'` qui override le `task` legacy. Param `cache_invariant=` pour prefix caching ephemeral 5min. Logging automatique. Cost computed via config pricing table.
- Handler `/llm_costs [hours]` : aggregation by tier × model, total calls, total cost, cache hit %
- Backward compat 100% : `task='signal_scoring'` continue à mapper Haiku, etc.

**Smoke test empirique** :
- Haiku $0.00010/call (~860ms)
- Sonnet $0.00127/call (~2700ms)
- Opus $0.00664/call (~2500ms)
- Ratio Opus/Haiku = **66x**

**Reste de A2 (~30min, optionnel) — A2b** :
- Migration des 3 call sites pour tier explicite (semantic polish, no functional change)
- Intégration `cache_invariant=` pour digest.py (highest call volume → biggest cache savings)
- Cost: aucun bénéfice tant que cache_invariant pas appliqué

**Tranche A status** : A1 ✅ + A2a ✅. Reste A3 (echo chamber semantic dedup, ~3h), A4 (info half-life, ~2h), et le A2b polish.


---

## ✅ A3 Echo Chamber Resolution shipped (12/05/2026 ~ 9:00 KST)

**Livrables** :
- `shared/embeddings.py` : wrapper BGE-small (sentence-transformers, local, 384 dims, free)
- Table `signal_embeddings(signal_id, embedding BLOB, model, embedded_at)` + col `signals.echo_cluster_id`
- 4 storage helpers : `store_signal_embedding`, `get_signal_embedding`, `get_unembedded_signals`, `get_embedded_signals_window`, `set_echo_cluster_id`
- `shared/echo.py` : compute_clusters (union-find sur cosine sim > 0.85), persist_clusters, get_recent_multi_source_clusters
- Cron `update_echo_clusters_job` (every 1h) : embed pending + recompute clusters
- Handler `/echo_recent [hours]`
- Filter upstream `_is_onboarding_noise` in `data_sources/gmail_.py` : 32 patterns multilingue (EN/FR/ES/DE/IT)

**Empirical validation** :
- 58 signaux backfilled → 47 après cleanup noise → 0 multi-source cluster avec data actuelle
- BGE-small empirique : paraphrase NVDA = 0.931, NVDA vs AAPL = 0.43 (gap large)
- A3 a servi de DIAGNOSTIC TOOL : a révélé pollution Gmail ingestion + 93% signaux sans entities

**Cleanup data quality effectué** :
- 11 signaux noise supprimés (welcome emails EN+FR + Error: prefix LLM failures)
- 64 conviction_history rows cascade-deleted
- 12 embeddings cleaned

**Bugs latents identifiés (non-corrigés ici)** :
- LLM Error response persisté en `summary='Error: ...'` au lieu de NULL+retry
- 93% des signaux sans `entities` extraits (54/58 avant cleanup) — entity extraction silent fail ou non-wired

**Tranche A status** : A1 ✅ + A2a ✅ + A3 ✅. Reste A4 Information Half-Life (~2h, infra-latent comme Brier).


---

## ✅ Entity extraction backlog fix (12/05/2026 ~ 9:10 KST)

**Bug diagnostiqué via A3** : digest cron quotidien plafonné à `limit=20` signaux/jour, mais ~30-50 signaux/jour ingérés → backlog cumulatif. Résultat : 81% des signaux n'avaient jamais traversé le LLM scoring.

**Fix** :
- Nouveau cron `score_pending_signals_job` toutes les heures (`process_unprocessed(limit=50)`) — suit le rythme gmail 1h
- Backfill manuel des 38 NULL signaux existants

**Résultats** :
- 38 signaux scorés en 153s (Haiku via signal_scoring, ~4s/signal)
- 19/47 ont maintenant entities (tickers extraits)
- 28/47 entities=[] (legit, pas de ticker mentionné)
- **0 NULL restant**
- 40 nouvelles predictions auto-registered → Brier loop alimentée

**Side benefit** : pipeline ticker-based maintenant fonctionnel (/orphan_tickers, materiality.extract_tickers, echo cluster sur ticker-relevant signals).

**Bugs latents non corrigés** (toujours dans TODO) :
- LLM Error response persisté en summary='Error:...' (au lieu de retry NULL)
- LLM-based noise classifier post-ingestion (welcome FR non-anglais, educational content)


---

## ✅ B5 Position book shipped (12/05/2026 ~ 9:40 KST)

**Livrables** :
- Réutilisation table `positions` existante (schema déjà présent : qty/avg_cost/status/realized_pnl/opened_at/last_updated)
- 5 storage helpers : `create_or_update_position_on_buy`, `record_position_sell`, `get_active_positions`, `get_position_by_ticker`, `get_positions_history`
- 4 handlers Telegram : `/position_buy`, `/position_sell`, `/portfolio`, `/position_history`
- Helper `_portfolio_journal_ctx` partagé pour auto-injection context (price/regime/credit/thesis/materiality_top)
- **Auto-journal hook** : chaque /position_buy → log_decision('entry' ou 'scale_in'), chaque /position_sell → log_decision('partial_exit' ou 'full_exit')
- Display `/portfolio` enrichi avec market value live (yfinance) + unrealized PnL + concentration %

**Smoke test** : entry $215.50 → scale_in $220 ($217 avg) → partial_exit $230 (+$65 rpnl) → full_exit $240 (+$230 rpnl, total $295). Math 100% validée.

**Bilan B5** : Phase 18 industrialisée. Plus besoin de /journal manuel, les trades auto-loguent. Use case clef débloqué : alerte "overweight AI 45% materiality flashe rouge" maintenant computable.

**Tranche B status** : B5 ✅. Reste B6 bias tagging extension Phase 18 (~2h) + B7 Pre-Mortem auto-gen sur création thesis (~2h).


---

## ✅ B6 + B7 shipped — Tranche B complete (12/05/2026 ~ 9:50 KST)

### B6 Bias tagging extension Phase 18
- Schema : `decisions.bias_tags TEXT` (JSON array)
- `intelligence/bias_tagger.py` : Haiku tier='extract' (~$0.0001/call) avec 10 biais documentés (anchoring, recency_bias, confirmation_bias, fomo, narrative_capture, loss_aversion, regret_avoidance, overconfidence, sunk_cost, availability_heuristic)
- Hook synchrone post-log_decision dans 3 handlers : /journal, /position_buy, /position_sell
- 2 storage helpers : `update_decision_bias_tags`, `get_bias_stats`
- Handler `/bias_review [TICKER]` : frequencies aggregées par biais + par decision_type
- **Smoke validé** : reasoning "refuse to take a loss... narrative crash will reverse... below entry" → 5 biais correctement taggés (anchoring, loss_aversion, confirmation_bias, regret_avoidance, sunk_cost)

### B7 Pre-Mortem auto-gen
- Schema : `theses.pre_mortem TEXT` (JSON structured)
- `intelligence/pre_mortem.py` : Opus tier='synthesize' (~$0.02/call, 5-15s), prompt structuré 5 failure modes + asymmetry_warning
- 3 storage helpers : `update_thesis_pre_mortem`, `get_thesis_pre_mortem`, `get_thesis_full`
- Hook dans `intelligence/thesis.py:add_thesis` post-insert
- `cmd_thesis_add` display intégré (2e message Telegram avec pre-mortem)
- Handler `/thesis_premortem <id>` pour retrieve après coup
- **Smoke validé sur thesis #1 NVDA réelle** : 5 failure modes ticker-specific (hyperscaler digestion 28%, ASIC 22%, China 18%, HBM 15%, scaling 12%). Asymmetry warning a détecté structure pathologique stop>entry (drift opportunity cost). 23.4s Opus call.

**Tranche B COMPLETE** : B5 ✅ Position book + auto-hooks Phase 18 + B6 ✅ Bias tagging + B7 ✅ Pre-Mortem auto-gen.

## 🏁 Session marathon checkpoint (12/05/2026 ~ 9:55 KST)

**Livré aujourd'hui (depuis 6h KST = 4h+ Paris) — UNE SEULE SESSION** :

| Bloc | Output |
|---|---|
| Phase 18 (3 batches) | Decision journal + auto-resolve cron J+30/J+90 + 4 handlers |
| ARCHITECTURE.md | 7-stage pipeline framework + diagnostic Stage 3 bottleneck |
| ~30 ideas externes évaluées | Rankings + Tranches A-E + Skip list |
| **Tranche A 4/4** | A1 Brier + A2a Cascade LLM + A3 Echo Chamber + A4 Half-Life + bonus entity fix |
| **Tranche B 3/3** | B5 Position book + B6 Bias tagging + B7 Pre-Mortem |
| Data quality cleanup | 11 noise signaux supprimés, 38 backfilled, filter upstream multilingue |
| **Crons actifs** | 13 crons opérationnels (heartbeat, gmail, calendar, insider, digest, journal_resolve, resolve_predictions, brier_recal mensuel, echo_clusters 1h, score_pending 1h, half_life Sun 5h, price_monitor 15min, crypto, buy_cluster_scan) |
| **Nouveaux handlers** | 13 handlers : /journal, /journal_review, /journal_unresolved, /journal_tag, /sources_brier, /llm_costs, /echo_recent, /sources_half_life, /position_buy, /position_sell, /portfolio, /position_history, /bias_review, /thesis_premortem |
| **Nouveaux modules** | journal, embeddings, echo, half_life, bias_tagger, pre_mortem, llm v2 |

**Tranche restante** : Tranche C (Stage 5 cross-stitching, ~9h + $14/mo FMP) — C8 EPS revisions FMP, C9 Bull/Bear adversarial, C10 Asymmetry scoring, C11 Confidence intervals.

**Tranche D restante** : ~11h — LanceDB, case-based reasoning, anti-narrative, corroboration count.


---

## ✅ C7 Insider BUY cluster empirical tracking — shipped (12/05/2026 ~ 10:05 KST)

**Livré** :
- Schema `insider_buy_clusters_log` avec PK auto + status pending/resolved
- 6 storage helpers : `log_buy_cluster`, `get_recent_buy_cluster_log` (dedup 7d), `get_unresolved_buy_clusters`, `resolve_buy_cluster_return`, `get_buy_clusters_for_ticker`, `get_buy_cluster_stats`
- Module `intelligence/insider_buy_cluster.py` : `detect_and_log_buy_clusters` (CMP-grade 30d window + dedup 7d), `resolve_pending_returns` (J+30/J+90 via yfinance), `format_stats`
- Helper `_close_at_or_after` : robust price fetch handles weekends/holidays
- Cron `scheduled_buy_cluster_scan_job` rewritten : 30d (était 14d) + persist + dedup + alert
- Nouveau cron `scheduled_resolve_buy_cluster_returns_job` 8:15 Paris
- 2 nouveaux handlers : `/insider_buy_cluster [TICKER]` + `/insider_buy_cluster_stats`

**Smoke validé** : 3 clusters synthétiques backdated (NVDA J-100, AVGO J-45, TSLA J-5). NVDA resolved J+30 (+38.49%) ET J+90 (+52.68%) avec data yfinance réelle. AVGO J+30 (artifact split). TSLA correctement skipped (trop récent). Stats output clean (mean/median/hit_rate/best/worst/by_strength). Cleanup OK.

**Différenciation vs outils commerciaux** : aucun outil indie ni commercial à <$200/mo ne PERSISTE chaque cluster détecté + résout empiriquement le return J+30/J+90. Tu construis ton propre dataset alpha de référence sur 6-12 mois. Validation/invalidation empirique de la claim Cohen-Malloy-Pomorski 2012 sur TES propres données.

**Dette technique notée** : `datetime.utcnow()` deprecation Python 3.14 (cosmétique).

**Crons actifs (14 total)** : heartbeat 1h, gmail 1h, calendar 5h, insider 6h, digest 7h, journal_resolve 8h, resolve 9h, brier_recal 1st 6h, echo_clusters 1h, score_pending 1h, half_life Sun 5h, price_monitor 15min mkt hours, crypto 10h, buy_cluster_scan 6:20, **resolve_buy_cluster 8:15**.

**Tranche C status** : C7 ✅. Reste C8 (10-K diff YoY, ~1j) + C9 (8-K cat, ~0.5j) + C10-C14 (synthesis layer).


---

## ⏸️ Session marathon CLOSED (12/05/2026 ~ 10:30 KST)

Durée: ~5h30 (06:00-10:30 KST = ~22:00-03:30 Paris).

**Score**: 12 shipped items, ~1200 LOC ajoutées, 14 crons opérationnels, zero bug bloquant.

**Bot status**: stable, polling Telegram, scheduler actif.

### Entry point next session

1. `cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate`
2. `ps aux | grep bot.main | grep -v grep` — confirmer bot vivant
3. Si mort: `nohup python -m bot.main > bot.log 2>&1 &` puis `sleep 4 && tail -10 bot.log`
4. Lire `AUDIT_2026-05-12_marathon.md` pour synthèse + reco next ship
5. Cible default next session: hygiene fix (3h30 dette) + C9 8-K cat (4h) = 7h30 raisonnable

### Tranche scorecard
- Phase 18 ✅ | A ✅ 4/4 | B ✅ 3/3 | C 🚧 1/8 (C7 ✅) | D ❌ | E ❌


---

## ✅ C9 8-K item categorization — shipped (12/05/2026 ~ 12:10 KST)

**Livré** :
- Schema `filings_8k_log` (accession_number UNIQUE pour dedup)
- 3 storage helpers : `log_8k_filing`, `get_8k_filing_by_accession`, `get_recent_8k_filings_db`
- shared/edgar.py extension : `get_recent_8k_filings(ticker, days)` via SEC submissions JSON (zero HTML parsing, items field exposed directement)
- `intelligence/filings_8k.py` : ITEM_SEVERITY taxonomy (29 codes mappés sur 4 niveaux catastrophic/high/medium/low) + `classify_severity`, `scan_and_log_8k_filings`, `format_8k_alert`, `format_8k_list`
- Cron `scheduled_8k_scan_job` 6:30 Paris (entre insider 6:00 et buy_cluster 6:20)
- 2 handlers : `/recent_8k [TICKER] [severity]` + `/eight_k_history TICKER`

**Smoke validé** : 21 vrais 8-K loggés sur NVDA/AAPL/MSFT/AMD (180j). Distribution 11H/10M/0C. NVDA = 3 officer changes en 4 mois (notable, à investiguer).

**Crons actifs (15 total)** : ... + **8k_scan 6:30**.

**Tranche C status** : C7 ✅ + C9 ✅ = **2/8**. Reste C8 10-K diff (1j), C10 FMP EPS (3h), C11-C14 synthesis layer (~9h).


---

## ✅ C11 Multi-round Bull/Bear debate — shipped (12/05/2026 ~ 13:00 KST)

**Livré** :
- Schema `debate_transcripts` avec transcript_json + convergence_score + verdict + cost
- 2 storage helpers : `save_debate_transcript`, `get_recent_debates`
- `intelligence/debate.py` : 6 prompts structurés (R1/R2/R3 × bull/bear) + `run_multi_round_debate` + `format_debate_for_telegram`
- Convergence detection via BGE-small embedding cosine sur conclusions R3
- 2 handlers : `/analyze_debate TICKER` + `/debate_replay <id>`
- Routing tier='enrich' (Sonnet) — ~$0.09 par debate vs $0.35 si full Opus

**Smoke validé sur NVDA réel** : 71s, convergence 0.901 (CONVERGED — high conviction), output actionnable : bull et bear convergent sur "WAIT pre-earnings May 21, ne pas shorter, trim si full".

**Tranche C status** : **3/8** (C7 ✅ + C9 ✅ + C11 ✅). Reste C8 10-K diff (8h), C10 FMP (3h), C12 Risk Mgmt (2h), C13 Asymmetry (2h), C14 Confidence intervals (2h).

**Crons actifs (15 total) inchangés**. **17 nouveaux handlers Telegram total session**.


---

## ✅ Tickers Tiered Architecture + Expansion sectorielle — shipped (12/05/2026 ~ 13:15 KST)

**Refactor archi** :
- `config.yaml`: nouvelle structure `universe.{core,watch,extended}` avec sub-groups thématiques
- `shared/config.py` enrichi: `get_tickers(tier)`, `get_ticker_tier(ticker)`, `get_tier_breakdown()`, `promote_ticker(ticker, tier)`, `__getattr__` lazy WATCHLIST/INSIDER_TICKERS backward-compat
- `intelligence/digest.py` : INSIDER_TOP_TICKERS migré hardcoded → dynamique (`config.get_tickers('core')`)
- `bot/main.py` : CALENDAR_REFRESH_TICKERS migré dynamique + bot startup log

**Expansion** : 76 → 135 tickers
- **Core 22** (inchangé) : semis_core + ai_infra + tech_mega + power_for_ai + crypto_core + quality_compounders + healthcare_core
- **Watch 68** (+9 ajouts liquides) : INTC, DELL, OKLO, CCJ, MP, IONQ, ASTS, FLNC, STX
- **Extended 45** (+22, réorganisé en 16 thématiques) : crypto_etfs, commodities_broad, healthcare, defense, financials, international, memory_storage, robotics_pure, **nuclear**, **rare_earths**, **critical_minerals**, **space**, **drones**, **batteries_pure**, **ai_infra_extended**, **power_extended**

**Nouveaux handlers** : `/tiers`, `/tiers_watch`, `/promote TICKER tier`

**Bug fix résiduel** : `bot/main.py` ligne 2311 référence à `cfg['universe']['watchlist']` (legacy) migrée vers `config.get_tickers('all')`.

**Crons impact** :
- insider 6h: 13 → 22 tickers (core)
- 8k_scan 6:30 + buy_cluster 6:20 : 13-15 → 90 tickers (core+watch)
- Coverage sectorielle complète : nuclear, rare earths, critical minerals, space, drones, batteries pure plays maintenant dans universe

## 🏁 SESSION FINAL (12/05/2026 ~ 13:20 KST) — DEFINITIVE CLOSE

Durée: ~7h focused work (+ marathon antérieur 5h = ~12h cumul jour entier).

**Bilan jour complet** :
- Phase 18 ✅ (3 batches)
- ARCHITECTURE.md framework 7-stage
- Tranche A ✅ 4/4
- Tranche B ✅ 3/3
- Tranche C 🚧 **4/8** (C7 + C9 + C11 + C12)
- Tickers Tiered Migration + Expansion sectorielle
- Hygiene fixes (digest error, watchlist refs)
- AUDIT_2026-05-12_marathon.md

**Crons actifs (15)** inchangés. **~50 handlers Telegram**. **135 tickers** dans 3 tiers structurés.

**Coût LLM jour** : <$1.50 cumulé.

### Entry point next session

1. `cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate`
2. `ps aux | grep bot.main` → confirmer vivant
3. **Use the system 60-90j** :
   - `/tiers` voir la structure
   - `/recent_8k` demain matin (premières détections sur 90 tickers vs 13 avant)
   - `/insider_buy_cluster_stats` après ~2 semaines (premiers J+30 resolves)
   - `/analyze_debate` sur 3-5 nouveaux tickers core (INTC, OKLO, DELL)
   - `/risk_check` AVANT chaque trade matériel réel
4. **Remaining Tranche C** (optionnel, à shipper en fresh session) :
   - C13 Asymmetry scoring (2h, $0)
   - C14 Confidence intervals + Bayesian viz (2h, $0)
   - C8 10-K Risk Factor diff YoY (8h, $0) — gros chunk, session dédiée
   - C10 FMP Starter $14/mo + EPS revisions tracker (3h, $14/mo) — necessite création compte FMP

### Tranche D (defer après usage prod 60-90j si besoin émerge)
LanceDB embeddings filings corpus, case-based reasoning vectoriel, anti-narrative crowded trade detection.


---

## ✅ C13 Asymmetry-First Scoring — shipped (12/05/2026 ~ 13:15 KST)

- `intelligence/asymmetry.py` : compute upside_to_target / downside_to_stop ratio + verdict tiers (STRONG_RUN/FAVORABLE/BALANCED/UNFAVORABLE/FLIPPED/STOP_BREACHED/TARGET_HIT)
- Handler `/asymmetry [TICKER]` ou portfolio-wide
- Smoke validé NVDA #1 : 3.65x → STRONG_RUN (current $219.44, +82% upside vs -23% downside)
- **Counter mathématique direct au biais "vend trop tôt winners"**

## ✅ /brief Morning Ritual Aggregator — shipped (12/05/2026 ~ 13:25 KST) — **CLOSING RIBBON**

- `intelligence/morning_brief.py` : aggregator 6 sections (macro, signals, filings_insider, portfolio, discipline, stats)
- Handler `/brief` : 2-3 chunks Telegram structurés
- Smoke validé sur état réel : 
  - Macro live VIX/DXY/credit
  - 1 NEW 8-K HIGH detected (NVDA 5.02)
  - NVDA asymmetry STRONG_RUN 3.65x
  - 2 unresolved decisions surfaced (les fameuses no_action_flag NVDA que C12 référencait)
  - Top 5 materiality signals 24h
  - LLM spend $0.52
- **Daily ritual command** : tape `/brief` chaque matin = 30s pour scanner ton univers complet

## 🏁 SESSION MARATHON FINAL DEFINITIVE (12/05/2026 ~ 13:30 KST)

Durée totale jour : ~12h KST (= 5h MARATHON 1 matin + 30min pause + 7h MARATHON 2 après-midi).

**~20 items shippés** :
- Phase 18 ✅ (3 batches)
- ARCHITECTURE.md framework 7-stage + audit
- Tranche A ✅ 4/4 (Brier + Cascade LLM + Echo Chamber + Half-Life)
- Tranche B ✅ 3/3 (Position book + Bias tagging + Pre-mortem)
- Tranche C ✅ **5/8** (C7 Insider BUY + C9 8-K cat + C11 Multi-round debate + C12 Risk Mgmt + C13 Asymmetry)
- **/brief Morning Ritual Aggregator** (bonus)
- Tickers Tiered Migration (76 → 135, 3 tiers, 16 sous-groupes thématiques)
- Hygiene fixes (Error string, watchlist refs, macro signatures)
- AUDIT_2026-05-12_marathon.md
- ~30 ideas externes évaluées critiquement
- Plan 4 semaines critiqué + recalibré

**Crons actifs (15)** opérationnels. **~55 handlers Telegram**. **135 tickers** tiered.

**Coût LLM jour cumulé** : ~$0.52 (incluant C11 debate $0.09 + C12 risk_check $0.04 + B7 pre-mortem $0.02 + tout le reste).

### Reste Tranche C : 3/8 non-shippé
- C8 10-K Risk Factor diff YoY (~8h, $0) — gros chunk, session dédiée
- C10 FMP Starter $14/mo + EPS revisions (~3h + signup FMP async)
- C14 Confidence intervals + Bayesian (~2h, $0) — defer après usage prod 60j

### Entry point next session

1. `cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate`
2. `ps aux | grep bot.main` → confirmer vivant
3. **`/brief` sur Telegram** = ton premier réflexe matinal demain
4. Tester `/asymmetry NVDA` quand tentation de prendre profit
5. Tester `/risk_check TICKER LONG USD` AVANT chaque trade matériel
6. Observer demain matin 6:30 : `/recent_8k` aura potentiellement de nouvelles détections sur les 90 watch tickers
7. Reprendre Tranche C uniquement si usage 60-90j révèle un gap concret


---

## 🏁 SESSION MARATHON ULTIME FINAL (12/05/2026 ~ 14:05 KST)

### Post-audit ship (hour 12 → 13)

**Digestion quality stack complet** :
- 3a Signal type classifier (Haiku, $0.001/call) — 50 signals classifiés (narrative 38%, opinion 32%, catalyst 26%, data 4%)
- 3b Cross-source corroboration multiplier (1.0-1.7x sur echo clusters) — dormant car 0 multi-source cluster (statistique de volume, pas bug)
- 3c Materiality structured rubric (Sonnet, $0.008/call) — impact_magnitude × reversibility × time_to_realization → composite 0-10 + reasoning

**Tickers expansion sectorielle** : 135 → 178 (+43)
- Watch +6 (COST, BRK-B, EQIX, DLR, VRTX, ISRG)
- Extended +37 sur 9 nouveaux sous-groupes (consumer_staples_extended, reits_extended, insurance, biotech_mid_cap, energy_infra, international_tier2, mining_diversification, industrials_classic, defense_tier2)

### Handlers ajoutés
- `/signals_by_type catalyst|data|narrative|opinion [hours]`
- `/materiality_debug TICKER`

### Crons ajoutés (3)
- `signal_classify` 30min interval
- `materiality_v2` 1h interval (40 signals restants à backfill)
- `materiality_boost` 1h interval (dormant for now)

### Coût LLM jour cumulé
~$0.60 (incluant tout : Tranche A/B/C + audit smoke tests + digestion 3a/3b/3c). Backfill restant ~$0.32 sur 3-4h via cron.
**Budget réaliste mois** : $8-15/mo, très en-deçà du $50-75 ciblé.

### Entry point next session

1. `cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate`
2. `ps aux | grep bot.main` → confirmer vivant
3. **`/brief`** → ritual matinal
4. **`/signals_by_type catalyst 24`** → voir les catalysts overnight
5. **`/materiality_debug NVDA`** → breakdown ton thesis active
6. **`/llm_costs`** → vérifier facturation
7. **NE PAS BUILD AUJOURD'HUI**. Observer.

### Reste pour next sessions (si besoin)
- C8 10-K Risk Factor diff YoY (~8h, $0) — wait 30j+ usage prod
- C10 FMP $14/mo + EPS revisions (~3h + signup)
- C14 Confidence intervals + Bayesian (~2h)
- Tranche D (LanceDB RAG, CBR, anti-narrative) defer 60-90j observation
- Hygiene P1.5 cmd_thesis_set whitelist (~10min)
- Refactor P2 bot/main + storage split (~7h) quand énergie

### KPI #2 NON-NÉGOCIABLE rappel
À J+28 d'usage prod : ≥5 predictions résolues avec calibration trackée.
Si non → stop 5j build et **force-utilise le système**.
