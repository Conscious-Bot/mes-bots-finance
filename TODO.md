# 📋 TODO — Bot Finance Personnel

Status legend :
- ✅ DONE
- 🟡 IN PROGRESS
- ⬜ TODO

---

## PHASE 1 — SUBSTRAT (semaines 1-2)
*Objectif : le bot vit, répond /ping, scheduler tourne, DB en place.*

### Code & Setup
- ✅ Projet créé, venv activé (Python 3.14.4)
- ✅ requirements.txt + 6 deps installées
- ✅ Structure dossiers complète
- ✅ config.yaml + .env.example
- ✅ scripts/init_db.py — 15 tables SQLite + bot_state.json
- ✅ shared/storage.py — accessors DB
- ✅ shared/config.py — loading .env + yaml
- ✅ shared/llm.py — wrapper Claude (Haiku/Sonnet/Opus routing)
- ✅ shared/notify.py — Telegram text/image/file
- ✅ shared/prompts.py — 6 prompts spécialisés
- ✅ risk/sizing.py — Quarter Kelly UNE formule (tests passés)
- ✅ risk/risk_engine.py — validation pré-output
- ✅ bot/main.py — entrypoint async + scheduler + /ping
- 🟡 .env rempli avec vraies clés (Anthropic + Telegram en cours)
- ✅ Lancer python -m bot.main et tester /ping

### Opérationnel
- ✅ crons/daily_backup.sh — backup quotidien data/
- ✅ crons/uptime_monitor.sh — heartbeat check toutes les 5min
- ⬜ Crontab installé sur ta machine
- ✅ PROCEDURE_QUOTIDIENNE.md — routine matinale 10min
- ✅ PROCEDURE_URGENCE.md — scénarios crash/drawdown/bug
- ✅ KPI_DASHBOARD.md — métriques quotidiennes/hebdo/mensuelles
- ⬜ Backup nommé avant chaque patch significatif

### Préparation user (en parallèle)
- ⬜ Watchlist définitive : 10-30 tickers max
- ⬜ Topics prioritaires précisés
- ⬜ Style d'invest explicité : horizon, conviction min, position max %
- ⬜ Métriques fondamentales prioritaires pour scoring
- ✅ Sources favorites (9 subscribed) de départ : 5-10 newsletters, 20-50 comptes X, 5-10 canaux TG
- ⬜ Réflexion lucide sur les 3 plus grosses erreurs des 12 derniers mois

---

## PHASE 2 — DISCIPLINE BEHAVIORAL (semaines 3-4)
*Objectif : digest matinal + thesis tracker + credibility actifs.*

### Setup OAuth
- ⬜ Compte Google Cloud + projet "mes-bots-finance"
- ⬜ Gmail API activée
- ⬜ OAuth credentials.json téléchargé
- ✅ Label "Newsletters" + filtres actifs "Newsletters" + filtres de redirection automatique

### Code
- ✅ data_sources/gmail_.py (Chunk 1 done) — fetch newsletters
- 🟡 intelligence/digest.py (code done, smoke blocked on API key) — compression cross-source, scoring 0-10
- ⬜ **Mots-clés bullish/bearish pré-scoring dans digest.py (économie tokens)**
- ✅ intelligence/thesis.py (Chunk 2 done + validated end-to-end) — complet (/thesis add, list, review, revisit mensuel)
- ⬜ intelligence/credibility.py — score par source via feedback ET outcomes
- ⬜ intelligence/probabilistic.py — helpers outputs probabilistes
- ⬜ intelligence/shadow_decisions.py — variantes parallèles dès le départ
- ⬜ intelligence/learning.py v1 — PredictionLedger
- ⬜ crons/resolve_predictions.sh
- ⬜ Handler /feedback 👍/👎

### Critère de fin Phase 2
- ⬜ Digest matinal reçu 5 jours d'affilée
- ⬜ Au moins 3 thèses loggées
- ⬜ Au moins 10 signaux scorés en DB

---

## PHASE 3 — CERVEAU MACRO (semaines 5-6)
*Objectif : régime macro + calendrier événements + timing.*

### Setup
- ⬜ Compte FRED → API key
- ⬜ Compte FMP Starter (~14€/mois) → API key
- ⬜ OpenBB installé et configuré

### Code
- ⬜ data_sources/markets.py — wrapper OpenBB unifié
- ⬜ data_sources/fred_macro.py — appels FRED directs
- ⬜ markets/regime.py — classification 4 régimes
- ⬜ intelligence/liquidity.py — interprétation Claude
- ⬜ intelligence/calendar_.py v1 — FOMC + CPI + NFP + earnings + OPEX
- ⬜ **Catalyst Detection enrichi : insider clusters, FDA approvals, ETF flows, lockup expirations, token unlocks, analyst upgrade clusters dans calendar_.py**
- ⬜ scripts/seed_calendar_2026.py
- ⬜ crons/update_macro.sh
- ⬜ Handler /macro et /upcoming
- ⬜ **Handler /why — "Why is market moving?" (régime + signaux 24h + événements imminents)**
- ⬜ Alertes événements T-2h scheduled

### Critère de fin Phase 3
- ⬜ /macro renvoie régime + 3 drivers + 1 risque
- ⬜ /why fonctionne et explique un mouvement actuel
- ⬜ Snapshot régime quotidien en DB
- ⬜ Alertes T-2h reçues avant FOMC/CPI

---

## PHASE 4 — PROFONDEUR ANALYTIQUE (semaines 7-9)
*Objectif : analyse multi-dimensionnelle sur demande, pattern matching.*

### Code
- ⬜ data_sources/earnings_transcripts.py
- ⬜ **data_sources/sec_edgar.py — Form 4 insider tracking (gratuit, alpha small/mid caps)**
- ⬜ intelligence/earnings_nlp.py — analyse ton, comparaison Q-by-Q
- ⬜ markets/fundamentals.py — scores structurés via OpenBB→FMP
- ⬜ **Principe "évolution > valeur absolue" dans fundamentals.py (scoring trajectoires sur 4-8 trimestres glissants)**
- ⬜ markets/technicals.py — EMA 20/50/200, RSI, MACD, niveaux
- ⬜ **TA-Lib comme dépendance pour technicals.py (battle-tested vs implémenter à la main)**
- ⬜ intelligence/analyze.py — orchestrateur /analyze TICKER
- ⬜ **Score multi-dimensionnel par ticker (7 sous-scores : Quality / Growth / Profitability / Valuation / Risk / Momentum / MacroAlignment) dans analyze.py**
- ⬜ intelligence/calendar_.py v2 — impact historique pré-calculé
- ⬜ intelligence/patterns.py v1 — analogues historiques
- ⬜ **Smart watchlist enrichie : scores dynamiques quotidiens par ticker (momentum, sentiment, RS vs SPY, days_to_earnings, narrative_strength)**
- ⬜ Tests unitaires sizing anti-cascade
- ⬜ Handler /analyze TICKER, /similar TICKER YEAR, /watchlist enrichie

### Critère de fin Phase 4
- ⬜ /analyze NVDA produit 800-1200 mots multi-dimensionnel avec 7 sous-scores
- ⬜ /similar retourne 3-5 analogues historiques avec outcomes
- ⬜ /watchlist affiche scores dynamiques utiles
- ⬜ Insider Form 4 alerts fonctionnent

---

## PHASE 5 — SOPHISTICATION (semaines 10-12)
*Objectif : système complet, 9 idées + 6 boucles apprentissage actives.*

### Setup
- ⬜ TwitterAPI.io ou Apify account (~5-15€/mois)
- ⬜ Compte X dédié pour listes curées
- ⬜ Telethon : Application API hash via my.telegram.org
- ⬜ Curer 4-5 listes X par topic
- ⬜ Curer 5-10 canaux Telegram publics

### Code
- ⬜ data_sources/prediction_markets.py — Polymarket + Kalshi
- ⬜ intelligence/prediction_markets_layer.py — calibration
- ⬜ intelligence/narratives.py — 12 narratifs trackés, dynamique 30/90/180j
- ⬜ intelligence/contradiction.py — cross-source contradictions
- ⬜ data_sources/x_.py — X via TwitterAPI.io
- ⬜ data_sources/telegram_channels.py — Telethon canaux
- ⬜ intelligence/debate.py — bull / bear / synthesizer
- ⬜ markets/screener.py — asymmetric opportunity hebdo
- ⬜ **PyPortfolioOpt pour correlation matrix + VaR + Sharpe sur historique thèses**
- ⬜ **Variance empirique 30j dans sizing.py (intuition GARCH sans formalisme)**
- ⬜ intelligence/learning.py v2 :
  - PatternMiner — extraction patterns récurrents
  - BiasDetector — rapport mensuel biais perso
  - RetrievalEngine — embeddings via sqlite-vec
  - **CalibrationEngine — Bayesian update explicite des distributions**
- ⬜ **Sharpe + Max Drawdown du bot lui-même tracké dans KPI dashboard**

### Critère de fin Phase 5
- ⬜ 9 idées + 6 boucles actives
- ⬜ ~100+ predictions évaluées
- ⬜ Pattern library démarrée (5+ patterns)
- ⬜ Premier rapport mensuel de biais reçu
- ⬜ Sharpe du bot mesurable

---

## PHASE 6 — MATURATION & BASCULE (semaine 13+)

- ⬜ Usage quotidien 3-6 mois
- ⬜ PLAN_BASCULE_PAPER_REAL.md — critères GO/NO-GO
- ⬜ Auto-évaluation : CLV positif sur thèses ?
- ⬜ Décision : bascule décisionnel engageant ou consultatif
- ⬜ **Correlation Shift Detector (après 6+ mois de data accumulée)**
- ⬜ **Conditional probability par régime (P(thèse réussit | VIX > 25) etc.)**
- ⬜ **Monte Carlo sur historique thèses (50+ résolues requis)**
- ⬜ **Piotroski / Altman Z / Beneish M scores en complément du score multi-dim (optionnel)**

---

## OPS & DÉPLOIEMENT

### Local → VPS
- ⬜ Bot en local pendant 2 premières semaines
- ⬜ VPS Hetzner CX11 (5€/mois) commandé
- ⬜ Setup Python + venv sur VPS
- ⬜ Migration crons sur VPS
- ⬜ Process management (nohup ou systemd)
- ⬜ Bot accessible sans Mac allumé

### Documentation
- ⬜ README.md à jour à chaque phase
- ⬜ ARCHITECTURE.md — décisions stratégiques
- ⬜ BOT.md — vue d'ensemble pour reprise après pause

### Discipline
- ⬜ Backup nommé avant CHAQUE patch significatif
- ⬜ Routine matinale quotidienne (10min)
- ⬜ Audit empirique trimestriel des filtres

---

## 🛑 LES 5 INVARIANTS ARCHITECTURAUX (à ne JAMAIS violer)

1. Risk engine valide TOUT output
2. Sizing = une formule, un cap (PAS de cascade multiplicateurs)
3. Pas de hardcoded fallback silencieux
4. Shadow decisions actives dès Phase 2
5. Backup avant chaque patch significatif

---

## 🎯 LE EDGE QU'ON CIBLE

On NE court PAS après :
- ❌ Information edge (alternative data — inaccessible solo)
- ❌ Order flow / GEX / dark pools (Bloomberg-grade)
- ❌ Multi-asset coverage (forex/commodities)
- ❌ ML predictions / RandomForest / ARIMA / GARCH formel
- ❌ Sentiment Reddit/Twitter (ratio bruit/signal terrible)

On maximise :
- ✅ Analytical edge — LLMs lisent 50 sources/h
- ✅ Behavioral edge — thesis tracker + anti-FOMO + sizing systématique
- ✅ Time horizon edge — pondération selon horizon
- ✅ Niche depth — AI/semis/macro IA ultra-profondeur
- ✅ Cross-domain synthesis — relier ce que les pros siloés ratent

---

## 🔑 PRINCIPES CLÉS POUR LE SCORING (issus des dernières recherches)

1. **Évolution > valeur absolue** : direction des marges/FCF/ROIC compte plus que niveau
2. **Multi-dimensionnel transparent** : 7 sous-scores explicables, pas 1 score boîte noire
3. **Mots-clés pré-filtre** : regex bullish/bearish AVANT LLM (économie tokens)
4. **Insider Form 4 clusters** : 3+ insiders qui achètent en 30j = signal historique fort
5. **Probabiliste, pas binaire** : "70% bullish 6m, conviction 4/5" jamais "Buy"
6. **CLV mesuré sur thèses** : étais-tu en avance sur le repricing du marché ?
7. **Bayesian update** : chaque outcome résolu affine les distributions futures

---

## ⏱️ TIMELINE GLOBALE
Sem 1-2   : SUBSTRAT (Phase 1)           ← ICI
Sem 3-4   : DISCIPLINE BEHAVIORAL (P2)
Sem 5-6   : CERVEAU MACRO (P3)
Sem 7-9   : PROFONDEUR ANALYTIQUE (P4)
Sem 10-12 : SOPHISTICATION (P5)
Sem 13+   : MATURATION (P6)


---

## 🏗 Tranches actives (refresh 2026-05-12 post-ideas-eval)

Cf `ARCHITECTURE.md` pour le référentiel 7-stages + ranking critique des ~30 ideas externes.

**Goulot actuel = Stage 3 (entonnoir de qualité).** Ordre = ROI compound. Total Tranches A+B+C ≈ 25h dev + $14/mo FMP + $25-40/mo LLM cascade = **~$50-55/mo total** sous budget.

### Tranche A — Stage 3 musclage (must come first, ~9h)

#### [ ] A1. Brier Score calibration + boucle credibility (~1h) — Stage 3
- À chaque résolution prédiction (cron resolve 9h), calculer `brier_score = (probability_predicted - outcome_actual)^2`
- Cron mensuel : recalculer `sources.credibility = 1 - mean(brier over N>=10 resolved preds for that source)`
- Add column `predictions.brier_score` (computed at resolve time)
- Add column `conviction_history.source_credibility_at_persist`
- Expose `/sources_brier` handler

#### [ ] A2. Cascade LLM routing Haiku/Sonnet/Opus + prefix caching (~3h) — Stage 3 transverse
**Levier stratégique #1** : sans ça, Tranches B-D explosent le budget
- Créer `shared/llm.py` avec routing par `tier` param : `extract` → Haiku 4.5, `enrich` → Sonnet 4.6, `synthesize` → Opus 4.7
- Migrer : extraction signals + classification regime + dedup → Haiku
- `materiality` + `why_matters` → Sonnet
- `/analyze` deep + digest final + adversarial → Opus
- System prompts restructurés : invariants (regime, credibility state, watchlist) en HEAD pour prefix cache 5min Anthropic
- Logger token usage + cost par tier dans table `llm_calls` pour audit

#### [ ] A3. Echo Chamber Resolution / cross-source semantic dedup (~3h) — Stage 3
- Tous les signaux ingérés via Gmail dans 24h embeddés (BGE-large local ou OpenAI text-embedding-3-small @ $0.02/M)
- Cosine sim > 0.85 sur claims principaux → fingerprint commun
- Nouvelle column `signals.echo_cluster_id`
- 5 sources qui citent même Stratechery article = 1 signal corroboré +5 conviction, pas 5 signaux indépendants
- Affecte `materiality_score` : boost si corroboration indépendante, pénalité si echo

#### [ ] A4. Information Half-Life par source (~2h) — Stage 3
- Pour chaque signal résolu, mesurer délai entre `signal_ts` et `peak_move_ts` (premier move >threshold sur primary_ticker)
- Aggregate `sources.half_life_days` = median par source
- Newsletter mainstream (BBG/FT) : attendu ~0-1j
- Specialized substack : 5-15j
- `/digest` flagge signaux avec urgence dépréciée (half-life passée → no-action recommandé)

### Tranche B — Stage 6 approfondissement (~7h)

#### [ ] B5. Position book + auto-hooks Phase 18 (~3h) — Stage 6
- Table `positions(id, ticker, qty, avg_entry, opened_at, closed_at, current_qty, realized_pnl)`
- Handlers `/position_buy <TICKER> <qty> <price>` et `/position_sell <TICKER> <qty> <price>`
- Auto-injection : `log_decision` automatique avec decision_type=entry/scale_in/partial_exit/full_exit
- Handler `/portfolio` : positions actives + concentration sectorielle + cash residuel
- Use case clef : alerte "tu es overweight AI (45%) alors que materiality flashe rouge"

#### [ ] B6. Bias tagging extension Phase 18 (~2h) — Stage 6
- Add column `decisions.bias_tags` (JSON list : anchoring, recency, confirmation, fomo, narrative_capture)
- Au moment du `/journal`, LLM Tier 1 (Haiku) auto-tagge biais potentiels depuis reasoning + position context
- Aggregation mensuelle dans `/journal_review` : "tu as confirmation bias sur NVDA — 78% signals positifs vs 52% baseline"
- Absorbe partiellement Phase 14 (decision attribution graph)

#### [ ] B7. Pre-Mortem auto-gen (~2h) — Stage 5+6
**Levier stratégique #2** : seule feature forçant exit discipline pre-commit
- Hook sur thesis insertion déclenche 1 call Opus
- Prompt : "5 raisons les plus probables pour lesquelles cette thesis échoue à 12 mois, avec P estimée et signaux à monitorer"
- Output structuré stocké dans `theses.pre_mortem`
- Affichage forcé dans `/thesis_show` — impossible d'ouvrir thesis sans avoir vu pre-mortem

### Tranche C — Stage 5 cross-stitching + first paid data (~9h + $14/mo)

#### [ ] C8. FMP Starter $14/mo + EPS revisions tracker (~3h) — Stage 2+3
- Subscribe FMP Starter ($14/mo)
- Module `shared/fmp.py` : `get_eps_revisions(ticker)`, `get_analyst_estimates(ticker)`
- Cron quotidien : pull revisions pour watchlist 76 tickers, store deltas
- `signals` enrichis avec EPS revision flag si delta >5% sur 30j
- Alpha académiquement validé (Bartov-Bernard, Womack)

#### [ ] C9. Bull/Bear adversarial pass sur /analyze + /digest (~2h) — Stage 5
- Après synthesis Tier 3 (Opus), 1 call Tier 3 supplémentaire en mode adversarial
- System prompt : "trouve 3 plus gros trous, identifie biais cognitifs probables, propose thesis contraire la mieux argumentée"
- Output mergé en section "Devil's advocate" à la fin de `/analyze`
- Coût marginal : 2× tokens Tier 3, uniquement sur thesis critiques (filtrées par cascade routing pour autres)

#### [ ] C10. Asymmetry-First Scoring (~2h) — Stage 5+6
- Score `/analyze` enrichi avec `asymmetry_ratio = (upside × P_up) / (downside × P_down)` avec tail cutoffs
- Convexity > Expected Value
- Counter direct biais vend-trop-tôt : système dit numériquement "tu sous-pondères l'asymétrie 5x-up / 1x-down @ P=20% vs 2x-up / 1x-down @ P=55%"

#### [ ] C11. Confidence intervals + Bayesian update viz (~2h) — Stage 5+6
- Tous claims LLM outputés en `(claim, P_true, reasoning_for_P, what_would_change_my_mind)`
- Calibration check mensuel : sur 100 claims @ P=0.7, ~70 doivent s'avérer vrais
- Bayesian update visualisé : signal arrive → prior P → likelihood ratio → posterior
- Stocké dans `predictions` table pour calibration loop

### Tranche D — Stage 4 enrichissement (~11h, post A-C done)

#### [ ] D12. LanceDB + embeddings tous signaux historiques (~4h) — Stage 3+4
- Setup LanceDB local
- Embed tous `signals` historiques + thesis + decisions + outcomes
- Schema vectoriel : `(signal_id, embedding, regime_at_t, credibility_at_t, outcome)`
- Foundation pour case-based reasoning + crowded trade detection

#### [ ] D13. Case-based reasoning intégré /analyze (~2h) — Stage 5
- Nouveau setup → retrieve top 10 plus similaires (cosine + filtres regime)
- Output : "setups comme celui-ci en late-cycle credit-tight : hit rate 58%, median return +12%, max DD -18%"
- Base rate empirique perso (impossible chez Bloomberg)

#### [ ] D14. Anti-Narrative / crowded-trade detection (~3h) — Stage 4 = Phase 19 reformulée
- Embedding tous signaux sur fenêtre rolling 14j
- Détecter quand >60% du corpus partage une narrative dominante (clustering)
- Search counter-narrative la mieux argumentée dans sources non-mainstream
- Output `/narrative_saturation` : "AI bubble narrative crowded 78% this week, counter best argued by X"
- Counter direct biais crypto-tops

#### [ ] D15. Temporal divergence + cross-source corroboration count (~2h) — Stage 4
- Column `signals.corroboration_count`
- Module weekly aggregation : cette semaine vs trailing 4w divergence
- Materiality score boosted si corroboration ↑ AND divergence ↑

### Tranche E — Defer 3-6 mois (conditionnel à A-D done)

- Polygon Options $29/mo (gamma exposure, sweeps)
- PIT bitemporal discipline (pré-requisite backtest)
- Insider Replication virtual portfolio (post B5)
- Persona Ensemble étendue 5 (reste à 2)
- Reflexivity Detector
- Structured logging + Prometheus + Grafana
- Phase 20 Regime Transition Detector

### Skip définitif

| Idée | Raison |
|---|---|
| Causal DAG Pearl | Trop ambitieux solo |
| Paralinguistic earnings audio | Alpha marginal, compute lourd |
| Pydantic+mypy strict everywhere | Polish premature |
| Postgres/DuckDB migration | SQLite tient |
| Ortex, WhaleWisdom | Free tier suffit |
| Property-based testing exhaustif | Sélectif if besoin |

---

## 📋 Tâches résiduelles hors tranches (data quality + bugs latents)

- [ ] Insider snapshot `total_buys_m`/`total_sells_m` persist (net_m correct mais bruts à 0)
- [ ] Return_pct format standardization (decimal vs percent partout)
- [ ] Upstream fix `get_or_create_source()` strip Gmail +labels (cause doublons)
- [ ] Watchlist expansion data-driven (après `/orphan_tickers` 3-5j)

### Phases tierces pré-existantes (mapping)
- Phase 12.2 Supplier confirmation — defer post tranches A-C
- Phase 13 Earnings transcripts NLP — defer (alpha lourd vs simple FMP transcripts)
- Phase 14 Decision attribution graph — partiellement absorbé par B6 + B5


---

## 🔬 Data quality bugs identifiés (12/05/2026, post-A3)

#### [ ] Don't persist `summary='Error:...'` on LLM failure (~20min) — Stage 2
Lieu : pipeline qui appelle LLM pour générer signals.summary (à localiser via grep).
Fix : si LLM call échoue, leave `summary=NULL` au lieu de persister "Error: <type>". Permet retry au prochain cron.

#### [ ] Entity extraction silent fail (~45min) — Stage 2 — **HIGH ROI**
Diagnostic A3 : 93% des signaux (54/58 avant cleanup) ont `entities IS NULL/[]`. Bloque /orphan_tickers, materiality ticker-based, echo cluster ticker corroboration.
À investiguer : où est wired l'entity extraction ? Pourquoi silent fail ? Re-run sur signals historiques.

#### [ ] LLM-based noise classifier post-ingestion (~30min) — Stage 3
Utiliser le summary LLM lui-même (post-ingestion) pour flagger signaux noise type "Email de bienvenue", "Newsletter éducative", "Tutorial post". Layer 2 au-dessus du filter title-based gmail_.py.


---

## ✅ Tranche B complétée (12/05/2026)

B5 Position book ✅ | B6 Bias tagging ✅ | B7 Pre-Mortem auto-gen ✅

**Next ready** : Tranche C (Stage 5 cross-stitching + first paid data) — voir section Tranches actives.


---

## 🔄 Tranche C réordonnée (12/05/2026, post-batch-2)

Ordre : items Stage 2-4 (data foundation) avant Stage 5 (synthesis). Items gratuits avant payants.

#### [ ] C7. Insider BUY cluster (inversion Phase 12.1) (~0.5j) — Stage 4 — **ALPHA #1 ACADÉMIQUE**
Cohen-Malloy-Pomorski 2012 : insiders non-routiniers acheteurs en cluster (≥3 dans fenêtre 30j) délivrent +82bp/mois d'alpha.
- Tu as déjà la pipeline EDGAR Form 4 + classification founder/operational/routine pour SELL
- Inverser le code : `intelligence/insider_cluster.py:detect_buy_cluster` analogue à detect_sell_cluster existant
- Filter : ≥3 distinct insiders BUY, dollar amount > threshold, classification ≠ routine
- Handler `/insider_buy_cluster` + cron daily ~6:30 (juste avant digest 7h)
- Notification auto si nouveau cluster détecté ce matin

#### [ ] C8. 10-K Risk Factor diff YoY (~1j) — Stage 2+3 — RARE SIGNAL FREE
Hudson Labs / Verity facturent 200$/mois pour ça. Free via EDGAR.
- Module `intelligence/filings_diff.py`
- Pour chaque 10-K résident annuel : fetch précédent 10-K même ticker, extract Section 1A "Risk Factors", diff via `difflib` + LLM Sonnet synthesis du diff
- Output structured : `new_risks[]`, `removed_risks[]`, `expanded_risks[]`, `severity_score`
- Cron : run quand nouveau 10-K détecté (signal type='10-K' filed dans EDGAR)
- Handler `/risk_diff <TICKER>` : affiche le diff le plus récent

#### [ ] C9. 8-K item categorization + severity flag (~0.5j) — Stage 2+3 — QUICK WIN FREE
8-K = material events. Items à fort signal :
- 1.01 entry material agreement
- 2.02 earnings results  
- 4.01 auditor change (red flag)
- 4.02 non-reliance previous financials (**CATASTROPHIC red flag**)
- 5.02 officer/director departure (unexpected = red flag)
- 7.01 Reg FD disclosure
- Auto-classify chaque 8-K ingéré + tag severity (low/medium/high/catastrophic)
- Handler `/recent_8k [severity]` filtrable
- Push notification immédiate si severity=catastrophic

#### [ ] C10. FMP Starter $14/mo + EPS revisions tracker (~3h) — Stage 2+3 — FIRST PAID DATA
[Original C8 retained] Bartov-Bernard alpha académique.

#### [ ] C11. Multi-round Bull/Bear debate (3 rounds + convergence) (~3h) — Stage 5 — **UPGRADE C9 ORIGINAL**
Pattern TradingAgents : N rounds dialectiques au lieu de single-shot.
- Round 1 : Bull pose thèse + Bear pose contre-thèse en parallèle (2 Opus calls)
- Round 2 : Bear lit dernière argumentation Bull et challenge spécifiquement les points faibles, vice-versa
- Round 3 : convergence ou désaccord persistant explicite
- Metric : `convergence_score` (similarity entre conclusions finales)
- Si converge → high-conviction signal. Si diverge → complexity flag, requires human attention
- Coût ~6 Opus calls par /analyze = $0.04/run. Justifié pour theses critiques uniquement (filter par materiality)

#### [ ] C12. Risk Management layer post-synthesis (~2h) — Stage 5+6 — TradingAgents/AutoHedge pattern light
Après la synthesis (ou le multi-round debate), 1 Opus call dédié avec system prompt explicit :
- "Tu as accès au verdict du trader. Ton job : challenger sizing, exposure totale, corrélation avec book actuel, time horizon mismatch, scénarios stress."
- Inputs : verdict synthesis + position_book courante + regime + credit_regime
- Output : approved/conditional/rejected + counter-proposal sizing si conditional/rejected
- Empêche rationalisation downstream

#### [ ] C13. Asymmetry-First Scoring (~2h) — Stage 5+6
[Original C10]

#### [ ] C14. Confidence intervals + Bayesian update viz (~2h) — Stage 5+6
[Original C11]

---

## 🔄 Tranche E enrichie (12/05/2026)

Items hors-priorité immédiate mais valeur conservée :

- **CFTC COT data** (~1j, $0) — positioning weekly commerciaux vs spec sur futures (rates/gold/oil/FX/indices). API gratuite. Macro/crypto.
- **Workforce intelligence** (~2-3j, $0) — scraping Lever/Greenhouse/Workday public boards + layoffs.fyi. Lead 1-3 quarters sur fondamentaux.
- **Web traffic + subdomain detection** (~2j, $0) — DNS enumeration + Google Trends pour B2C/SaaS proxy. SimilarWeb-style poor man's version.
- **USPTO + ArXiv R&D tracker** (~2j, $0) — patents filed + papers published per company. Forward 2-4 quarters R&D investment signal. Niche AI/semis.
- **Equity issuance + dilution tracker** (~1-2j, $0) — Form S-3/S-8/424B via EDGAR. Reflexivity proxy Soros. Tesla 2020-2021 archétype.
- **Webpage change monitoring** (~1j, $0) — ChangeDetection.io self-host sur IR pages, pricing pages, exec bios. Event-driven, catch alpha avant 8-K.
- **Polygon Options $29/mo** — déjà listé, valider Tranches A-D avant.
- **PIT bitemporal discipline** — pre-requisite backtest réel, attend.

---

## ❌ Skip définitif ajouté (12/05/2026, post-batch-2)

- **LangGraph state machine + checkpoints** — plomberie enterprise. Decision_journal Phase 18 fournit déjà l'audit trail nécessaire pour solo.
- **App store scraping** (Sensor Tower / Annie style) — hors scope B2C plays. Olivier = thesis-driven concentré sur AI/semi/crypto/macro.
- **USASpending.gov** (government contracts) — hors scope défense/healthcare.
- **Corporate jet ADS-B tracking** — alpha M&A trop niche, faible signal/noise pour scope.
- **Channel check linguistic baseline per CEO** — projet plusieurs semaines, defer 6+ mois post tranches C-D.

---

## 📐 Framework non-tech (à internaliser hors-bot)

Frame "retard vs autres bots" = poison cognitif documenté :
- Pousse au FOMO build (features sans ROI) → dette technique
- Pousse au FOMO trade (chase moves déjà priced) → pattern statistiquement perdant

Trois actions hors-tech :
1. **Benchmark explicite** : TWR portfolio vs SPY/QQQ glissant 12M. Cron mensuel post B5 quand position_book accumule trades.
2. **3 outcomes qualitatifs 6M** (pas features) : ex "Brier <0.20 sur 30 predictions résolues", "0 panic sell sur thesis core", "100% decisions matérielles documentées".
3. **Ban scrolling X de bots concurrents 30j** : signal/noise catastrophique.


---

## ✅ C9 shipped (12/05/2026) — 21 vrais 8-K loggés au smoke

Backlog tuning future (non-bloquant) :
- [ ] 5.02 sub-classification routine vs unexpected via Sonnet reading filing body
- [ ] 7.01 (Reg FD) detection si content material → upgrade severity dynamique
- [ ] /analyze integration : pull 8-K severity≥medium pour ticker dans la fiche


---

## Data Layer Upgrades — Pricing (décision 13/05/2026)

**❌ Ne PAS plug TradingView** — pas d'API officielle, scrapers fragiles, TOS violation, et 15-min delay yfinance suffit pour profil thesis-driven slow alpha.

Roadmap d'upgrades pricing par ordre de leverage marginal :

### 1. Court terme (gratuit, ~1h dev)
**Étendre `crypto_zone_job` pour pull ETH/SOL/HYPE via CoinGecko** en plus de BTC.
- Cost: $0/mo (CoinGecko free 30 calls/min)
- Apporte multi-decimal real-time sur les 4 majors crypto
- Refresh ~1min, précision 6+ décimales
- Action: modifier `intelligence/crypto_zone.py` (ou équivalent) pour itérer sur [BTC, ETH, SOL, HYPE]

### 2. Moyen terme ($14/mo)
**FMP Starter pour EPS revisions** (= C10 backlog déjà identifié).
- Cost: $14/mo (Financial Modeling Prep Starter plan)
- Apporte EPS revisions + analyst estimates + earnings surprises
- Justification académique: Bartov-Bernard alpha sur révisions d'EPS (12-18 mois fenêtre)
- Pas un upgrade prix mais data fundamental complémentaire à yfinance
- Pré-requis: création compte FMP user-side (async)

### 3. Long terme ($29/mo) — IF needed
**Polygon.io Starter pour real-time US equities + options chain**.
- Cost: $29/mo
- Apporte real-time tick (vs 15-min delay yfinance) + options chains
- Pertinent UNIQUEMENT si décision de trader des options
- À reconsidérer post J+60 d'usage prod si gap réel identifié

---

**Principe directeur** : plus de précision prix ≠ meilleur edge pour un profil slow alpha. yfinance + CoinGecko free couvrent 95% des besoins de décision. Polygon est un upgrade de luxe, pas une nécessité.


---

## Path 5/6 Strategic Pivot — High Standard Mode (13 mai 2026)

### Décision stratégique
Objectif explicite : **Path 5 (acquihire $200K-$1M, 18-24 mois) ET/OU Path 6 (content + Substack/prosumer subscription $100K-500K/an, 24-36 mois)**.

Path 1 (mass B2C), Path 3 (license framework), Path 4 (open source pur) explicitement écartés. Path 2 (prosumer SaaS direct) possible en hybride avec Path 6 mois 24+.

### Inflection point
**Velocity a dépassé solidification.** 60+ features shippées en 14h marathon attendent : tests, observabilité, runbooks, documentation actionnable, sources validées, KPIs enforced. C'est exactement le moment d'arrêter d'ajouter et solidifier. Pas glamour, mais c'est ce qui fait la différence entre "j'ai construit un bot" et "j'ai un asset commercialisable".

### Reconnaissance des dettes critiques (issues from audit critique)
1. **"Audit GREEN" était overselling** — c'était linting/imports, pas audit. Zéro test unitaire. Credibility/Brier/materiality math non-vérifiés.
2. **Backup non-scheduled = pas de backup**. Restore non-testé non plus.
3. **PIT discipline absente** — backtest credibility ledger bloqué tant que non migré.
4. **64 handlers sans telemetry** — distribution Pareto inconnue, pas de gating utilisation.
5. **KPIs aspirationnels** — seul KPI #2 (≥5 predictions à J+28) a stop-rule.
6. **60+ items shippés sans hiérarchie d'impact** — on ne sait pas distinguer utile vs cérémoniel.
7. **Fiche mélange 5 cadences** — corruption garantie en 3 mois.
8. **Source actives "à confirmer"** dans doc canon = précipitation.
9. **215 tickers vs 1 thesis active** — pas de policy de gating explicite.
10. **No failure modes registry, no cost trajectory, no glossary, no data lineage**.

---

## Roadmap 4 Dimensions Path 5/6

### Dimension 1 — Solidification technique (4-6 semaines, ~40-45h)
**Objectif : code base auditable par acquéreur sans embarras.**

#### P0 cette semaine (8-10h)
- [ ] Property-based tests Hypothesis sur credibility_update, brier_score, materiality_composite, asymmetry_ratio (6h)
- [ ] Scheduled backup daily cron + restore test automatisé `make test-restore` boot instance test (2h)
- [ ] Confirmer sources actives + tier S/A/B documenté proprement (1h)
- [ ] Handler usage telemetry → table `handler_calls` + cron weekly stats (2h)
- [ ] Failure modes registry `docs/failure_modes.md` — top 5 scenarios (2h)

#### P1 semaine prochaine (8-12h)
- [ ] Failure modes registry P1 — 5 scenarios supplémentaires + runbooks `docs/runbooks/` (3h)
- [ ] Docs restructure : FICHE_TECHNIQUE lean (≤80 lignes) + REFERENCE_SCHEMA.md + HANDLERS_INDEX.md + SOURCES.md + PROCEDURES.md séparés (4h)
- [ ] Concurrency audit + SQLite WAL mode si pas déjà (1h)
- [ ] Cost trajectory model spreadsheet cost-per-feature × frequency × growth (2h)
- [ ] PIT migration plan daté écrit (`docs/adrs/001-pit-bitemporal.md`) (2h)

#### P2 quinzaine (10-15h)
- [ ] CI minimal GitHub Actions running tests on push (1h)
- [ ] Type hints + ruff/mypy basics (4h)
- [ ] Refactor bot/main.py 2428 LOC → bot/handlers/{positions,thesis,insider,journal,filings,debate,risk,brief,asymmetry}.py (4h)
- [ ] Refactor shared/storage.py 1605 LOC → split par domaine (3h)
- [ ] Glossaire `docs/glossary.md` 30-50 termes (1h)
- [ ] Data lineage Mermaid diagram dans REFERENCE_SCHEMA.md (1h)
- [ ] Onboarding "resuming after break" checklist (1h)
- [ ] Universe gating policy écrite dans CONVENTIONS.md (1h)

### Dimension 2 — Mesure track record (6-12 mois, parallèle à D1)
**Objectif : Brier <0.20 sur 30+ predictions résolues + benchmark TWR vs SPY/QQQ documenté.**

**ZÉRO nouveau code.** Pure usage du système.

#### KPIs avec stop-rules et enforcement
| KPI | Cadence check | Seuil dégradation | Action si dégradé |
|---|---|---|---|
| **#2 (NON-NEG)** ≥5 predictions résolues J+28 | Hebdo dimanche | <5 à J+28 | Stop 5j build + force-use |
| **#3** Brier <0.20 rolling 90j | Hebdo dimanche | >0.25 ou >0.30 | Alert + revue méthodo |
| **#4** 0 panic sell thesis core | Mensuel 1er | ≥1 panic sell détecté | Pause + analysis bias_tagger |
| **#5** 100% decisions matérielles journalisées | Mensuel 1er | <90% | Aucune nouvelle thèse jusqu'à backfill |
| **#6** TWR vs SPY/QQQ glissant 12M | Mensuel 1er | <-5% pp | Revue stratégique trimestrielle |

#### Cadence rituelle
- Hebdo dimanche soir : review predictions résolues + Brier + calibration mental
- Mensuel 1er : TWR cumulé + top biais bias_tagger + decisions count
- Trimestriel : decision matrix universe/handlers cleanup

### Dimension 3 — Dépersonnalisation (à partir mois 6)
**Objectif : system devient un framework configurable, pas le bot personnel d'Olivier.**

- [ ] Prompts templatisés (config-driven biases vs hardcoded "vend trop tôt") (6h)
- [ ] Behavioral framework documenté en termes transférables decoupling profile (4h)
- [ ] Onboarding flow capturant biais + univers d'un nouvel utilisateur (8h)
- [ ] Universe + thesis templates par profil (slow_alpha / growth / value / macro) (4h)
- [ ] Compliance positioning : "outil aide décision" jamais "recommandation" — wording legal review (3h)

### Dimension 4 — Positionnement public (à partir mois 12)
**Objectif : audience qui voit la méthodologie tourner avec discipline mesurée.**

- [ ] Substack mensuel : Brier du mois + 1 case study anonymisée + 1 leçon méthodo
- [ ] LinkedIn/Twitter : 1 post/semaine sur 1 invariant méthodologique
- [ ] Page publique calibration plot live (Brier rolling 90j) — le moat
- [ ] Optionnel : opensource framework "behavioral discipline ledger" sans prompts perso

---

## Mode opératoire "High Standard"

À partir de maintenant :
1. **Pas de nouvelle feature avant que les tests existent sur la math critique**
2. **Pas de claim "production-ready" sans coverage report et backup testé**
3. **Pas de doc canon avec "à confirmer" — soit confirmer, soit marquer [STUB]+deadline**
4. **Toute décision architecturale majeure → ADR dans `docs/adrs/`**
5. **Hebdo dimanche : check 5 KPIs ci-dessus + commit hebdo de réflexions**
6. **Mensuel 1er : decision matrix cleanup univers + handlers**
7. **Plus de cron sans observabilité (success rate, duration p50/p95, last_run)**
8. **Plus de feature LLM sans coût modélisé (cost-per-call × estimated frequency)**

---

## Tranches existantes — réordonnancement Path 5/6

Backlog Tranche C/D/E **DÉPRIORISÉ tant que Dimension 1 P0+P1 non shipped.**

Reordonnancement post-solidification :
- **C14 Calibration viz** → bumpé en P0.5 (pertinent track record Path 6)
- **C10 FMP EPS revisions** → après D1 solidification, mois 4-6
- **C8 10-K diff** → mois 6+, gros chunk
- **Tranche D entière** → mois 9-12 minimum, post-validation Brier <0.20
- **Tranche E entière** → mois 12+


---

## P1 Dette technique découverte (recon sources 13/05/2026)

### Bug #1: last_signal_at NULL malgré n_signals > 0
- Symptôme: majorité des sources affichent last_signal_at vide alors que n_signals > 0
- Cause probable: multiple code paths INSERT INTO signals, certains ne callent pas UPDATE sources SET last_signal_at
- Fix: audit grep "INSERT INTO signals" + storage.add_signal vs autres paths
- Effort: ~1h
- Priority: P1 (data integrity, bloque les "sources dormantes" queries)

### Bug #2: materiality_v2 coverage seulement 16%
- Symptôme: 10/62 signaux 30j ont impact_magnitude scored
- Cause probable: cron `materiality_v2 1h` traite batch limité, ou échec silencieux LLM
- Fix: audit logs cron + augmenter batch size + retry sur LLM errors
- Effort: ~2h
- Priority: P1 (le rubric est le coeur du système — 84% non-scored = système borgne)

### Bug #3: SemiAnalysis 0 signaux malgré paid $65/mo
- Symptôme: 0 signaux 30j sur paid sub majeur
- Cause possible: filtre Gmail label "Newsletters" exclut sender, ou email pas envoyé en 30j (peu probable)
- Fix: vérifier label Gmail manuellement + log gmail_fetch_job pour cette source
- Effort: ~30min
- Priority: P0.7 (financial waste si non résolu)

### Bug #4: Sources dupliquées (Stratechery)
- Symptôme: Ben Thompson <email@stratechery.com> ET Stratechery <email@stratechery.com> = 2 entries DB
- Cause: probable case sensitivity ou normalization manquante au create_source
- Fix: dedupe + ajouter normalize_sender_email() helper
- Effort: ~30min
- Priority: P2 (cosmétique mais salit les stats)
