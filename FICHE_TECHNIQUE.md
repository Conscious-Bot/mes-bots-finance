# PRESAGE (mes-bots-finance) — Fiche Technique (Lean)

**Version**: 01 juin 2026 soir (Day 27 — polish UI 8 pages + 5 tâches P2 fermées + filet 4-layer currency)
**Auteur**: Olivier Legendre
**État**: High Standard / Observation jusqu'au 10/06/2026 (KPI #2 batch resolution V1 ; V2 pour cohortes futures wired en prod)
**Bot**: Telegram @Hawk_Dove_bot (mono-instance lock fcntl depuis 01/06)

## Session 01/06/2026 — 8 commits, polish UI complet + filet currency + 5 tâches P2

Session multi-bloc : polish dashboard exhaustif + canonisation currency-native + dette technique P2.

### Dashboard polish UI (8 commits avant tâches P2)
- **8 Stars** (verdict 3 secondes) sur les 8 pages : Vue d'ensemble, Discipline, Positions, Copilot, Thèses, Stratégie, Concentration, Signaux, Urgence
- **Palette modernisée TR/Robinhood** : `--acc #16C055`, `--bear #E53935`, `--bg #F8F9FB` (light bg), respiration spacing tokens élargie
- **Sparkline hero** Catmull-Rom smoothing + area fill gradient + endpoint pulse animation
- **Accordéon FX** : pattern `geo-item` cloné pour exposition par devise (click → drop tickers + poids)
- **8 section icons** SVG inline 16×16 cohérents (`sh-ico`) sur tous les headers (Synthèse copilot, Prédictions, Biais fomo_greed, Biais lock_in, Journal, Stratégie déclarée, Lecture livre, Risques cachés)
- **Sidebar tooltip stacking context fix** : `.sidebar z-index:60` + `.wrap z-index:0` isole + bg ink contrasté
- **Logo PRESAGE refonte fidèle** : sparkle 4-points élongué vertical + halo radial + 7 dots signal droite + wordmark espacé
- **Réordre Vue d'ensemble** : Opportunités + Mouvement du jour AU-DESSUS de Top risque (lecture acte→bouge→risque)
- Cmd+1..9 retirés (parasite UX), Cmd+K conservé
- Transitions smooth sur `.card` `.kpi` `.row[data-tk]` (slide-in 4px hover)

### Currency-native canonisé (L12 LESSONS, fix racine bug récurrent)
Bug 4063.T cible +23876% (31/05) puis stop -11089% (01/06) = même classe = mix EUR/native dans formule `%`.

- **Helper canonique** `_stop_distance_pct_native(ticker, stop_price)` dans `dashboard/render.py` : tout calcul `%` impliquant un prix-thèse passe par native vs native
- **Sentinel TARGET_HIT** (`asymmetry_ratio = 999.0` quand `current ≥ target_full`) → `_asym_format()` rend "cible ✓" pas "999.0×"
- **Accordéon FX** `compute_fx_exposure()` étendu avec `holdings[{tk, eur, pct_of_cur}]`
- **LESSONS.md L12** : "Devise native vs EUR : interdit mélanger dans une formule de %"
- **Memory** `currency-native-render-helper`

**Filet anti-régression 4-layer** (`tests/test_currency_native_guard.py`) :
1. Grep static sur `render.py` + `intelligence/` + `shared/` (pattern syntaxique EUR/native dans expression arithmétique)
2. Helper canonique présent
3. Sentinel TARGET_HIT branchement explicite (`ratio >= 999`)
4. Smoke e2e du HTML rendu (fail si `%` > 1000 apparaît, signature classique JPY/KRW)

### 5 tâches P2/P3 fermées
- **#34** Guard mono-instance bot/main.py : `fcntl.flock` exclusif sur `data/bot.pid`, 2e instance exit 1 propre. N'affecte pas le tennis bot (process différent, lock différent).
- **#40** Endpoint Telegram `/bias_status` : aggregate read-only des `bias_events` (total + breakdown par bias + status). Empty state propre pré-J-day avec marqueurs de canaux.
- **#36** Couverture chemins critiques : `materiality_boost.py` 17%→**100%** (13 tests) + `asymmetry.compute_thesis_asymmetry` 13 chemins (19 tests pure-function).
- **#38** Tests `self_loop_v0` isolation : fixture `_isolated_db` autouse avec schéma temp (decision_counterfactual + counterfactual_resolution + decisions + triggers append-only). Plus de `database is locked` sous load bot, plus de 150 rows TEST_SL_ qui s'accumulent en prod. 13 tests verts en 1s.
- **#41** Fixture `migrated_db` + invariants L8 à la racine : `tests/conftest.py` expose fixture pytest réutilisable qui crée sqlite temp + lance `bootstrap_schema (alembic upgrade head)` + monkeypatch `storage.DB_PATH`. `tests/test_migrated_db_schema.py` : 7 tests d'invariant qui catch toute future drift schéma/code (note_tags_json, position_event_id, status enum, append-only triggers, baseline_price).

### Backup + checkpoint
- Backup tarball + DB snapshot 01/06 23:40 (DB integrity OK)
- 8 commits propres, branche `main`

### Pour reprise demain
Roadmap chronologique (cf memory `session_roadmap_j_day`) :
1. **#67 Macro composite V3 holdout OOS strict** ← bloquant non-gated avant J-day
2. **#15** Pre-J-3 vérif scaffolds activation sur vraies résolutions (07/06)
3. **#13** J-day 10/06 batch KPI #2 + observer activation
4. **#19** Publi #01 réelle (post-J-day si densité)
5. **#11** Hero track record (J+30 = 10/07)
6. (mi-juin) #35 mypy strict + #61/#66 refactor render.py
7. (sur déclencheur) #21/#22 viz upgrades, #24/#37 site presage.pro

---

## Session 30/05/2026 — 35 commits, 14 chantiers, 10 itérations arc V2

Audit pré-batch 10/06 a révélé les 40 prédictions toutes dans probabilité [0,608-0,658] (mono-bucket V1). Réécriture pipeline scoring + intégration sources primaires SEC + verification empirique.

### Architecture livrée
- **SIGNAL_SCORER_V2** (`intelligence/signal_scorer_v2.py`, ~189 lignes) : prompt LLM 3 étapes (base rate / ajustement / anti-ancrage), enforcement weak→watch + sémantique P(call correct) + zone morte interdite. Intégré dans `intelligence/learning.auto_register_predictions`. Cohortes FUTURES utilisent V2 (cohortes du 10/06 restent V1 figées).
- **Wire SEC EDGAR primary forward** (`intelligence/edgar_signal_wire.py` + `shared/edgar_exhibits.py`) : 8-K + insider buy clusters → `signals` → V2 → predictions. Forward-only strict. Source dédiée `SEC EDGAR 8-K` / `Insider Cluster` credibility=0.85. Dedup `gmail_id='sec_8k:{accession}'` / `'insider_cluster:{ticker}:{date}'`. Hook sync dans `EightKSource.persist()` et `BuyClusterSource.persist()`.
- **Extracteur d'exhibits** : `extract_filing_content(filing_url)` résout cover→exhibit (typiquement Exhibit 99.1 = press release). Fix iter 5 du bug "URLs vers cover page".
- **Consolidation `storage.DB_PATH`** : `_DB_PATH` devient alias dynamique via `__getattr__` module-level. Anti-régression pollution prod via tests. `tests/test_db_path_alias.py`.
- **ADR 012** : 8-K severity classifier soft-deprecated comme mesure evidence_strength (conservé pour alerting heuristique low-latency seulement).

### Vérification (10 itérations, pattern adversaire)
- DoD e2e wire : NVDA Q1 FY27 8-K → V2 prob=0.750 bullish strong ✅
- DoD insider synthétique 3 niveaux : weak→watch, moderate→0.62, strong→0.74 ✅
- Dry-run résolution pré-10/06 : Brier 0.295 attendu (PIRE qu'un prior 0.5 trivial). Mécanisme tourne (40/40 prix fetched). V1 mauvais comme prédit.
- Pattern itéré 10 fois : *"la conclusion est toujours en avance d'un cran sur la preuve"* — y compris sur le fix lui-même (iter 9 : alias statique n'était pas un fix, test régression l'a montré).

### 3 posts canoniques bilingues FR+EN dans `posts/`
- `post_01_calibration_unanchored.md` : "Six fois j'ai cru avoir fini" (arc V2)
- `post_02_comment_that_lied.md` : SK Hynix 1600× bug (data > comments)
- `post_03_dry_run_eleven_days.md` : J-11 dry-run honnête
- Phase A juillet du `PLAN_ACQUIHIRE.md` : 3 brouillons faits, ~60 jours d'avance

### Hygiène + sécurité
- Audit security 7 patterns (sk-ant-, ghp_, xoxb-, BEGIN PRIVATE KEY, Bearer 30+, ya29., AKIA) : 0 vraie clé exposée. `.env.example` placeholders confirmés. Item "hygiène secrets faite une fois" validé binairement.
- TODO + SESSION_STATE + CONVENTIONS §5 (DB_PATH) refreshés.
- Backup tarball + tag `eod-30-05` pushé.

## Session 29/05/2026 — 53 commits

Refonte profonde du systeme d'aide a la decision :

### Architecture (sprints 5-19)
- **Sprint 5-6** : Note du portefeuille deterministe (6 dims) + Note PF panel + simulate_grade + injection copilot
- **Sprint 7** : Chat surface dashboard (RAG profil + grade + positions + theses + interventions)
- **Sprint 8** : /grade Telegram + backfill 41 pre_mortems
- **Sprint 9** : Chat persiste (chat_messages) + chat-driven trade execution + Layer 2 conceptions + Layer 3 preferences
- **Sprint 9.d** : Passive signal extraction (chat_extracted_signals)
- **Sprint 12** : Tagger sur 4 axes (driver/stage/moat/macro_factor) pour redefinir redondance et decorrelation
- **Sprint 13** : Trajectory grade + factor exposures + stress tests
- **Sprint 14** : SPOF graph upstream + Mauboussin implied sizing + valo > bull case
- **Sprint 15** : Kill-criteria monitor + alertes Telegram
- **Sprint 16** : PEA/CTO wrapper + tax-loss + FX exposure + alpha vs SOXX
- **Sprint 17** : Data-defined clusters par correlation rendements
- **Sprint 18** : Gates concentration + vraie Fragilite + remove old narrative panel
- **Sprint 19** : user_strategy declare (target 75%, benchmark SOXX, concentrator_thematic)
                + kill-criteria pre-alert + chat compound + auto-classification

### Glossaire canonique (FR clair) - 5 axes + 2 notes
- **Solidite** : Incontournable / Solide / Incertain / Fragile (ex T1+/T2/T3/T4)
- **Pari** : Pari principal / Autre pari (ex cluster_cap / decorrelation)
- **Doublon** : Solo / Doublon (driver+stage strict)
- **Sante** : Sain / Sous surveillance (verifie ticker_meta + review freshness)
- **Calibrage** : OK / Trop gros / Trop petit (vs cap conviction)
- Notes : **Construction** = Solidite + Pari + Calibrage / **Fragilite** = Sante + cycle/valo

---

## Mission

Système d'intelligence finance perso en boucle fermée self-learning (Telegram + Claude). **Mécanise la discipline.**

**Biais documentés et état d'instrumentation** (source canonique : [`docs/glossary.md` § Biais documentés](docs/glossary.md)) :
1. **`lock_in`** — vendre les winners trop tôt (historique PLTR @9, NVDA @130). **Biais #1 de PRESAGE, raison d'être.** *Non instrumenté à ce jour* — chemin prévu Surface 2 (ADR-010 §2), non livrée. Toute surface qui présente PRESAGE comme mécanisant ce biais lit faux.
2. **`fomo_greed` (enum technique, acception large)** — « pas réduit/sorti quand la discipline le disait ». Mécanisé sur 2 canaux (cf glossaire) : `kill_criteria` actif, `over_cap` en veille (par décision) phase construction.
3. **Biais #2 historique anti-FOMO crypto aux tops** — distinct de l'enum `fomo_greed` ci-dessus (cas spécifique signal-de-top, pas l'enum large). Dormant ortho depuis stock-only 26/05 — 0 crypto en book. Code backend (regime CRYPTO-TOP-ZONE, risk_manager, self_loop) préservé, réactivable.

*Vision projet (31/05) : outil rigoureux multi-tenant subscription investisseurs sérieux, track record performance proof-of-value.*

Le bot **ne trade pas**. Il force la réflexion structurée pré-commit via thesis tracker bidirectionnel, calibration Brier, multi-round debate, /risk_check Opus, journal auto-résolu. Boucle : ingestion → process LLM → décision → prédiction (horizon mesurable) → outcome → rétrospection → enrichissement contexte → loop.

---

## Stack contraintes

- Python 3.14, SQLite **WAL mode**, APScheduler, embeddings BGE-small-en-v1.5 locaux
- Cascade Anthropic : Haiku (volume) / Sonnet (enrich) / Opus (raisonnement)
- Dashboard read-only : `dashboard/render.py` (static-gen → dashboard.html) + `dashboard/serve.py` (stdlib, 127.0.0.1:8000)
- **PAS** FastAPI / Postgres / Redis / LangGraph. Local MacBook Pro, pas de cloud.
- Coût observé : **~$15-20/mo** (budget $50)

---

## État empirique (29 mai 2026 — Day 24, post-session)

| Métrique | Valeur |
|---|---|
| Tests | **352** (Hypothesis + smoke, 100% pass) |
| Thèses actives | **28** (canoniques) — 13 archivees 'out_of_scope' (NVDA/MRVL/CEG/GEV/BWXT/...) |
| Positions tenues | **27** (sans VRT/TER fermees post-trades, avec SNOW nouveau) |
| Prédictions | 188 total, 8 décisions resolved encore 0 J+30 |
| Signaux | 291 cumulés |
| Univers canonique | **29 tickers** (1 source de verite via positions + scripts/canonical_perimeter.json) |
| Handlers Telegram | **73** (telemetry actif, top : /analyze 54, /brief 43, /digest 40) |
| Crons | **35** (incl. daily portfolio_grade 23h15, kill_criteria 07h30, weekly bot_conceptions Sun 19h, monthly bot_preferences 1er 04h) |
| ruff | 0 erreur |
| **Note PF** | **A+ 91/100** (post user_strategy : target cluster 75%, aucun gate actif) |
| Tables DB | 47 (incl. 11 nouvelles cette session : chat_messages, chat_extracted_signals, bot_conceptions, bot_preferences, ticker_axes, ticker_meta, kill_criteria_alerts, data_clusters_snapshots, portfolio_grades, portfolio_narrative_clusters, user_profile) |
| Migrations Alembic | 15 (0015 = data_clusters_snapshots) |
| Pages dashboard | **7** (vigie / positions / theses / **strategie** / concentration / signaux / urgence) |
| Panels dashboard | 20 distincts |

### Strategie utilisateur declaree (config.yaml.user_strategy)
- archetype : `concentrator_thematic`
- target_cluster_cap_pct : 75 (vs default 35)
- target_decorrelation_pct : 15
- accepted_concentrated_factors : ["AI capex", "AI inference/compute demand"]
- benchmark_ticker : SOXX (vs ^SOX)
- thesis_horizon_years : 7

### Book actuel (29/05/2026, post-trades VRT/TER -> CCJ/SNOW)
- Cost basis : 43 091€
- Market value : 53 558€ (+24.3%)
- Wrapper : PEA 17% / CTO 83%
- Pari principal : AI capex 66.5% (vs cible 75% — at_or_below)
- Cycle/valo expose : 30% (>cible 20% : STMPA fade, 000660.KS fade, 6920.T fade+valo>bull, ALAB fade+valo>bull, COHR, AMD)
- Doublons strictes : MU↔SK Hynix (Memory cycle + HBM/DRAM IDM) — 2.5% du book
- Sante : 82.9% sains, 7 sous surveillance (fade ou valo>bull)

---

## Architecture (couches)

1. **SUBSTRATE** — schéma DB (33 tables), config.yaml, secrets
2. **INGESTION** — Gmail (max_results 50), EDGAR, FRED, yfinance, CoinGecko
3. **ENTONNOIR** — signal_type Haiku + materiality_v2 Sonnet chaîné + echo BGE
4. **SIGNAUX** — insider clusters, 8-K cat, crypto zones, debt-crisis monitor (15 indicateurs)
5. **SYNTHESIS** — multi-round debate, /analyze deep, /risk_check Opus (avec injection signaux newsletters)
6. **APPROPRIATION** — position book, journal auto-resolve, bias_tagger
7. **RESTITUTION** — /brief, /digest 2x/j, /kpi_status, /cost_trajectory
8. **OBSERVE (dashboard)** — PRESAGE, lecture seule ; toute décision reste sur Telegram

**Passerelles uniques** : DB → shared/storage.py, LLM → shared/llm.py, Telegram → shared/notify.py, config → shared/config.py, prix → shared/prices.py (HARDCODED_FX_TO_EUR), display → shared/display.py.

**Avertissement schéma** : CONVENTIONS.md et KPI_DASHBOARD.md décrivent des colonnes périmées (claim_json, outcome_evaluated_at n'existent pas). Vérité = `sqlite3 data/bot.db ".schema <table>"`. predictions porte : resolved_at, final_price, return_pct, outcome, probability_at_creation, brier_score. theses → narratif via `notes` (`sector_thesis_id: <ID>`).

---

## Brier / track record — état honnête (MAJ 30/05/2026 soir)

**Trois couches successives de réparation** :

1. **Pré 23/05** : `probability_at_creation` = snapshot crédibilité source ~0.5 = Brier vide (cluster 0.50 partout).
2. **23/05 fix V1** : `estimate_probability(score, credibility, signal_type, impact_magnitude)` formule cap [0.50, 0.72]. Diversifie via score, MAIS produit **mono-bucket** sur les inputs uniformes du pipeline newsletters (toutes sources cred=0.50 default, scores 6-7 dominants → 4 valeurs uniques sur 40 predictions).
3. **30/05 fix V2** : `signal_scorer_v2.score_directional_probability()` = LLM 3 étapes (base rate / ajustement / anti-ancrage). Plage réelle [0.0, 1.0] sans cap artificiel. Source contamination (source_name) éliminée du prompt. `weak/none → watch` enforced. `prob < 0.55 → watch` (sémantique P(call correct)). Wire EDGAR primary pour nourrir le V2 d'évidence forte. Forward-only strict.

**Le batch 10/06 (40 predictions) reste sous V1 figé** — cohortes loguées pré-V2 ne se ré-écrivent pas. Dry-run J-11 confirme : Brier attendu ~0.295 (PIRE qu'un prior 0.5 trivial). **NE PAS publier comme track record positif**. À publier honnêtement comme baseline V1 fige (cf `posts/post_03_dry_run_eleven_days.md`). Vraie calibration V2 = post-août quand N V2 suffisant (script de monitoring : `scripts/post_resolution_brier_report.py`).

---

## KPIs runtime

| KPI | Cible | État 23/05 |
|---|---|---|
| #1 uptime 30d | >95% | 99.9% ✅ |
| **#2 NON-NEG** ≥5 résolues/28d | ≥5 | 1 résolu, ~40-44 dues 10/06, J-18 ⏳ ON TRACK |
| #3 Brier <0.20 rolling 90d | <0.20 | N=1 🔍 insufficient (vrai mesure post id≥158) |
| #4 0 panic sell core | 0 | 0 ✅ |
| #5 décisions journalisées | 100% | forward-only depuis 21/05 (baseline reset) |
| #6 Pf vs SPY/QQQ/SMH | >-5pp | 🔍 INSUFFICIENT (need 365d) |

---

## Concentration

EXCESSIVE : cluster AI Compute ~80% du book (cap narratif advisory 30-35%, 6 lignes > 5%). Le bot signale en OVERWEIGHT advisory (ADR 008) ; trim/hold = décision opérateur (Olivier), pas une règle config.

---

## Path 5/6

**Path 5** (acquihire $200K-$1M, 18-24mo) ET/OU **Path 6** (Substack + prosumer subscription, 24-36mo).
Dim 1 solidification : avancée. Dim 2 track record : activée (KPI runtime + timer 10/06). Dim 3 dépersonnalisation : month 6+. Dim 4 public : Substack post-Brier mesurable (~fin juin+).

---

## Documents canoniques

| Fichier | Rôle |
|---|---|
| `docs/AGENT_HANDOFF.md` | Manuel de reprise pour agent IA (contrat de travail, structure, conventions) |
| `HANDOFF.md` | Log de session chronologique (lire le tail) |
| `SESSION_STATE.md` | Handoff session courte |
| `TODO.md` | Backlog actionnel courant |
| `PHILOSOPHY.md` | High Standard Mode + boucle |
| `CONVENTIONS.md` | Naming + structure + Lessons 1-41 |
| `docs/adrs/` | ADR 001-008 (registry décisions archi) |
| `docs/failure_modes.md` | FM-1 à FM-12 + runbooks |
| `dashboard/render.py` + `serve.py` | Couche OBSERVE |

---

## Principes directeurs

1. Le bot ne trade pas, il force la discipline pré-commit
2. Précision dans la mesure > surface monitorée
3. Cascade LLM : Haiku volume, Opus raisonnement
4. Bidirectionnel : anti-vend-trop-tôt ET anti-tient-trop-long
5. Matière empirique > construction (KPI #2 NON-NEG)
6. High Standard : tests + coût modélisé + observabilité avant feature
7. Pas de scope creep : stack contraint jusqu'à break explicite
8. Less surface > more discipline
9. Backup + versioning obligatoire
10. Track record > features

---

## Appropriation roadmap (cadre 14/05, échelle de mois)

Le bot instrumente des DÉCISIONS réelles ; sans positions réelles, les boucles bidirectionnelles n'ont rien à instrumenter. Staging psychologique, pas un toggle :
- **Phase 1** (~fin mai) : pré-conditions sécurité (FileVault, bot.db hors iCloud, restore test, risk.validate wired, paper_only vérifié)
- **Phase 2** (~mi-juin, post-10/06) : 2-3 quality compounders neutres (pas PLTR/NVDA/crypto)
- **Phase 3** (~juillet, post-30j Phase 2) : positions chargées, PLTR-equivalent en dernier
- **Phase 4** (~août-sept) : full portfolio + execute_real si retenu

Policy 2-week observation post-opening (Day 16) : pas d'action portfolio offensive avant J+14 d'une thèse. À encoder dans PHILOSOPHY.md + guardrail bot.

## MAJ 27/05/2026 — Dashboard cockpit (canonique)
Cockpit HTTP (dashboard/serve.py, http://127.0.0.1:8000/dashboard.html) : identite visuelle canonique -- palette par etat (rouge breche / ambre attention / vert sain / bleu donnee / ink valeur), metal sur readouts (technique --c) et titres chrome (silver dark / graphite frost, 46px). 3-leviers Taille / Cible / Stop distincts. Reference : CONVENTIONS.md.
Stock-only depuis 26/05 (axe crypto/biais #2 en pause). Prochain jalon : batch KPI #2 le 10/06.
