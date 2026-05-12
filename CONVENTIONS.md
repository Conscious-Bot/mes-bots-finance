# CONVENTIONS — Ligne de conduite technique

Document de reference pour l'ecriture du code et des donnees du bot.
A consulter avant toute decision d'implementation pour rester coherent.

---

## 1. Time & timezone

- Interne : tout en UTC (ISO 8601 avec offset, ex 2026-05-11T07:00:00+02:00)
- Affichage Telegram : Europe/Paris, format DD/MM HH:MM
- Jamais de datetime.now() sans timezone explicite

## 2. Tickers, enums, identifiants

- Tickers : toujours UPPERCASE (NVDA, jamais nvda ou Nvda)
- Enums : lowercase_snake_case (risk_on, paper_only, bullish)
- Narratifs : snake_case (AI_infra, semi_cycle, comme dans config.yaml)
- IDs DB : integer auto-increment, jamais UUID
- Status these : active | invalidated | realized | stale
- Direction these : long | short | watch
- Sentiment signal : bullish | bearish | neutral

## 3. JSON dans colonnes TEXT (SQLite)

Schemas canoniques figes.

claim_json (predictions) :
- direction : long | short | watch
- target_price : float ou null
- prob : float entre 0 et 1
- conviction : int 1 a 5
- drivers : liste de strings
- horizon_days : int

outcome_json (predictions) :
- measured_at : ISO timestamp
- price_at_entry : float
- price_at_horizon : float
- pct_move : float
- max_drawdown_pct : float
- target_hit : bool
- summary : phrase courte

metadata (analyses) :
- scores : dict {quality, growth, profitability, valuation, risk, momentum, macro_alignment} chacun 0-100
- regime_at_time : risk_on | risk_off | transition | crisis
- narratives_active : liste

Regle : JSON toujours sorted keys, pas de trailing newline.

## 4. Probabilistic output canonique

Jamais Buy ou Sell. Toujours :
- prob : 0.X (entre 0 et 1, JAMAIS en pourcentage stocke)
- conviction : 1-5 (cognitivement simple)
- horizon_days : N
- claim : phrase mesurable
- invalidation : phrase mesurable
- drivers : 2-5 bullets

## 5. Acces aux ressources externes

Une seule passerelle par ressource :
- DB SQLite -> toujours via shared/storage.py
- LLM Anthropic -> toujours via shared/llm.py
- Telegram -> toujours via shared/notify.py
- Config + env -> toujours via shared/config.py

Si on voit import sqlite3 ailleurs que dans storage.py, c'est un bug architectural.

## 6. Erreurs explicites, jamais silencieuses

- raise MissingDataError si donnee requise absente
- raise ConfigurationError si config invalide
- Jamais try/except: pass ni default=0.5 silencieux (lecon tennis-bot)
- Bot continue apres erreurs module-level, mais loggue clairement

## 7. Logging structure

Format unifie : timestamp level module: action context

Niveaux :
- DEBUG : verbeux, dev only
- INFO : flow normal
- WARN : anomalie recuperee
- ERROR : echec module
- CRITICAL : systeme inutilisable

Jamais logger les secrets.

## 8. Telegram output canonique

- Markdown leger, un seul asterisque pour gras
- Header avec emoji + titre
- Sections separees par ligne vide
- Sources citees inline entre parentheses
- Toujours probabiliste, jamais binaire

## 9. Naming files & modules

- Python : snake_case.py
- Docs racine : UPPERCASE.md
- Crons : action_target.sh
- Backups : {file}.backup_avant_{action}_{YYYYMMDD}
- Folders : snake_case/

## 10. Prompts dans shared/prompts.py UNIQUEMENT

Aucun prompt en dur dans un module fonctionnel.

Structure : ROLE -> CONTEXT -> INPUT -> TASK -> CONSTRAINTS -> OUTPUT FORMAT

Toujours :
- Output format explicite
- Clause si tu n'es pas sur, dis-le
- Cite sources si presentes en input
- Force probabilistic output

## 11. Module Python : structure canonique

Ordre imports : stdlib -> third party -> local, separes par ligne vide.

Module doit avoir :
- docstring en tete (purpose + main exports)
- imports groupes
- constants UPPER_CASE
- functions/classes
- bloc if __name__ == __main__ optionnel pour tests inline

## 12. Git / backup discipline

Pas de Git en Phase 1. Quand introduit :
- Commit subject : imperatif present, max 72 chars
- Tag de phase : [P2] Add thesis revisit logic
- Backup tar avant chaque migration de phase

Toujours :
- Backup nomme avant modification significative
- Backup quotidien automatise via cron

## 13. Versioning des prompts

Chaque prompt avec version tag :
- SIGNAL_SCORER (alias vers derniere version)
- SIGNAL_SCORER_V1, V2, V3 (historique)

Permet tracking et A/B test.

## 14. Conviction inflation watch

Si plus de 20% des theses actives ont conviction 5 -> inflation cognitive.
Bot alerte mensuellement.

## 15. Module deprecation policy

Avant suppression de code :
1. Marquer DEPRECATED dans docstring + date + raison
2. Logger warning si encore appele
3. Garder 1 mois minimum
4. Backup avant suppression definitive

---

## Resume executable

Checklist avant tout commit / patch :

1. Times en UTC interne ?
2. Tickers UPPERCASE ?
3. JSON suit le schema canonique ?
4. Output probabilistic ?
5. Acces externe via passerelle dediee ?
6. Erreurs explicites ?
7. Logging structure ?
8. Telegram format canonique ?
9. Naming conforme ?
10. Prompts dans prompts.py uniquement ?
11. Structure module standard ?
12. Backup avant patch significatif ?
13. Prompts versionnes ?

Si une case ne coche pas -> stop, ajuste, puis commit.
