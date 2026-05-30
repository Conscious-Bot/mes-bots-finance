# AGENT_HANDOFF — Manuel de reprise pour le prochain agent IA

> But: permettre a un agent IA qui ouvre ce repo a froid de reprendre sans rien casser.
> Ordre de lecture: ce fichier -> SESSION_STATE.md (tail) -> PHILOSOPHY.md -> CONVENTIONS.md.
> Derniere maj: 2026-05-30 (day25-arc-v2-calibration, 35 commits, wire EDGAR primary).

## 0. Contrat de travail — LIRE EN PREMIER

- Tu (l'agent) n'as PAS acces a la machine d'Olivier ni au repo en execution. Tu AUTHORES du bash/python; Olivier le COLLE dans SON terminal et te renvoie la sortie. Tu ne lances rien toi-meme contre le repo. Toute "verification" passe par un bloc qu'il execute.
- Verite > complaisance. Olivier veut le red-team explicite, les failure modes, l'avis tranche, la mediocrite nommee. Pas de flagornerie. Quand il est a un point d'arret: defaut = la cloture la plus complete (commit + doc + backup), pas une matrice de choix.
- Langue: francais, jargon pro, droit au but. Prose > bullets sauf doc de reference.
- Reversible > destructif. Backup avant toute edition DB ou ecrasement de fichier. Jamais de DELETE quand un UPDATE/retag suffit.

## 1. Ce qu'est PRESAGE

Systeme d'intelligence finance perso en boucle fermee self-learning. Telegram bot (@Hawk_Dove_bot) + Claude. Marque: PRESAGE (le veilleur qui voit/entend et sonne le Gjallarhorn).

Le bot NE TRADE PAS. Il mecanise la discipline pre-commit pour compenser deux biais asymetriques d'Olivier:
1. vend les winners trop tot (locking-in + mean-reversion) — historique PLTR @9, NVDA @130;
2. ne vend pas la crypto aux tops d'indicateurs (FOMO/greed sur BTC/ETH).

Boucle: INGESTION -> PROCESSING(LLM) -> DECISION -> PREDICTION(horizon mesurable) -> [TEMPS] -> OUTCOME -> RETROSPECTION(calibration/credibilite) -> ENRICHISSEMENT CONTEXTE -> [LOOP]. Regle d'or: tout output non instrumente (claim mesurable + horizon + retour d'outcome) est gaspille.

Cible strategique: Path 5 (acquihire, 18-24mo) et/ou Path 6 (Substack + track record, 24-36mo). Mode actuel depuis le 13/05: High Standard / Solidification > Velocity.

## 2. Stack & contraintes

Python 3.14, SQLite (WAL mode), APScheduler, embeddings BGE-small-en-v1.5 locaux, cascade Anthropic (Haiku volume / Sonnet enrich / Opus raisonnement). Tourne en local sur MacBook Pro, pas de cloud. Cout observe ~$15/mo (budget $50).

INTERDITS de stack (jusqu'a break explicite): FastAPI, Postgres, Redis, LangGraph. "Less surface > more discipline."

## 3. Structure du code

Passerelle unique par ressource (si tu vois `import sqlite3` hors storage.py = bug archi):
- DB        -> shared/storage.py        (seul point d'acces SQLite; insert_prediction y est le SEUL funnel de creation de prediction)
- LLM       -> shared/llm.py            (cascade + cout)
- Telegram  -> shared/notify.py
- Config    -> shared/config.py         (config.yaml + env)
- Prix      -> shared/prices.py         (yfinance; HARDCODED_FX_TO_EUR: USD 0.858, JPY 0.005467, KRW 0.000591, GBP 1.17...)
- Math pur  -> shared/math_helpers.py   (compute_brier_score, estimate_probability, clamps)

Couches:
- data_sources/   ingestion (gmail_.py entry point cron 1h, edgar, fred, coingecko)
- intelligence/   learning.py (resolve_due_predictions, horizons), materiality_v2.py, asymmetry.py, digest.py, journal.py, credibility.py, snapshot.py (agregat dashboard)
- bot/main.py     ~2400+ LOC, tous les handlers Telegram + scheduler (refactor en handlers/* = dette P3 connue)
- risk/           risk_engine.validate + sizing (Quarter Kelly) — PRETS mais PAS cables runtime (gele pendant observation)
- dashboard/      render.py (static-gen) + serve.py (serveur stdlib)
- tests/          property-based Hypothesis + smoke

DASHBOARD (couche OBSERVE en lecture seule; toute decision/ecriture reste sur Telegram):
- dashboard/render.py::render() (~ligne 1336, AUCUN argument) lit la DB live et ecrit dashboard/dashboard.html (constante OUTPUT). Sous-fonctions: _positions, _sectors (ticker->narrative via regex `sector_thesis_id:` dans theses.notes), _theses (groupe par tier de CONVICTION, pas par narrative), _concentration, _secteurs, _geo, _signaux, _urgence, _system_state, _journal, _clean_sector.
- dashboard/serve.py: stdlib, 127.0.0.1:8000, regen toutes les 60s, no-store. IMPORTANT: serve.py hot-reload UNIQUEMENT render.py (mtime). Un changement dans shared/* ou intelligence/* exige un restart complet bot+serve. Un changement DB seul s'affiche au Cmd+R (pas besoin d'editer render.py).
- Esthetique "Luminous Dark" via CSS vars sur :root. bg #0E1622, panel #141E2D, ink #E6F1EC, gold #D4AF37, acc #37E0A0, bear #FF6B6B. Fonts: Bricolage Grotesque / Inter Tight / IBM Plex Mono / Orbitron / Noto Sans Runic.

## 4. Schemas DB REELS — LES DOCS MENTENT

CONVENTIONS.md et KPI_DASHBOARD.md decrivent des schemas PERIMES (ils citent claim_json, outcome_json, outcome_evaluated_at qui N'EXISTENT PAS). Verifie TOUJOURS la realite: `sqlite3 data/bot.db ".schema <table>"`. Schemas reels confirmes empiriquement:

- predictions: id, signal_id, ticker, direction(bullish/bearish), horizon_days, baseline_price, baseline_date, target_date, resolved_at, final_price, return_pct, outcome(correct/incorrect/neutral), credibility_delta, created_at, probability_at_creation, brier_score. Ouverte = resolved_at IS NULL.
- signals: id, source_id, timestamp, title, content, summary, score(INT), narratives, entities, sentiment, decay_at, raw_url, gmail_id, user_feedback, echo_cluster_id, signal_type, materiality_boost, impact_magnitude, reversibility, time_to_realization, materiality_breakdown.
- theses: rattachement au narratif via le champ notes contenant `sector_thesis_id: <ID>` (IDs UPPERCASE: AI_COMPUTE_2026, EU_DEFENSE_2026, MAG7_2026...). conviction 1-5. target_partial NULL sur toutes (gap de discipline connu).

## 5. Methode de travail (paste-driven, validee ~40x)

Patch d'un fichier:
1. `cp file file.bak_$(date +%H%M%S)`
2. construire le patch via heredoc a delimiteur QUOTE: `cat > /tmp/patch.py << 'PYEOF'` (le quote rend le corps 100% litteral: backticks, """ , ' passent sans souci)
3. dans le script: `assert s.count(old) == 1` AVANT `path.write_text(...)` (un anchor non-unique ou absent abort le patch et laisse le fichier intact)
4. gates: ruff check --fix; mypy <modules strict>; pytest -q; smoke
5. restart PROPRE: `pkill -9 -f "bot.main"; sleep 5; pgrep -f bot.main` (doit etre vide) puis `python -c "import bot.main"; nohup python -m bot.main > bot.log 2>&1 &; sleep 6; pgrep -fl`. Le pkill gracieux + sleep 3 est INSUFFISANT -> deux pollers -> telegram.error.Conflict.
6. verif 1:1 (Telegram ou dashboard Cmd+R) puis commit atomique.

PIEGES ZSH (le terminal d'Olivier mord souvent):
- Une apostrophe dans un commentaire `#` inline (`qu'il`) ouvre une chaine -> prompt `quote>`. NE METS PAS de commentaire inline avec apostrophe dans un bloc a coller. Idealement aucun commentaire inline.
- Premier caractere d'une ligne collee parfois avale (`sqlite3`->`qlite3`).
- `"...count(*)..."` dont le `"` ouvrant saute -> `(*)` lu comme glob -> `zsh: number expected`. Pour TOUT SQL avec count/parentheses/caracteres speciaux: HEREDOC `<<'SQL'` (immunise).

## 6. Conventions d'ecriture (essence de CONVENTIONS.md)

- Temps interne en UTC; affichage Europe/Paris.
- Tickers UPPERCASE; enums lowercase_snake_case; narratifs snake_case.
- Output TOUJOURS probabiliste, jamais Buy/Sell: prob in [0,1] (JAMAIS en %), conviction 1-5, horizon_days, claim mesurable, invalidation mesurable.
- Erreurs explicites (raise), jamais try/except: pass ni default=0.5 silencieux (lecon tennis-bot).
- Prompts UNIQUEMENT dans shared/prompts.py, versionnes.
- Type hints: adoption graduelle, strict par-module via override mypy dans pyproject.toml. "Type quand tu touches", pas de sweep top-down.
- Backup nomme avant toute modif significative; commit imperatif present, tag de session au close.

## 7. Ou on en est (2026-05-30 soir, post-arc-V2)

Mode observation High Standard. J-11 avant batch resolution 10/06. Portefeuille ~27 positions, ~53k EUR (market value). Univers ~311 tickers (core/watch/extended). Bot tourne PID 84607 + caffeinate, code wire EDGAR chargé (premier test live = cron 8-K demain 6:30).

**Etat session 30/05** : 35 commits, 10 iterations sur l'arc V2 calibration (cf section 8 + decision log #01). 3 posts canoniques bilingues prets dans `posts/`. ADR 012 acte. Tag git `eod-30-05`. 414/414 tests verts.

## 8. LES PIEGES A CONNAITRE ABSOLUMENT (MAJ 30/05)

**Piege #1 — Brier batch 10/06 sera mauvais comme prevu** (acte dry-run iter 10).

Les 40 predictions du batch 10/06 ont ete loggees sous V1 (`estimate_probability` formule cap [0.50, 0.72]) en mai. Toutes dans probabilite [0.608-0.658] = mono-bucket. Dry-run J-11 confirme empiriquement : Brier attendu ~0.295 (PIRE qu'un prior 0.5 trivial = 0.25), accuracy 38%, surconfiant et mal calibre.

A FAIRE le 10/06 a 9h05 (apres le cron `daily_resolve_job` 9h) :
```bash
python -m scripts.post_resolution_brier_report 2026-06-10
```

Le Telegram automatique enverra counts (correct/incorrect/neutral) mais SANS Brier moyen -- d'ou le script standalone. Le post `posts/post_03_dry_run_eleven_days.md` est deja drafte pour publier honnetement le mauvais chiffre (pas de pivot last-minute, c'est l'asset narratif).

**Piege #2 — Le scorer canonique est V2, pas V1** (acte arc 30/05).

`intelligence/signal_scorer_v2.py` est la source de verite des probabilites depuis le 30/05. `shared/math_helpers.estimate_probability` (V1) reste pour rollback A/B SEULEMENT. **NE PAS** la ressusciter comme primary -- elle produit du mono-bucket. Cohortes futures (post 30/05) utilisent V2 via `intelligence.learning.auto_register_predictions` -> `insert_prediction(probability_override=...)`. Enforcement server-side critiques : `evidence in (none, weak) -> watch`, `prob < 0.55 -> watch`, pas de `source_name` dans le prompt (contamine).

**Piege #3 — storage.DB_PATH est l'unique source du path DB** (fix iter 9).

`storage._DB_PATH` est resolu DYNAMIQUEMENT via `__getattr__` module-level -> retourne `storage.DB_PATH` courant. **NE PAS** reintroduire `_DB_PATH = Path(...)` statique. Bug pollution prod connu (tests qui monkeypatch un seul des deux paths laissent l'autre ecrire en prod). Test regression : `tests/test_db_path_alias.py`. Cf CONVENTIONS.md §5.

**Piege #4 — Wire EDGAR primary est FORWARD-ONLY strict** (decision iter 5/7).

`intelligence/edgar_signal_wire.py` insere les 8-K + insider clusters dans `signals` UNIQUEMENT a leur arrivee (via `EightKSource.persist()` et `BuyClusterSource.persist()`). **NE PAS** backfill les 421 lignes historiques (43 8-K + 378 insider snapshots) -- stale-dated predictions = artefact temporel cousin du cluster horizon=30. Forward-only acte dans la memoire `edgar-primary-wired-forward`.

**Piege #5 — ADR 012 : 8-K severity classifier soft-deprecated** (acte 30/05).

`intelligence/filings_8k.classify_severity(item_codes)` ne lit QUE les Item codes, pas le contenu. Il a classe NVDA Q1 FY27 earnings beat en `medium` (le contenu reel sort `strong` via V2). Le classifieur est CONSERVE pour alerting low-latency (Telegram alerts + morning_brief filter rapide) mais **deprecate comme mesure de evidence_strength**. Pour calibration / Brier, source de verite = V2 sur contenu. Si tu modifies l'alerting Telegram, NE PAS te baser sur severity comme proxy de force d'evidence.

## 9. Ce qui vient (a partir du 31/05)

- **Demain 31/05 6:30** : observer `bot.log` apres `scheduled_8k_scan_job`. Si une nouvelle 8-K material est detectee : premier signal V2 dans le ledger reel. Sinon attendre.
- **Demain 31/05 6:20** : observer `scheduled_buy_cluster_scan_job`. Aucun cluster en `insider_buy_clusters_log` actuellement (0 rows) -- le wire sera teste naturellement quand un cluster sera detecte.
- **10/06 9h00** : `daily_resolve_job` cron -> Telegram counts. **9h05** : lancer manuellement `python -m scripts.post_resolution_brier_report 2026-06-10` pour Brier complet. Publier honnetement le mauvais chiffre via post_03.
- **Post-10/06** : observer accumulation cohortes V2 via wire EDGAR. Premiere comparison V1 vs V2 possible quand N V2 suffisant (~aout probable).
- **Path 6 / publication** : differe jusqu'a calibration plot publishable (N V2 >= 50 ideally). Pas le 10/06.
- **Concentration AI Compute** (~75% du book vs cible user_strategy 75%) : at_or_below, OK temporairement, mais a surveiller drift.
- **Wire insider clusters** : code en place, hook actif, mais 0 cluster detecte recemment. Si en 30j toujours 0, debug `scheduled_buy_cluster_scan_job` ou re-tune le seuil `is_buy_cluster`.
- **Tests `slow` marker** : 3 tests reseau-dependants dans `tests/test_edgar_exhibits.py` + 1 dans `tests/test_edgar_signal_wire.py`. Lancer pre-release : `pytest -m slow`. Skipped par defaut.

## 10. Lecons cardinales

- **"La conclusion est toujours en avance d'un cran sur la preuve"** (pattern session 30/05, itere 10 fois) : a chaque "ah j'ai trouve", verifier d'abord revele le vrai bug une couche plus bas. Y compris quand le bug est dans le fix lui-meme (iter 9 alias statique). Le pattern adversaire vaut son cout en commits.
- **Empirical-verify-before-patch** (L13/15) : ne patche jamais sur hypothese; lis le code et la DB reels d'abord.
- **nan est insidieux** : truthy, `nan != nan`, passe `is None`. Garde avec `x != x` ou math.isfinite.
- **"audit green" != audit reel** ; unit-test vert != integration prouvee. Le bug pollution prod 30/05 a ete attrape parce qu'un test FAIL a explose dans la console -- sans ce fail, le code shippait silent-mode.
- **Source credibility != forecast probability** ET ne **PAS** mettre `source_name` dans le prompt de scoring (contamine evidence reading -- iter 3).
- **P(call correct) != P(price up)** : un bearish prob=0.38 est logiquement incoherent (= "je suis 62% sur que bearish est faux"). Enforce `prob >= 0.55 OR direction=watch`.
- **Forward-only strict** sur les wire primary -- backfill = artefact stale-dated qui pollue calibration.
- **Mauvais Brier publie honnetement > maquillage** : si tu sais que le batch va etre mauvais, ecris le post AVANT le moment de verite (cf post_03 deja drafte 11j avant le batch).
- **Savoir s'arreter et banker** (commit + tag + backup + docs refresh) EST de la discipline, pas une faiblesse.
