# ARCHITECTURE — Pipeline 7 étages

Référentiel canonique pour structurer le système et classifier le travail. Toute feature nouvelle doit se mapper à un (ou plusieurs) stage. Quand un stage est faible, c'est lui qu'on muscle — pas celui qui est déjà saturé.

## Les 7 étages

1. **STRUCTURE** — Substrat. Schéma DB, ontologie, docs racine, conventions, backup, observabilité du pipeline lui-même (combien de signaux droppés à chaque stage).

2. **DATA GATHERING** — Ingestion brute. Gmail newsletters (9 sources), yfinance, EDGAR Form 4, FRED, calendar earnings/macro. SPOF principal: Gmail OAuth.

3. **ENTONNOIR DE QUALITÉ** — Filtrage. Dedup, `sources.credibility` calibrée par Brier, materiality scoring, cross-source corroboration, noise rejection. *Le stage où l'asymétrie signal/bruit se forge.*

4. **SIGNAUX** — Extraction. Top material signals, insider clusters, narrative saturation, temporal divergence (cette semaine vs trailing 4w), cross-source convergence count.

5. **REFLECTION/DIGESTION** — Analyse. `/analyze` deep fiche, digest, regime, credit, macro, why_matters LLM. Le stage où "des données" deviennent "une thèse".

6. **APPROPRIATION** — Internalisation. Theses actives, predictions Brier-tracked, decisions journal (Phase 18), conviction history, position book, risk budget. *Le stage où le système devient TIEN, pas générique.*

7. **RESTITUTION** — Output. Handlers Telegram, digest 7h, alerts price_monitor, heartbeats, weekly/monthly reviews.

## État actuel par stage (12/05/2026)

| Stage | État | Lacune principale |
|---|---|---|
| 1 Structure | Solide | Pas d'observabilité pipeline (drop rate par stage) |
| 2 Data gathering | Bon | SPOF Gmail; pas de RSS / options unusual / 13F |
| 3 Entonnoir | **FAIBLE — goulot** | credibility statique; pas de Brier; bug +label dedup; pas de cross-source |
| 4 Signaux | Fonctionnel mais shallow | Cluster insider isolé; pas de temporal divergence; pas de corroboration |
| 5 Reflection | Strong en isolation, non-cross-stitché | `/analyze` ne consomme pas materiality_top du jour; pas de red-team intégrée |
| 6 Appropriation | Renforcé par Phase 18 | Manque position book → impossible risk budget / auto-hooks trades |
| 7 Restitution | Saturé (39 handlers) | Aucune mesure d'usage; candidat dégraissage post-Stage 3-4 |

## Diagnostic structurel

Le système est **lourd aux extrémités (1, 2, 7), léger au centre (3, 4)** — pattern classique d'un bot construit feature-first plutôt que pipeline-first. Le goulot est l'entonnoir de qualité : tant que `sources.credibility` reste figé, tout le reste amplifie indistinctement signal et bruit.

## Règle de priorisation

Pour toute feature candidate, poser ces 3 questions dans l'ordre :
1. Quel stage est musclé par cette feature ?
2. Ce stage est-il déjà saturé ou est-il un goulot ?
3. Renforcer un stage saturé = ROI nul. Renforcer un goulot = ROI compound sur tous les stages aval.

## Séquence haute-leverage active

Voir `TODO.md` section "Stage-weighted roadmap" pour la séquence ordonnée par ROI compound.


---

## Tranches actives (12/05/2026)

Re-priorisation post-évaluation de ~30 ideas externes "Bloomberg-adjacent" (cf section "Ideas evaluated" infra). Tranches ordonnées par ROI compound sous contraintes : **capacité cognitive de l'outil + budget data $75/mo max**.

### Leviers stratégiques structurants

**Levier #1 — Cascade LLM routing + prompt prefix caching** (Tranche A2). Réduit -60 à -80% le coût LLM. Sans lui, l'enrichissement de `/analyze` (devil's advocate, asymmetry scoring, case-based, confidence intervals) explose le budget et force des arbitrages features. Avec, on garde l'ensemble.

**Levier #2 — Pre-Mortem auto-gen** (Tranche B7). Seule feature forçant structurellement l'exit discipline AVANT entry. Sans elle, le journal Phase 18 documente l'échec d'exécution mais ne le prévient pas.

### Tranche A — Stage 3 musclage (le bottleneck, must come first, ~9h)

| # | Tâche | Effort | Output |
|---|---|---|---|
| A1 | Brier calibration + boucle credibility | ~1h | Calibration empirique sources |
| A2 | Cascade routing Haiku/Sonnet/Opus + prefix caching | ~3h | -60 à -80% coût LLM |
| A3 | Echo Chamber Resolution (semantic dedup cross-source) | ~3h | 1 signal corroboré pas N indépendants |
| A4 | Information Half-Life par source | ~2h | Urgence d'action calibrée par source |

### Tranche B — Stage 6 approfondissement (compound on Phase 18, ~7h)

| # | Tâche | Effort | Output |
|---|---|---|---|
| B5 | Position book + auto-hooks /position_buy/sell | ~3h | Risk budget calculable, overweight alerts |
| B6 | Bias tagging extension Phase 18 (column bias_tags) | ~2h | Pattern mining biais cognitifs perso |
| B7 | Pre-Mortem auto-gen sur création thesis (1 call Opus) | ~2h | Exit discipline pre-commit |

### Tranche C — Stage 5 cross-stitching + first paid data (~9h + $14/mo)

| # | Tâche | Effort | Output |
|---|---|---|---|
| C8 | FMP Starter $14/mo + EPS revisions tracker | ~3h | Alpha académique Bartov-Bernard |
| C9 | Bull/Bear adversarial pass sur /analyze + /digest | ~2h | Red-team intégrée |
| C10 | Asymmetry-First Scoring (convexity > EV) | ~2h | Counter direct biais vend-trop-tôt |
| C11 | Confidence intervals + Bayesian update viz | ~2h | Calibration mesurable, posterior tracé |

### Tranche D — Stage 4 enrichissement (~11h)

| # | Tâche | Effort | Output |
|---|---|---|---|
| D12 | LanceDB local + embeddings tous signaux | ~4h | Vector DB persistant |
| D13 | Case-based reasoning intégré /analyze | ~2h | Base rate empirique perso |
| D14 | Anti-Narrative / crowded-trade detection (= Phase 19) | ~3h | Counter direct biais crypto-tops |
| D15 | Temporal divergence + cross-source corroboration count | ~2h | Cette semaine vs trailing 4w |

### Tranche E — Defer 3-6 mois (conditionnel à A-D done)

- Polygon Options $29/mo (gamma exposure, sweeps) — valider A-D d'abord
- PIT bitemporal discipline — quand backtest réel sera prêt
- Insider Replication virtual portfolio — post position book
- Persona Ensemble étendue 5 — resté à 2 jusque-là
- Reflexivity Detector — hand-wavy académique
- Structured logging + Prometheus + Grafana — overkill solo
- Phase 20 Regime Transition Detector — déjà Tier S original, attend A-D

### Skip définitif (sous contraintes actuelles)

| Idée | Raison |
|---|---|
| Causal DAG Pearl complet | Trop ambitieux solo, ROI lointain |
| Paralinguistic earnings audio | Alpha académique mince (Larcker-Z. effect size faible), compute lourd |
| Pydantic + mypy strict everywhere | Effort/ROI faible solo, polish ingénieur premature |
| Postgres / DuckDB migration | SQLite tient pour scope, premature |
| Ortex, WhaleWisdom | Free tier FINRA + EDGAR direct font 90% du job |
| Property-based testing exhaustif | Effort/ROI faible, sélectif si besoin |

### Ideas evaluated externes (12/05/2026)

Document utilisateur uploadé 12/05/2026 avec ~30 features Bloomberg-adjacent. Ranking critique :

| Idée | Verdict |
|---|---|
| Echo Chamber Resolution | **Ship Tranche A3** (bullshit-filter Stage 3 missing piece) |
| Information Half-Life par source | **Ship Tranche A4** (calibre urgence par source) |
| Asymmetry-First Scoring | **Ship Tranche C10** (counter biais vend-trop-tôt) |
| Pre-Mortem auto-gen | **Ship Tranche B7** (exit discipline pre-commit) |
| Anti-Narrative / Crowded trade | **Ship Tranche D14** (counter biais crypto-tops) |
| Meta-Cognitive Bias Tagging | **Ship Tranche B6** (extension Phase 18) |
| Case-Based Reasoning vectoriel | **Ship Tranche D13** (base rate empirique unique vs BBG) |
| Persona Ensemble Framework | **Réduit à 2 (bull/bear) en C9**, pas 5 |
| Reflexivity Detector | Defer (hand-wavy académique) |
| Insider Replication Portfolio | Defer post B5 (position book pre-requisite) |
| Causal DAG Pearl | **Skip** (trop ambitieux solo) |
| Paralinguistic earnings calls | **Skip** (alpha marginal, compute lourd) |

**Critique du framework externe** : conflation systématique entre "engineering polish" (Pydantic+mypy, PIT bitemporal, schema versioning Alembic) et "alpha generation". Premier batch = polish nice-to-have. Second = revenue. La priorisation actuelle distingue.


---

## Re-ordering Tranche C (12/05/2026, post-idea-eval batch 2)

Évaluation critique d'un second batch d'idées externes (~18 items TradingAgents-like + alt-data sources + filings intelligence). Verdict :
- **3 quick wins gratuits non-couverts** insérés en tête de Tranche C (insider BUY cluster, 10-K diff YoY, 8-K categorization)
- **C9 upgrade** : single-shot bull/bear → multi-round dialectique avec convergence detection (TradingAgents pattern)
- **C9b ajouté** : Risk Management layer post-synthesis (séparé de la trader synthesis), version light de TradingAgents/AutoHedge
- **D12+ étendu** : LanceDB inclut désormais filings corpus (10-K/Q/8-K) pour Document RAG, pas juste signals
- **Tranche E enrichie** : CFTC COT, workforce scraping, USPTO+ArXiv, dilution tracker, webpage monitoring
- **Skip définitif ajouté** : LangGraph state machine (overkill solo), app store scraping (hors scope B2C), USASpending (hors scope), corporate jet ADS-B (niche), channel check linguistic baseline (defer 6+ mois)

**Principe de réordonnement** : Stage 2-4 (data foundation) avant Stage 5 (cross-stitch) au sein de Tranche C. Items gratuits avant items payants. Insider BUY cluster en premier car académiquement le plus solide (Cohen-Malloy-Pomorski +82bp/mois) et zero coût.
