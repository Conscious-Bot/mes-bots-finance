# AGENT_HANDOFF — Manuel de reprise pour le prochain agent IA

> But: permettre a un agent IA qui ouvre ce repo a froid de reprendre sans rien casser.
> Ordre de lecture: ce fichier -> SESSION_STATE.md (tail) -> PHILOSOPHY.md -> CONVENTIONS.md.
> Derniere maj: 2026-05-23 (day15-brier-dashboard).

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

## 7. Ou on en est (2026-05-23)

Mode observation High Standard. Portefeuille ~21 positions, ~43k EUR. Univers ~178 tickers (core/watch/extended). ~33 theses actives. Narratifs re-taggees ce mois: AI_COMPUTE (~15), EU_DEFENSE (2), MAG7 (2, nouveau bac) + autres. Concentration EXCESSIVE: cluster AI Compute ~80% (cap narratif 30%, 6 lignes > 5%) — decision politique en attente, c'est l'appel d'Olivier.

Le Brier vient d'etre repare a la racine (voir section 8). Dashboard live avec son premier test. risk/ pret mais non cable (gele observation). Crons actifs: resolve 9h, snapshot 23:00, signal_classify 30min, score_pending 1h, gmail 1h, backup 04:00, etc.

## 8. LE PIEGE A CONNAITRE ABSOLUMENT

Jusqu'au 22/05, probability_at_creation = simple snapshot de la credibilite source (~0.5 sur 143/152 predictions) = erreur de categorie (confiance source != P(cet appel correct)) -> Brier vide mais VERT (artefact de la bande neutre +/-5%). Repare le 23/05 par shared/math_helpers.estimate_probability(...) cable dans insert_prediction, MAIS l'effet ne porte que sur les predictions FUTURES (id >= 158).

CONSEQUENCE: les 151 predictions legacy (dont le cluster de 40 qui resout le 10 juin) gardent prob=0.5 et resolveront en Brier vide-mais-vert. NE PUBLIE JAMAIS ce Brier-la comme track record. Le VRAI track record commence aux id >= 158 (prob differenciee), exploitable ~fin juin. ATTENTION recence != qualite: id >= 158 est selectionne par RECENCE, donc domine par les sources Asie Day14+ non-prouvees (cred 0.5). Lire son Brier maturite-source en tete; "commence" n'est pas "valide". Track record > nouveaute. estimate_probability est un PRIOR APPRENABLE, pas une verite calibree: son job est de rendre le Brier informatif/iterable, la vraie calibration viendra de la boucle resolve -> reliability diagram -> ajustement.

## 9. Ce qui vient

- Verifier le fix prob en prod: predictions id >= 158 = integration confirmee. NE PAS conjoindre != 0.5: une prediction post-fix peut calculer 0.50 legitimement (donc ratee par ce filtre), et != 0.5 attrape 8 legacy a 0.53. id 158 = prochaine cree sous le code corrige (max_id etait 157 au restart). Au 23/05: post_fix=0, pas encore tire.
- ~27 mai: 1eres resolutions — verifier final_price sains (pas de nan; garde `px != px` posee dans resolve_due_predictions).
- VUE CALIBRATION (LA surface produit Path 6, le vrai "ameliorer le site"): a batir quand >= 10 predictions a prob differenciee sont resolues (~fin juin). Contenu: reliability diagram (bucket de prob predite vs taux realise) + Brier-over-time + ledger des resolues. Decision a trancher la-bas: neutral exclu du Brier vs binaire-0.5.
- Politique de concentration (EXCESSIVE 80%): decision strategique d'Olivier.
- Logo: parke sur candidat A (heaume-onde), a integrer dans render.py .logo svg + favicon.
- Classifieur 8-K: marque TOUT Item 5.02 = HIGH (bruit qui pollue signal->prediction). Gele pendant l'observation, a recalibrer post-batch.
- Deferred: refactor shared/display.py (symboles devise canoniques), ADR 005 P2 (audit EUR-canonical restant), refactor bot/main.py en handlers/*, push GitHub + CI — VERIFIER que credentials.json/token.json sont gitignores: FAIT le 23/05 (push effectue, secrets client_secret Google + refresh_token verifies hors historique git), prune univers mi-juin.

## 10. Lecons cardinales

- Empirical-verify-before-patch (L13/15): ne patche jamais sur hypothese; lis le code et la DB reels d'abord. La cause-racine du Brier ne s'est revelee qu'en lisant le code, pas les docs (qui mentaient sur le schema).
- nan est insidieux: truthy, `nan != nan`, passe `is None`. Garde avec `x != x` ou math.isfinite.
- "audit green" != audit reel; unit-test vert != integration prouvee. D'ou "verifier la prob en prod demain" et le smoke test render.
- Velocity a depasse la solidification -> gate High Standard avant toute feature. Less surface > more discipline.
- Source credibility != forecast probability (l'erreur exacte du Brier).
- Un prior differencie mais non calibre > une constante 0.5: il rend la metrique testable/iterable.
- Savoir s'arreter et banker (commit + close) EST de la discipline, pas une faiblesse.
