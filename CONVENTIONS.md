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

---

## Type hints policy (added 13 May 2026, Ship 1 closed)

**Adoption**: Gradual. Modules opt-in to strict typing via `pyproject.toml` `[[tool.mypy.overrides]]`.

**Currently strict-typed** (`mypy = 0 errors`):
- `shared/math_helpers.py` — pure math helpers
- `shared/storage.py` — DB access layer (public signatures)
- `shared/llm.py` — LLM cascade wrapper
- `shared/prices.py` — yfinance abstraction
- `shared/notify.py` — Telegram notify
- `shared/config.py` — config + env loader

**Patterns used**:
- Python 3.14 native: `dict[str, Any]`, `list[X]`, `T | None` (not `Optional[T]`)
- `Iterator[T]` for `@contextmanager`-decorated generators
- `cast(T, expr)` for SDK return values (anthropic, json.loads, sqlite Row tuples)
- `# noqa: ARG001` for unused args required by external API contracts (e.g. python-telegram-bot `ctx`)

**Untyped modules** (intelligence/*, data_sources/*, bot/main.py): gradual. When you touch a function in those, add a return type annotation. Don't force a top-down sweep.

**CI gate**: `mypy <typed_files>` runs on every PR via `.github/workflows/ci.yml`. New modules joining the strict-typed list must reach 0 errors before being added to the override.


---

## 16. Detector validation rule (KPI integrity)

**Added 2026-05-14 from postmortem AI #8.** Context: `uptime_monitor.sh` used a
case-sensitive `pgrep -f` pattern that never matched the macOS capital-P
`Python` binary. KPI #1 (uptime > 95 percent) was tied to this broken detector
for 3+ days, accumulating 422 false-negative FAIL entries before discovery.

**Rule**: Any detector backing a KPI must have an independent validation test
at authoring time. Applies to:
- Process detection scripts (pgrep, systemd checks, port scans)
- Cron health checks
- DB-based liveness queries
- LLM cost / error / latency sensors
- Any function whose output feeds a KPI in `KPI_DASHBOARD.md` or `HANDOFF.md`

**Required at authoring time**:
1. Positive case test: detector returns "alive/OK" when the thing IS present/healthy.
2. Negative case test: detector returns "down/FAIL" when the thing is genuinely absent/broken.
3. Both results documented in commit message OR automated via `tests/test_smoke_*.py`
   (preferred for KPI-critical detectors).

**Forbidden**: shipping a KPI whose detector has not been exercised in both
directions. KPI inheritance from an unverified detector = silent metric
breakage with delayed discovery.

**Enforcement gate**: commit message must contain a "Detector validation:
positive=PASS, negative=PASS" line for any change touching a KPI-backing
detector.

## 17. Recon-before-ship rule (sprint scoping)

**Added 2026-05-14 from Day 3 afternoon meta-lesson.** Context: Sprint 1.4
cost enforcement was nearly re-shipped on 2026-05-14 despite being already
implemented Day 2 as "Ship C" (`weekly_cost_summary_job` at `bot/main.py:1173`).
The SESSION_STATE Day 2 afternoon entry stated this explicitly but context
was lost across sessions.

**Rule**: Before scoping any sprint, sub-sprint, or "Ship X" on a named
feature, run two recon commands:

```bash
grep -i "feature_name" SESSION_STATE.md
git log --oneline --grep="feature_name"
```

If either returns prior implementations, **read them first**. Only proceed
with new work after confirming one of:
1. The named feature does not already exist.
2. The existing implementation has a documented gap that the new work fills.

**Forbidden**: scoping or committing on a named feature without running the
two recon commands above.

**Why this matters**: re-implementing existing features = pure dette + drift,
no Path 5/6 value. Each re-implementation also creates two parallel
implementations that drift in subtle ways, multiplying maintenance cost.

**Adjacent reading**: `docs/post-mortems/2026-05-14-uptime-monitor-case-bug.md`
captured this rule in the same session as the detector-validation rule above.
Both stem from the same root cause: confident action without empirical
pre-check.

## 18. Paste-safe bash blocks rule (zsh interactive_comments)

**Added 2026-05-14 evening, meta-lesson 9.** Context: Phase 6b commit + push
+ backup block was paste-rejected on 2026-05-14 with `zsh: parse error near
')'`. Root cause: `interactive_comments` option OFF in user's zsh setup,
so lines starting with `#` were parsed as commands. Comments containing
parens like `# 1. Commit (paste-safe)` triggered subshell parsing on
`(paste-safe)`, failing on the unmatched paren and rejecting the entire
batch. Zero of the 80+ line block executed despite full paste.

This was a recurrence: the same root cause hit on 2026-05-13 morning paste
catastrophe. First occurrence noted informally in SESSION_STATE without
codification. Second occurrence justifies promotion to CONVENTIONS.

**Rule**: Interactive paste blocks for zsh MUST follow one of two patterns:

1. **Preferred — zero `#` comments outside heredocs.** Annotate intent in
   the chat message or in the source file the block modifies. Heredoc
   bodies (`<< 'TAG'` ... `TAG`) are exempt because their content is
   literal, not parsed as zsh.

2. **Fallback — `setopt interactive_comments` as the first line of every
   block**, no exceptions. Less robust because it relies on remembering
   every paste. Still requires `setopt no_bang_hist` alongside to neutralize
   `!` history expansion in the same input.

**Forbidden**: pasting any bash block with `#` comments containing parens,
backticks, semicolons, or shell metacharacters when target shell is zsh
with default options.

**Detection**: if a paste fails with `zsh: parse error near` followed by
any single char from `() {} ; & | < >`, suspect commented metacharacter
as the cause. Recovery = inspect with diagnostic block (git status, file
existence checks) to confirm nothing executed, then retry without comments.

**Adjacent reading**: §16 (detector validation), §17 (recon-before-ship).
Same family — assumptions about default tool/shell behavior that bite at
ship/paste time.


## 19. macOS process targeting (Python.app launcher gotchas)

**Added 2026-05-14 evening from apscheduler-hang-restart-cascade postmortem.**

Two related macOS-specific rules for any code/script targeting a running Python process. Both rules surfaced during a single incident with two cascading violations (21:13 KST + 21:25 KST same evening).

### Rule 1: §16 scope extension — case-insensitive matching applies to ALL process commands

§16 (Detector validation rule) initially covered `pgrep -f` in KPI-backing detectors. This rule **extends** to:
- `pkill -f <pattern>` — same case-sensitive trap as pgrep
- `ps -ef | grep <pattern>` — same trap
- Any process matching against macOS bin paths containing `/Python.app/Contents/MacOS/Python` (capital P)

**Required**: use `-i` flag on `pkill -if`, `pgrep -if`, or `grep -i` for any process matching. Without `-i`, lowercase `python` patterns will not match capital `Python` bins.

**Forbidden**: case-sensitive process matching in any restart, kill, or detection script for production bot operations.

### Rule 2: Python.app launcher PID ≠ interpreter PID

`/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python` is a **launcher app**, not the interpreter directly. When invoked, it forks the actual Python interpreter into a different PID. The launcher may exit shortly after fork, leaving the interpreter orphaned and reparented.

Concrete consequence for `nohup python -m bot.main > bot.log 2>&1 &`:
- bash job `[N]` PID = launcher PID (e.g., 13201)
- Actual interpreter running bot.main = different PID (e.g., 13403), forked child
- `kill %N` or `kill <launcher_pid>` only kills the launcher (often already dead)
- Interpreter PID survives, PPID becomes shell PID after reparent

**Required for cleanup**: kill by interpreter PID discovered via pgrep, not by bash job PID or launcher PID.

Canonical pattern:
pgrep -if "python.*bot.main" | xargs kill -9

Or per-PID loop:
for pid in (pgrep−if"python.∗bot.main");dokill−9"(pgrep -if "python.*bot.main"); do kill -9 "
(pgrep−if"python.∗bot.main");dokill−9"pid"; done

**Forbidden**: `kill %1`, `kill %2`, or kill by bash job PID alone. Always verify via `pgrep -ifl` after kill to confirm interpreter is actually dead.

### Adjacent reading
- §16 (detector validation rule, root of case-sensitivity trap)
- §18 (paste-safe bash blocks, also macOS shell gotcha family)
- `docs/post-mortems/2026-05-14-apscheduler-hang-restart-cascade.md`
- `docs/failure_modes.md` #6 (APScheduler hang runbook)

### Recurrence count
2 violations on 2026-05-14 alone (in single evening):
- 21:13 KST — `pkill -f` case-sensitive failed during first restart attempt
- 21:25 KST — kill by job PID didn't kill interpreter, leaving 13403 alive

Justifies promotion from informal note to codified §19.


---

## Section 16: Gates 5/5 discipline (added Day 9, 17 mai 2026)

Lessons acquired through 3 protocol failures dans Sprint 1 Day 9.
Cette section est non-negotiable - violations = bot crash / KPI undercount /
silent data corruption observees empiriquement.

### Regle 1: Ruff = boolean STOP
Si `ruff check` retourne ANY error (exit != 0), commit STRICTEMENT bloque.
Aucune agregation avec autres gates (import OK, pytest passed, mypy clean
ne sont PAS des exceptions). La gate ruff se lit boolean isole.

Anti-pattern observe Day 9 Sprint 1: shipped commit avec ruff F821 RED
en s'appuyant sur "import OK + pytest 218 passed = good enough" -> bot crash
post-restart (NameError 'datetime' not defined).

### Regle 2: WARN halt upstream
Les WARN dans output de patches scripts (anchor count != 1, conditional
skip silencieux, missing import inference) = HALT signal. Ne pas continuer
aux gates si WARN detected. Investiguer + corriger le patch script avant
runs gates.

Anti-pattern observe Day 9 Sprint 1: ignored WARN "couldn't find anchor
for UTC injection" -> shipped F821 RED -> 2eme ruff failure dans meme sprint.

### Regle 3: Scope match producer
Empirical smoke test DOIT couvrir TOUTES les branches du producer, pas
juste un cas connu. Si fixing un classifier qui handle 5 status types,
tester les 5. Si fixing un formatter qui rend N cas, tester N.

Anti-pattern observe Day 9 Sprint 1: tested only 5 KPI #2 branches dans
smoke beta v1 -> production avait KPI #3-6 avec d'autres emojis (cible/
en_attente) -> Overall count undercount persisted post-fix.

### Regle 4: Carry-forward dette = inline
Si commit message mentionne explicitly "carry-forward dette remains" pour
une issue connexe au fix shipped: per meta-rule "default = option la plus
complete", fixer inline. Reporter cette dette = echec discipline.

Anti-pattern observe Day 9 Sprint 1: commit alpha v1 explicitly noted
"timezone consistency dette remains - separate carry-forward" et shipped
quand meme -> uptime "-2h 7min" negative empirically -> alpha2 closure
forcee meme sprint.

### Regle 5: Conditional patch logic risk
Heuristics dans patching scripts (`if X not in content[:1000]`) = misfire
risk silencieux. Preferer EXPLICIT anchors + asserts. Si l'anchor n'est
pas trouvable, l'erreur doit etre bruyante (assert fail), pas silencieuse
(skip + WARN).

Anti-pattern observe Day 9 Sprint 1: heuristic UTC injection failed
silently because content slice didn't match expected pattern -> WARN logged
but execution continued -> patches referenced unbound UTC -> ruff F821.

### Regle 6: Transcript compaction = duplicate commit risk
Sur reopen post-transcript-compaction, ALWAYS run `git log -5` +
`git rev-parse --verify <tag>` AVANT toute action de closure proposee.
Tag/commit du jour existe deja -> diagnostic first, action ensuite.

Anti-pattern observe Day 8 closure: duplicate Day 8 close commit shipped
because pre-compaction commit not visible in active context -> force-reset
+ force-push recovery.

### Regle 7: Bash inline # = path separator (zsh)
zsh `interactive_comments` not active inline. `git log A..HEAD # comment`
-> "fatal: ambiguous argument '#': unknown revision or path". Use `;`
separator or `||true` continuation, JAMAIS inline comment dans bash bloc.

Anti-pattern observe Day 8/9 multiple times: inline `#` comments breaking
diagnostic outputs.

### Regle 8: Channel verification before bug assumption
Avant de conclure "X est silencieux donc X est broken", verifier TOUS
les channels potentiels :
- bot.log (file-based logging)
- data/bot.db (DB-persisted telemetry / events / calls tables)
- data/bot_state.json (state-based heartbeats)
- in-memory caches

Bot finance utilise au moins 3 channels distincts. Telemetry middleware
ecrit en DB (handler_calls table 155 rows), PAS dans bot.log (by design,
avoid spam). Si tu vois bot.log silent + /health "last handler call @
T+recent", c'est NORMAL : telemetry DB-side fonctionne.

Anti-pattern observe Day 9 morning diagnostic : `grep "cmd_|update_id"
bot.log` returns nothing -> conclusion hative "telemetry broken" -> false
positive inscrit dans HANDOFF carry-forward Day 10. Corrige soiree Day 9 :
empirique handler_calls table 155 rows, /handler_stats Pareto working
end-to-end, top-10 handlers concentrent 60% des calls.

Discipline : checker DB tables relevantes AVANT d'inscrire un "X silent"
en carry-forward.


### Regle 8 addendum: mypy "unused section(s)" warning is contextual

Si mypy reporte `note: unused section(s): module = [...]` lors d'une
invocation single-file (e.g. `mypy shared/portfolio_metrics.py`), c'est
NORMAL : mypy signale les modules dans override list qui ne sont PAS
checks dans cette invocation. Pas une ghost entry, pas une dette technique.

Anti-pattern observe Day 9 audit : interpreter le warning comme presence
de modules fantomes dans override. Cross-reference empirique requise :

```python
import tomllib
from pathlib import Path
with open('pyproject.toml','rb') as f:
    cfg = tomllib.load(f)
mods = [m for o in cfg['tool']['mypy']['overrides'] for m in o.get('module',[])]
ghosts = [m for m in mods if not Path(m.replace('.','/') + '.py').exists()]
```

Audit Day 9 P3 closing : 31 modules override, 0 ghosts confirme override
list propre. Warning mypy contextuel only - safe to ignore lors de
single-file invocations.


### Regle 9: Helper deduplication discipline (grep before defining)

Avant de definir N'IMPORTE QUEL nouveau helper / utility / fonction
partagee, grep pour variants existants :

```bash
grep -rn "def helper_name\|def similar_name" --include="*.py" .
```

Anti-pattern observe Day 9 Ship V H3 (Phase A retracted) : ajout de
`escape_markdown` dans `shared/display.py` sans grep prealable. Decouvert
Phase B que `bot/handlers/_common.py:telegram_safe` existait deja avec
couverture PLUS complete (5 chars vs 2). Duplicate function = silent
debt + future audit regression risk.

Discipline : chercher au-dela du naming evident. Multiple aliases possibles:
- escape_markdown / escape_md / md_escape / markdown_escape
- telegram_safe / tg_safe / md_safe / sanitize
- format_safe

Si audit trouve une utility existante : etendre (si besoin), pas duplicate.
Si usage pattern differe significativement : rationale explicite dans
docstring + cross-reference vers l'existante.

Audit Day 9 P3 Ship V : 0 nouveau helper ajoute, 2 inline escapes refactores
vers `telegram_safe` existant dans `bot/handlers/_common.py`. Cosmetic +
defensive (couverture 5 chars vs ad-hoc 1 char per site).


### Regle 10: Telegram MarkdownV1 backslash escape NOT consumed inside *bold*

Empirical observation Day 9 Ship V Phase D :

- PLAIN context : source `text\_word` -> Telegram render `text_word` (backslash escape consume)
- BOLD context : source `*text\_word*` -> Telegram render `text\_word` (backslash literal visible)

Telegram MarkdownV1 parser ne consomme le backslash escape qu'en plain
context. Inside `*bold*` ou `_italic_`, backslash render literal.

Discipline pour dynamic content avec potential `_` chars destine a contexte
emphasis :

1. **Drop emphasis** : plain text label sans `*` ni `_` wrap.
   Mid-word `_` (entre 2 letters) n'est pas italic-triggered en MarkdownV1.
2. **HTML parse_mode** : `parse_mode="HTML"` avec `<b>...</b>`.
   HTML escape `&lt; &amp;` only, supports nested formatting cleanly.
3. **MarkdownV2** : explicit escape complet mais spec stricte + verbeux.

Anti-pattern observe Day 9 zeta : `narrative.replace("_", "\\_")` +
`*narrative*` wrap shipped sans visual empirical verify in bold context.
Bug ne render correctement qu'en Ship V Phase D correction (24h later).

Lesson : empirical retest DOIT inclure visual diff du rendu rendu Telegram,
pas seulement "command returns without crash". Section 16 Regle 3 scope
match producer = tester rendering paths reels, pas juste code paths.

Audit Day 9 Ship V Phase D : /portfolio_narratives bold dropped, telegram_safe
maintenu defensive plain context. Mid-word `_` literal sans backslash.

### Regle 11 — Cross-config drift on AST extraction

Context: when extracting a function from a file inside `[tool.ruff.lint.per-file-ignores]` zone (ex `bot/main.py = ["ARG001"]`) to a file outside that zone (ex `bot/handlers/*` no ignore), the silent per-file-ignore safety net disappears at the destination.

Day 10 E batch 1 manifestation: cmd_ping/cmd_help/cmd_insiders extracted from bot/main.py (ARG001 ignored) to system.py + signals_filings.py (no ignore) → 4× ruff ARG001 + 2× mypy union-attr fired at first gate (annotations `update: Update` + `ctx: ContextTypes.DEFAULT_TYPE` triggered Message|None strict check + unused-arg flag).

Rule: before extraction, audit `[tool.ruff.lint.per-file-ignores]` + target convention. Normalize at extraction time:
- Strip type annotations on update/ctx if target convention is untyped (bot/handlers/* convention)
- Add inline `# noqa: ARG001` for unused ctx
- Remove orphaned imports (`from telegram import Update`, `ContextTypes`) if no longer referenced

Extension of R3 (scope match producer): per-file-ignore is part of the function's effective scope. Moving the function moves it out of that scope; destination must replicate equivalent silence (inline noqa) or be brought to convention.

Implementation note for batches E2/E3/E4: AST extraction script must include annotation-stripping + noqa injection BEFORE first gate run.

### R13 — pkill/ps macOS Python case-sensitive (Day 10 17/05/2026)

`pkill -f "python.*"` ne match pas le binaire macOS framework `Python` (capital P). Toujours utiliser `pkill -9 -if "python..."` ou pattern `[Pp]ython` pour kill bot.main de façon fiable. Idem pour ps/grep de vérif post-kill. Voir docs/failure_modes.md FM-7.

### R14 — AST extraction "name exists" check : assignment regex obligatoire

Quand un script AST/regex vérifie si un nom (constante, variable, fonction) existe au niveau module, JAMAIS utiliser `if 'NAME' in src` (substring match) — toujours regex assignment :

```pythonre.search(r'^NAME\s*=', src, re.MULTILINE)

Pourquoi : le nom apparaît aussi comme référence dans les corps de fonction. Substring match retourne True → script skip l'insertion → bug silencieux jusqu'à utilisation runtime.

**Source** : Day 10 17/05/2026 batch 2+3 fixup #2 (CALENDAR_REFRESH_TICKERS skippé parce que cron L364 contenait le nom comme référence). Coût ~30min + 1 fixup commit en plus.

### R15 — Heredocs zsh : `#` début de ligne = `command not found`

Les lignes commençant par `#` à l'intérieur d'un heredoc Python `<< 'PYEOF' ... PYEOF` sont OK (commentaires Python), mais hors heredoc dans le même bloc bash zsh interprète `#` comme commande inexistante → `zsh: command not found: #`.

Fix : `: # comment` (no-op builtin) ou strip les commentaires hors heredoc Python.

**Source** : Day 10 17/05/2026, 2 occurrences dans le bash clean-kill.

### R16 — Diagnostic discipline : symptôme persistant après "fix" = STOP forensics

Quand une cleanup/restart cycle produit le même symptôme N fois consécutives malgré des "fixes" appliqués entre temps :

1. **STOP** d'appliquer des fixes
2. **STOP** d'escalader le même pattern (kill plus fort, wait plus long, regen plus de tokens)
3. **PIVOT** vers forensic deep-dive : lsof, ps -ax broad pattern, file descriptors
4. Le root cause est presque toujours invisible à l'outil de diagnostic primaire (FM-7 = pgrep ment, FM-8 = ps grep ment)

**Anti-pattern observé Day 10** : 10 restart attempts cascade → 10 zombies accumulés → cascade Conflicts → hypothèse "Telegram retry" sans verif lsof → ~2h perdues. Le 1er restart qui Conflict après "kill" aurait dû déclencher `lsof bot.log` immédiatement, pas un 2ème restart.

**Source** : Day 10 17/05/2026.

### R17 — Claude diagnostic priority : forensic before solution

Pour Claude opérant sur ce projet : quand l'user reporte un symptôme persistant matching un anti-pattern connu (Conflict cascade, ghost process, état contradictoire), le first move est **TOUJOURS** une commande de forensics (lsof, broad ps, network state), JAMAIS une "solution" supposée (regen, restart, retry).

Erreur Day 10 : Claude a suggéré token regen #1 comme "solution" Conflict → user a exécuté (BotFather workflow + .env update) → symptôme inchangé → preuve que diagnostic était faux. Le bon move était `lsof bot.log` au premier Conflict cascade observé.

Règle : 1ère réponse à un symptôme "weird operational" = forensic command + paste output. PAS hypothèse + fix avant données empiriques.

**Source** : Day 10 17/05/2026 mea culpa Claude.
