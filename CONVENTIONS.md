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

Passerelles dediees :
- LLM Anthropic -> toujours via shared/llm.py
- Telegram -> toujours via shared/notify.py
- Config + env -> toujours via shared/config.py

DB SQLite : architecture par OWNERSHIP, pas passerelle unique.
- Tables coeur (theses, predictions, signals, sources, calibration, patterns) : INSERT via shared/storage.py ; certaines MAJ (UPDATE) par les modules-domaine ci-dessous.
- Modules-domaine possedant les writes de LEUR table : shared/positions.py (positions/position_events), shared/ticker_names.py (cache), shared/llm.py (llm_calls), intelligence/{price_monitor,materiality_v2,debt_monitor,insider_digest,analyze}.py (leur output), bot/main.py (handler_calls), bot/handlers/misc.py (edition champs these).
- Acces via le helper instrumente query() (sql_observability) avec tag, pour l'observabilite.
- Surface GELEE et testee : tests/test_db_write_discipline.py echoue si un nouveau module ecrit en DB hors allowlist. Ajouter un writer = acte conscient (route via storage.py, ou etend l'allowlist avec justification).

Propriete auditable : "qui peut muter la DB" est explicite et verifie, pas une promesse de single-gateway que le code dement.

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

**Currently strict-typed** (`mypy = 0 errors`, source of truth = `pyproject.toml` `[[tool.mypy.overrides]]`):

The override list is canonical. CONVENTIONS.md is documentation only.
When adding a module to strict mode, edit `pyproject.toml` first, then
update this list to match.

shared layer:
- `shared/display.py` — Currency + format helpers
- `shared/math_helpers.py` — pure math (clamp_credibility, brier_score)
- `shared/storage.py` — DB access layer
- `shared/llm.py` — LLM cascade wrapper
- `shared/prices.py` — yfinance abstraction
- `shared/notify.py` — Telegram notify
- `shared/config.py` — config + env loader
- `shared/positions.py` — position book + journal
- `shared/sql_observability.py` — query wrapper with telemetry
- `shared/edgar.py` — SEC EDGAR API
- `shared/crypto.py` — crypto price helpers
- `shared/echo.py` — BGE embeddings echo clusters
- `shared/embeddings.py` — BGE-small wrapper
- `shared/macro.py` — FRED macro data
- `shared/data_source_base.py` — common ingestion interface
- `shared/uptime.py` — heartbeat
- `shared/portfolio_metrics.py` — position-level metrics

intelligence layer:
- `intelligence/learning.py` — outcome resolution + credibility update
- `intelligence/materiality_v2.py` — composite materiality rubric
- `intelligence/asymmetry.py` — long/short asymmetry verdict
- `intelligence/digest.py` — twice-daily synthesis
- `intelligence/journal.py` — decision journal auto-resolve
- `intelligence/credibility.py` — source credibility ledger
- `intelligence/insider_digest.py` — Form 4 insider activity
- `intelligence/price_monitor.py` — thesis threshold trigger cron
- `intelligence/bias_tagger.py` — auto bias tagging
- `intelligence/signal_classify.py` — Haiku signal_type
- `intelligence/materiality_boost.py` — promotion logic
- `intelligence/half_life.py` — decay
- `intelligence/regime.py` — risk_on/off classifier
- `intelligence/calendar.py` — macro/earnings calendar
- `intelligence/analyze.py` — /analyze deep fiche
- `intelligence/thesis.py` — thesis tracker

bot layer:
- `bot/handlers/positions.py` — position handlers (Day 12 Step C)

data_sources layer:
- `data_sources/gmail_.py` — newsletter ingestion

risk layer:
- `risk/risk_engine.py` — pre-trade validate
- `risk/sizing.py` — Quarter Kelly + hard cap

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
for pid in $(pgrep -if "python.*bot.main"); do kill -9 "$pid"; done
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

### R18 — Bash shipping code DOIT gate-abort sur RED

Tout bash qui (a) modifie du code source ET (b) git commit ce code dans la même séquence DOIT inclure un mécanisme d'abort si une gate échoue. Sinon le commit passe malgré des erreurs visibles dans le output → broken code in git.

Patterns acceptables :
- `set -e` au début du bash (toutes commandes abort sur exit != 0)
- `command || { echo "X FAILED"; exit 1; }` après chaque gate critique
- Test pytest avec `$?` capture explicite avant le `git commit`

Anti-pattern observé Day 11 (item A kpi6 SMH) : 4 ruff errors + 1 mypy error + 7 pytest failures dans output → commit a quand même tourné car séquence linéaire sans abort → commit 7f7bb7d shipped broken. Fix forward même session, mais discipline aurait évité.

**Lien R14** : R18 protège quand R14 (et autres règles de patching) échouent. Defense in depth.

**Source** : Day 11 17/05/2026 (item A SMH benchmark).


## R19 — Explicit pytest/mypy/ruff gate pattern (Day 11, FM-9 mitigation)

**Rule**: Shipping bash MUST use explicit exit-code capture for every gate
that decides whether to commit/push. NEVER rely on `set -eo pipefail` to
abort on a `cmd 2>&1 | tail -N` pipeline inside a subshell wrapped in
`|| echo`.

**Empirical motivation**: Day 11 saw 2 R18 self-violations (commits 7f7bb7d
and f2b23fe) where the previous pattern silently allowed broken commits.
Root cause: see docs/failure_modes.md FM-9.

**Required pattern**:
```bash
pytest -q > /tmp/pt 2>&1 && rc=0 || rc=$?
if [ "$rc" -ne 0 ]; then
  tail -15 /tmp/pt
  echo "===== ABORT — R19 gate triggered ====="
  exit 1
fi
echo "  pytest GREEN: $(tail -1 /tmp/pt)"
```

**Forbidden patterns** (proven unreliable in zsh):
- `pytest -q 2>&1 | tail -3` followed by `git commit` (pipe-to-tail masks exit)
- `mypy ... 2>&1 | tail -3` followed by `git commit` (same)
- `ruff check . 2>&1 | tail -3` followed by `git commit` (same)

**`grep -c` counting gotcha** (related — `grep -c` returns exit 1 + stdout 0
when no matches):
```bash
# BAD: || echo 0 appends a SECOND "0" → err_count = "0\n0" → [ test fails
err_count=$(grep -cE 'error:' /tmp/mypy || echo 0)

# GOOD: || true preserves stdout "0" without appending
err_count=$(grep -cE 'error:' /tmp/mypy 2>/dev/null || true)
```

**Scope**: every shipping bash containing `git commit` / `git push` / any
file mutation past a quality gate.


## R20 — Display-layer forensic before display-affecting refactor (Day 11, ADR 004 audit)

**Rule**: Before refactoring ANY handler that calls a centralized formatter
(`format_finance`, `format_position_line`, `format_aggregate_line`,
`format_brief_position_line`, `format_money`, `format_pct`, `format_billing`,
`format_pnl_pct`), VIEW the formatter source FIRST. Identify:
- Hardcoded canonical constants (e.g. CANONICAL_FINANCE, CANONICAL_BILLING)
- Symbol/format logic embedded in shared module
- Architectural invariants in module docstring

**Empirical motivation**: Day 11 ADR 004 Batches 4A/4B passed USD-converted
values through `format_finance` (CANONICAL_FINANCE=EUR). Would render
`€{USD_value}` on restart = symbol/magnitude mismatch. Caught by forensic
audit before bot restart. Damage contained to repo.

**Required workflow**:
1. Forensic view of formatter source code + docstring + canonical constants
2. Identify architectural assumptions (currency invariants, type contracts)
3. Design patch to RESPECT architecture (add kwarg, migrate constants, etc.)
4. If architecture is wrong shape for refactor: codify in ADR amendment first

**Scope**: any commit touching user-visible display strings via centralized
formatters. Applies to currency, percentages, dates, billing.


## R19 v3 — Ruff gate mandatory + R14 v2 reinforcement (Day 12 Step 1.5 lesson)

**R19 v3 — extension of R19 v2**: ruff gate MUST be added to every shipping
bash alongside pytest + mypy gates. Day 12 Step 1 commit 4ceb084 landed with
3 ruff errors unresolved because R19 v2 only gated pytest + mypy. Day 12
Step 1.5 retrofit attempt was correctly aborted by R19 v3 ruff gate on
4 RUF002 errors before commit could land.

**Required pattern (add alongside R19 v2 gates)**:
```bash
ruff check <files> > /tmp/ruff 2>&1 && ruff_rc=0 || ruff_rc=$?
if [ "$ruff_rc" -ne 0 ]; then
  cat /tmp/ruff
  echo "===== ABORT — ruff gate ====="
  exit 1
fi
echo "  ruff GREEN"
```

Order in bash: ruff -> pytest -> mypy (cheapest first, catches lint + syntax
+ auto-fixable issues earliest).

**R14 v2 — function-scoped AST checks**: when applying SEQUENTIAL pattern-replace
patches across multiple sibling functions in the SAME file in the SAME bash run,
"already patched" substring `in src` checks are CONTAMINATED by earlier
patches.

Day 12 Step 1 example: step 2 added `format_finance(market_value, decimals=0,
width=6, currency=currency)` inside format_position_line. Step 3's check
`'format_finance(market_value, decimals=0, width=6, currency=currency)' in src`
returned True from step 2's edit -> step 3 incorrectly skipped patching
format_aggregate_line (silent substring contamination by sibling function in
same file).

**Required pattern**: use AST function-scoped detection, NOT global `in src`:
```python
tree = ast.parse(src)
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == target_fn:
        body = '\n'.join(src.splitlines()[node.lineno-1:node.end_lineno])
        if marker_text in body:
            already_patched = True
        break
```

**Scope**: any sequential multi-function patch in same file. AST function-
scoped extraction mandatory for both "already patched" checks AND for the
patch itself when matching needs to be precise (line-range replacement).


## R19 v4 — Semantic completeness gate (Day 12 Step 2A lesson)

**Rule extension of R19 v3**: when applying a batch of N pattern-replace
patches across one or more files, MUST verify N transformations actually
occurred via AST function-scoped marker count BEFORE commit. Syntactic gates
(ruff + pytest + mypy from R19 v2/v3) only catch breakage from APPLIED
patches, NOT missed-pattern silent failures.

**Empirical motivation**: Day 12 Step 2A commit a9c3adf landed with 3 of 4
portfolio_views.py patches MISSED due to pattern mismatch (file uses emoji
literal chars 📊/🎯 while pattern expected \\U escape form from forensic
dump). 'WARNING: pattern not matched' messages were visible but bash did
NOT abort. Syntactic gates passed because unchanged source remains valid
Python. Display would render '\u20ac{USD_value}' on bot restart for sectors
header + format_aggregate_line + narratives header (partial USD migration).

**Required pattern (after batch of patches, before commit)**:
```python
expectations = {
    'function_name_1': expected_marker_count,
    'function_name_2': expected_marker_count,
    'function_intentionally_not_patched': 0,  # explicit declaration
}
failures = []
tree = ast.parse(src)
for fn, expected in expectations.items():
    found = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn:
            body = '\n'.join(src.splitlines()[node.lineno-1:node.end_lineno])
            actual = body.count(MARKER)
            if actual != expected:
                failures.append(f"{fn}: expected {expected}, got {actual}")
            found = True
            break
    if not found:
        failures.append(f"{fn}: not found")
if failures:
    raise SystemExit(1)
```

**Scope**: any bash applying batch of pattern-replace patches where missed
patches would cause semantic regression (display, behavior, output). Explicit
`expected_count` per function — functions intentionally NOT patched get
explicit 0 as DECLARATION of intent (not silent default).

**R19 stack complete**:
- R19 v2: pytest + mypy via explicit gate (FM-9 mitigation)
- R19 v3: ruff added to v2 (Step 1.5 lesson)
- R19 v4: AST function-scoped marker count (Step 2A lesson)

All gates explicit, none relies on subshell pipefail. Bash shipping discipline
solid.

**Pattern-mismatch lesson (paired with R19 v4)**: when source file may use
emoji/unicode literals (chars like 📊 🎯) instead of \\U escape form, derive
the patch pattern from LIVE-READ file content via Path.read_text + split,
not from heredoc-encoded escape strings. Forensic dumps via terminal may
show one form while file source has another.


## R19 v5 — Explicit rc check for ALL commands (Day 12 FM-12 lesson)

**Rule extension**: R19 stack (v2 pytest+mypy, v3 ruff, v4 AST semantic) uses
explicit `cmd && rc=0 || rc=$?` + `[ $rc -ne 0 ] && exit 1` pattern for EVERY
discipline-critical command, including python3 heredocs. zsh `set -e` does
NOT reliably propagate failures from heredoc commands in subshells (FM-12).

**Required pattern**:
```bash
cmd > /tmp/out 2>&1 && rc=0 || rc=$?
if [ "$rc" -ne 0 ]; then
    cat /tmp/out
    echo "===== ABORT — context (rc=$rc) ====="
    exit 1
fi
```

Applied to:
- ruff / pytest / mypy gates (R19 v2/v3)
- python3 heredoc patches (R19 v5 NEW)
- python3 heredoc semantic gates including R19 v4 itself (R19 v5)
- git commit / push if their failure should abort downstream

**Anti-pattern**: relying on `set -eo pipefail` alone in zsh subshell.

**R19 stack final**:
- v2: pytest + mypy explicit rc check (FM-9 mitigation)
- v3: ruff added
- v4: AST function-scoped marker count (semantic completeness)
- v5: explicit rc check applied to ALL commands incl. python3 heredocs (FM-12 mitigation)

The disciplined bash pattern: NO bare command with reliance on set -e in zsh
subshell. Every command captures rc, checks, aborts explicitly.

### Lesson 12 (Day 13 — R19 v5 explicit rc gate mandatory)

Gate commands (`ruff`, `pytest`, `mypy`) MUST be wrapped in explicit rc check:

```bash
ruff check . || { echo "RUFF FAIL"; exit 1; }
pytest -q || { echo "PYTEST FAIL"; exit 1; }
```

Plain `ruff check .` allows gate failure to be silently absorbed by command chains, propagating broken code to commit/push.

**Incident** (commit d4925b3, 2026-05-19): Shipped P0 v1 with F821 (`get_conn` undefined). Bash sequence wrote bare `ruff check .` without rc gate. Ruff flagged error in stdout but subsequent commands continued; commit landed broken. Required emergency fix c7e5ed0.

### Lesson 13 (Day 13 — schema empirical verification before queries)

Before writing SQL referencing a column, verify schema empirically:

```bash
sqlite3 data/bot.db ".schema <table>"
```

**Incident** (commit d4925b3, 2026-05-19): Wrote `SELECT s.materiality_v2, src.tier FROM signals JOIN sources` — neither column existed. Reality: `signals` has `score INTEGER` + `materiality_boost REAL` (decomposed v2); `sources` has `credibility REAL` only (tier dynamically derived: S ≥ 0.7 / A ≥ 0.5 / B ≥ 0.3). Cost: emergency fix e29a887. Same anti-pattern as Lesson 12.

### Lesson 14 (Day 13 — macOS process discovery requires `-i`)

macOS Python framework executable is **`Python`** (capital P) at `/Library/Frameworks/Python.framework/.../MacOS/Python`. `pgrep -f "python.*bot.main"` is case-sensitive by default → **silently misses macOS Python processes**. Always use `pgrep -fil` / `pkill -fi`.

**Incident** (Day 13, 2026-05-19): PID 55387 zombie since 2026-05-04 (15 days) caused persistent Telegram `getUpdates` Conflict. 4 simultaneous bot instances accumulated; every `pkill -f` since Day 5 was a silent no-op. WAL integrity protected DB (125 signals = 125 distinct gmail_ids audited clean). `PROCEDURE_URGENCE.md` Scenario 1 patched.

Empirical:
```bash
pgrep -fl "python.*bot.main"    # macOS: NOTHING (case-sensitive miss)
pgrep -fil "python.*bot.main"   # macOS: all bot instances
```


### Lesson 15 (Day 13-14 — empirical verification applies beyond SQL)

Storage convention claims in comments are documentation of *intent at time of writing*; the actual storage IS what storage IS. When auditing a system claim, derive truth from **data**, not from **text**. The Lesson 13 SQL-schema pattern generalizes to ANY structural assumption: function signatures, storage layouts, return shapes, currency conventions.

**Incident** (Day 13-14 audit, commits `1cefee6` + `b601bfd` + `8e345c2`): Day 11 ADR 004 Batch 4A inline comments asserted `positions.avg_cost` stored in NATIVE currency (JPY for `.T`, KRW for `.KS`, etc.). Actual broker import path (`legacy_import_2026_05_15`) stored EUR canonical for all 21 positions. Mismatch caused cascading bugs: morning_brief SK hynix display $0.76 (actual: $1,216), KPI #6 entry deflation -4.12% bullshit (actual currency-coherent: -4.05%). Discovery required cross-currency ratio audit on real DB rows. See `docs/adrs/005-eur-canonical-positions.md`.

**Empirical tooling pattern** (verified Day 14, generalizable):
```python
# Cross-currency ratio audit for storage convention
from shared.prices import get_current_price_in
for ticker, _qty, stored_value in db_rows:
    pe = get_current_price_in(ticker, "EUR")
    ratio = stored_value / pe
    # All ratios ~1.0 across native currencies → EUR canonical
    # Ratios cluster on native_fx_to_EUR rates  → NATIVE canonical
    # Mixed cluster                             → dette empirical, per-row audit
```

**Trigger**: any time you read a comment that asserts a data convention (storage unit, currency, semantic shape) before modifying logic that depends on it. Failure-mode signature: tests pass because they encode the same aspirational assumption as the code (Day 13 `test_fallback_currency_aware_*` encoded the same broken NATIVE assumption — both broken in sync). Property-based tests on real DB data, not mocked, detect this.

### Lesson 16 (Day 14 — heredoc-in-heredoc double-escape diligence)

When a bash heredoc invokes Python which writes Python code to a file, escape sequences pass through TWO interpretation layers:

1. The outer heredoc Python parses its own source. Inside a triple-quoted string, `\\n` collapses to `\n` (two chars: backslash + n). A bare `\n` collapses to a literal newline char inside the string — which then ends up in the output file as an actual line break inside a quote pair, producing invalid Python syntax.
2. The output file's Python parses the literal text. `"\n"` (2 chars) is interpreted as a newline at runtime.

**Incident** (Bash 66-67, Day 14 evening): Heredoc patch contained `messages.append("\n".join(msg_lines))` intended as a join on newlines. The outer Python heredoc collapsed `\n` to a literal newline, writing a multi-line broken string literal to `intelligence/debt_monitor.py`. Ruff caught 11 cascading SyntaxErrors. Fix: replace `\n` with `\\n` in heredoc source so the output file contains `"\n"` literal.

**Companion trap — triple-quote nesting** (Bash 70-71, Day 14 evening): Embedding a triple-single-quote sequence (`'''`) anywhere inside a triple-single-quote-delimited heredoc string terminates the outer string prematurely. Even in prose (backtick code refs in markdown). Olivier example: `f"writing Python code using triple-single-quote delimiters"` killed parsing because of the embedded literal triple-quote in the description.

**Rules**:
- Outer heredoc delimiter MUST differ from any sequence appearing inside content (`"""` outer when content has `'''`, vice versa)
- Backslash escapes destined for output file MUST be doubled: `\\n` → `\n` (file) → newline (runtime)
- Verify with `ast.parse(p.read_text())` immediately after write_text before any commit

**Trigger**: any patch script using Python heredoc to write Python source code. Defaults to "double-escape + outer-delimiter swap if content has same triple-quote type".

### Lesson 17 (Day 14 — audit must read complete control flow before declaring SEVERE)

Audit findings labeled SEVERE create disproportionate response (urgent fixes, pre-deadline races, scope expansion). A false-positive SEVERE erodes signal-to-noise across future audits and triggers wasted refactor cycles.

**Incident** (Day 14 evening, audit response): Declared "S1 SEVERE: cron_tier1_daily recomputes partial composite from only Tier 1 indicators, corrupting state". Proposed full architecture refactor (tier_scan + recompute_composite_from_latest split). Reality: lines 391-400 of `intelligence/debt_monitor.run_scan` already iterated ALL 15 indicators, merging fresh-scanned tiers with stale cached values from `get_latest_indicator()` for non-scanned tiers, computing composite on full 15 with `stale: True` markers. The fix I proposed already existed.

Root cause: I read the function signature + opening loop, pattern-matched against my mental model of "tier scoped means tier limited", and skipped reading lines 391-400 where the conditional branch handled exactly the case I claimed was broken.

**Rules**:
- Before declaring SEVERE, read the COMPLETE function body line-by-line
- Verify with: (a) empirical test on real data, OR (b) `git log -p` to see if the pattern was previously intentional, OR (c) recon grep for related comments/tests
- If unsure within 5 minutes, downgrade to HIGH or "potential" pending verification
- Track audit accuracy: false-positive rate matters more than total finding count

**Anti-pattern signature**: audit finding stated with high confidence but without quoting the specific lines of code that exhibit the bug. If you can't paste 3-5 lines showing the bug, you haven't read enough.

**Trigger**: any audit response. Apply meta-discipline before propagating findings.

### Lesson 18 (Day 14 — cron entry points MUST have try/except + notify envelope)

APScheduler runs jobs in its event loop. An uncaught exception in a cron function logs the traceback and continues, but no other surface exists for the failure: no retry, no alert, no signal to operator that the daily 06:00 protective layer just silently broke. The bot keeps running; the cron next-cycle is 24h away. Empty interval.

**Pattern (canonical)**:
```python
def cron_X() -> None:
    try:
        log.info("cron_X starting")
        # ... real work ...
        log.info("cron_X complete")
    except Exception as e:
        log.exception(f"cron_X crashed: {e}")
        try:
            from shared import notify
            notify.send_text(
                f"⚠️ *cron_X* crashed\n\n"
                f"`{type(e).__name__}: {e}`\n\n"
                f"Bot continues. Next attempt next cycle. Investigate logs."
            )
        except Exception:
            pass  # never let the alert dispatch raise; cron must return cleanly
```

Reference implementation: `intelligence/debt_monitor._cron_run(tier, label)` shared helper. The 3 debt_monitor crons delegate to it. Tested via mock.patch.object(run_scan, side_effect=RuntimeError) — confirms cron does NOT raise, crash-alert dispatches with proper format.

**Trigger**: any function passed to `sched.add_job(...)` as the callable. If it's a cron entry point, it MUST have the try/except envelope. Exceptions in regular handlers are caught by `python-telegram-bot` framework; crons have no such safety net.

### Lesson 19 (Day 14 — user-facing alerts MUST include actionable recommendation)

A Telegram push that says "Phase 2 → Phase 3, drivers: Gold P3, RepoSRF P3 — see /debt_status for more" is informational at best and useless at worst. The user (Olivier) is woken up at 06:00 Paris by the buzz, opens phone, reads alert, must context-switch to recall the playbook ("what does Phase 3 mean? what was I supposed to do? cash percentage? trim what?"), open /debt_status, cross-reference with portfolio state, then make a decision. Each step is a friction point. In a crisis, friction = abandonment of the protocol.

**Pattern**: every alert that announces a state change MUST include the action recommended for that state, inline, before the "see X for more" reference. The user should be able to take the right action with the push notification alone, even with the screen still locked.

**Reference**: `_PHASE_ACTIONS` dict in `intelligence/debt_monitor.py`:
```python
_PHASE_ACTIONS = {
    1: "Monitor. No portfolio action required.",
    2: "Cash +5%, halt aggressive deploys, watch Tier 1 daily for escalation.",
    3: "Cash +10-15%, defensive rotation, trim leveraged or concentrated positions.",
    4: "Cash 25%+, kill leverage, hedge tail risk (puts/inverse), defensive only.",
}
```
Composite escalation message appends `*Action:* {playbook[new_phase]}` before the /debt_status reference.

**Trigger**: any new push notification or Telegram alert that announces a state transition or threshold breach. Ship blocker: action playbook must exist before the alert can be enabled.

### Lesson 20 (Day 14 — UTC explicit on all persisted datetime fields)

Naive `datetime.now()` produces a timezone-unaware timestamp. When persisted to SQLite and queried later for chronological ordering or date arithmetic, ambiguity surfaces: was it server-local? UTC? CEST? KST? Cross-timezone migrations break silently. Comparing a naive datetime to a UTC-aware datetime raises `TypeError` at runtime.

**Rule**: all persisted datetime fields MUST use:
```python
from datetime import UTC, datetime
ts = datetime.now(UTC).isoformat()
```

This produces ISO 8601 with explicit `+00:00` offset. Roundtrip via `datetime.fromisoformat(s)` preserves tz info.

Display layer (Telegram, CLI prints) can convert to local via `ts_utc.astimezone(local_tz)`. Storage stays UTC.

**Incident** (Day 14 audit, scope: read-only finding): Discovered 20+ violations across legacy modules. Top offenders:
- `shared/storage.py:40` `last_heartbeat_ts = datetime.now().isoformat()` — naive, written every minute
- `shared/positions.py:47` position event timestamps
- `shared/edgar.py` (6 sites) caching layer timestamps
- `intelligence/{digest, morning_brief, calendar, price_monitor}.py` cutoff computations
- `bot/handlers/{thesis_health, anti_erosion, find}.py`

`intelligence/debt_monitor.py` was already correct (lines 318, 332). Audit produced full inventory; sweep tracked in TODO P2.

**Trigger**: any new `datetime.now()` call without arg → STOP, write `datetime.now(UTC)` instead. Existing violations sweep deferred to a dedicated session, not boil-the-ocean during feature work. Ruff custom rule candidate: detect `datetime.now()` (zero args) → flag.



---

## Lessons learnt — session 20/05/2026 (Chantier #1 start)

### Lesson 21 — Grep before invoke

Avant tout call cross-module à une fonction, classe, ou attribut:
- `grep -nE "^(async )?def {name}" {module}` OU inspect `__all__`
- N'invente JAMAIS de nom sur intuition

Three name-guess failures this session as forcing function:
- `tier_scan` invented (actual: `run_scan`)
- `recompute_composite_from_latest` invented (actual: `run_scan` persists already)
- WRESBAL units assumed billions (actual: millions per FRED native)

Sub-rule FRED-specific: empirical fetch + log value range AVANT de définir phase_ranges.
FRED units inconsistent (billions vs millions vs index vs % vs bp).

### Lesson 22 — Imports via ruff --fix only, never isort standalone

`pyproject.toml [tool.ruff.lint.isort]` config (combine-as-imports=true) takes
precedence for project canonical style. Standalone `isort` tool default behavior
SPLITS `from X import a, b` into two lines, opposite of ruff's combine.

Running both produces 18+ violations. Single source of truth:
- `ruff check --fix` for imports
- Drop `isort` from requirements-dev.txt and from CI workflows

### Lesson 23 — task= field optional by design in llm wrapper

`llm.call(tier=..., task=...)` has `task` as legacy/optional parameter.
Canonical pattern: use `tier=` (cost cascade routing). 19/21 call sites use
`tier=`. Only 2 sites use `task=` for legacy reasons (digest.py:29 signal_scoring,
why_matters.py:75 why_matters).

Empty task='' in llm_calls table is expected, NOT a bug. The `tier` column
provides sufficient cost attribution (haiku/sonnet/opus breakdown).

Documentation only; no code change required.

### Lesson 24 — Vulture is occasional audit, not CI gate

Vulture and ruff have overlapping concerns:
- ruff ARG001 catches unused function arguments via `# noqa: ARG001`
- vulture catches unused variables but doesn't read `# noqa` comments

This produces false positives on Telegram handler signatures
`async def cmd_X(update, context): # noqa: ARG001` which ruff allows but
vulture flags.

Resolution: vulture removed from regular gate workflow. Run occasionally
for audits via `vulture --min-confidence 80 --ignore-names context shared/ ...`.
Keep `ruff check` as the canonical CI gate for unused-arg detection.



### Lesson 25 — Phase B5 chain validated live, gap was discipline not code

Investigation 20/05/2026 KPI #5 (decisions journaled = 2/21 positions = 9.5%):

Diagnostic empirical via smoke test (/position_buy SMOKE → decision #8 entry / 
/position_sell SMOKE → decision #9 full_exit, both with auto-tagged biases):
- Phase B5 hook (positions.py:325 + L393) functional bout-en-bout
- Bulk backfill scripts (import_positions_legacy.py) intentionally bypass handler
  by calling `positions_mod.add_buy()` direct without log_decision
- Gap was discipline-of-use, not code regression

**Conclusion**: lower KPI #5 historical reading does NOT indicate Phase B5 broken.
Indicates bulk imports + zero live decisions. Forward-tracking is the right metric.

**Pattern for future audits**: when a KPI seems "off", trace data path empirically
before declaring code bug. A smoke test taking 30 seconds eliminates hypothesis (b) 
"code broken" before lengthy investigation of hypothesis (a) "data flow expected".



### Lesson 26 — UTC sweep audits ALL datetime touchpoints in same module

When sweeping `datetime.now()` → `datetime.now(UTC)` in a module, the change
makes computed timestamps tz-aware. ALL downstream operations that touch
these values must also be aware, otherwise TypeError on arithmetic.

Audit checklist for any module receiving UTC sweep:
1. `datetime.strptime(...)` → result is naive → `.replace(tzinfo=UTC)` needed
2. `datetime.fromisoformat(...)` → may be naive depending on input string
   - If input has `+00:00`/`Z` suffix → aware ✓
   - If input is naive ISO `2026-05-20T12:34:56` → naive → needs promote
3. `dt.replace(tzinfo=None)` strip pattern → ANTI-PATTERN with UTC-aware now
   - Invert logic: if dt.tzinfo is None: dt = dt.replace(tzinfo=UTC)
4. `(now - other_dt)` arithmetic → both must be aware OR both naive

Empirical regressions surfaced by Bash 124 sweep:
- shared/uptime.py: strptime parsed naive, compared to UTC cutoff → TypeError
  → fixed by .replace(tzinfo=UTC) on strptime result (Bash 126)
- bot/handlers/thesis_health.py: parsed datetimes had tz STRIPPED explicitly,
  then compared to UTC now → TypeError
  → fixed by inverting strip logic (Bash 128)

Trust the gates: tests + pytest surface these mismatches deterministically.
A failing test post-sweep IS the audit. Half-aware codebases are silent
runtime bombs; full sweep + test feedback is the safest discovery path.

Open backlog: `datetime.now(UTC).replace(tzinfo=None)` anti-pattern in 8 live
sites (intelligence/, bot/handlers/, shared/storage.py L868). Equivalent to
deprecated datetime.utcnow(). Harmonization candidate for separate P3 ship.


### Lesson 27 — Schema discipline tooling (Chantier #1 closing 21/05/2026)

Forcing function for Lesson 21 'grep before invoke': two complementary mechanisms.

**Write-time guard (opt-in, per developer)**:
```python
from shared.schema import assert_column_exists

def my_query():
    assert_column_exists("position_events", "ts")  # raises SchemaError on drift
    cx.execute("SELECT ts FROM position_events WHERE ...")
```

Use `shared.schema` helpers whenever writing new SQL touching a table.
LRU-cached, near-zero overhead. Discipline > performance.

Available helpers:
- `list_tables()` → all table names
- `list_columns(table)` → all column names of a table (raises if table missing)
- `assert_table_exists(table)` → raises SchemaError if missing
- `assert_column_exists(table, column)` → raises SchemaError if column or table missing
- `clear_cache()` → for tests / post-migration

**CI smoke gate (automatic, every test run)**:
`tests/test_schema_drift.py` AST-walks every `.execute()` / `.executemany()`
call site, regex-extracts table refs from constant SQL strings, validates
against current DB schema. Fails CI on orphan references.

Scope: tables only. Dynamic SQL (f-strings, concatenations with variables)
is skipped — accept those rare cases can't be statically verified.

When `test_no_orphan_table_refs` fails:
1. Typo / invented identifier → fix the SQL.
2. Legitimate new table → ensure table is in DB, run
   `python scripts/regen_schema_doc.py`, re-run tests.
3. SQL construct false positive (CTE alias, subquery name) → add to
   `_WHITELIST` in tests/test_schema_drift.py with rationale comment.

Empirical context: 5 Lesson 21 violations occurred during ad-hoc sqlite3
investigation in Bash 99-105 (May 2026). All would have been caught at
write-time with `assert_column_exists` / `assert_table_exists`. The
AST-based CI test would have caught the same patterns had they reached
actual code (they didn't — investigation only).

Chantier #1 closing criterion #6 closed via Option C (combo helpers + CI).


### Lesson 28 — Pre-commit gates order: ruff first, pytest last

CONVENTIONS for the order of verification before any `git commit`:
ruff check . [--fix]          # cheapest, surfaces formatting + obvious bugs
mypy --no-incremental ...     # type safety
pytest -q                     # behavioral correctness
git add ... && git commit ... # only after all 3 green

Empirical context: 2x this session (Bash 142 and Bash 147) I pushed commits
with `ruff` errors because I ran `pytest -q` (which passed) and skipped re-
running `ruff` after Python script edits. Both required immediate amend
commits.

Rule: **NEVER `git commit` without re-running `ruff check .`** after any
Python edit, even if pytest already passed. Ruff catches structural issues
that mypy + pytest don't see: import order, unused imports, redundant code
patterns. The 5-second ruff run is dirt cheap.


### Lesson 29 — Code-patching scripts must assert match invariants

When writing Python scripts that patch code via string substitution
(`text.replace(old, new)` or regex), pattern-match failures MUST surface
explicitly, not skip silently.

WRONG (silent skip):
```python
m = re.search(pattern, text)
if m:  # If pattern not found, skip without error
    text = text.replace(m.group(0), new_value)
```

RIGHT (explicit fail):
```python
m = re.search(pattern, text)
if not m:
    raise RuntimeError(f"Pattern {pattern!r} not found")
text = text.replace(m.group(0), new_value)
```

Empirical context: Bash 156 (commit 7a37803) patched scheduler job names
using `if m:` conditional. The script silently skipped 4 jobs whose names
didn't match the assumed pattern (e.g. `backup_job` vs actual
`daily_backup_job`). Fix required separate forward-fix commit (Bash 157
/ commit cef3356).

Pattern related to Lesson 21 (grep before invoke) but distinct surface:
Lesson 21 covers SQL identifiers, Lesson 29 covers in-code Python
identifiers. Same root cause: invented names that the scripted patch
doesn't validate.


### Lesson 30 — Test log capture: monkeypatch over caplog when module configures logging

`pytest.caplog` (and even root-logger handler attachment) becomes
non-deterministic across test orderings when ANY other module configures
logging at import time (`logging.basicConfig()`, `logging.disable()`,
setLevel on root, etc.). 

Empirical context: 16 tests in `tests/test_sql_observability.py` passed
isolated but 5 failed in full suite. caplog returned empty buffer in suite
context. Cause: `bot.main` import triggered `logging.basicConfig()`
which interacted with caplog's root handler. Tried 3 fixture approaches:
- caplog with logger name filter → fail
- caplog without filter → fail
- root logger custom handler → fail

Solution: **monkeypatch the module's `_log` reference directly with a
capturing stub**. Bypasses Python logging framework entirely. Tests verify
the SUT calls `_log.<level>(msg)` with expected args; production routing
to handlers is a config concern verified separately.

```python
@pytest.fixture
def log_capture(monkeypatch):
    from shared import sql_observability
    captured: list[tuple[str, str]] = []
    class Capturing:
        def info(self, msg, *a, **kw): captured.append(("INFO", msg))
        def error(self, msg, *a, **kw): captured.append(("ERROR", msg))
        # ... other levels
    monkeypatch.setattr(sql_observability, "_log", Capturing())
    return captured
```

Test asserts on `captured` list directly. Deterministic. Independent of
suite ordering, logging config, pytest plugin interactions.

Use this pattern when a module instruments via `logging.getLogger("X")`
and you want to unit-test the instrumentation calls.


### Query observability migration pattern (Item 1 canonical)

Use `shared.sql_observability.query()` for any **new** SQL site touching
the DB. Migration of existing sites is opt-in (high-ROI sites first).

Pattern:
```python
from shared.sql_observability import query

# Read with fetchall:
rows = query(cx, "SELECT ... WHERE ...", (params,),
             tag="module.intent", fetch="all")

# Read with fetchone:
row = query(cx, "SELECT ... WHERE ...", (params,),
            tag="module.intent", fetch="one")  # returns None if no match

# Write (UPDATE/INSERT/DELETE):
cur = query(cx, "UPDATE ... SET ...", (params,),
            tag="module.intent")  # returns cursor for .rowcount / .lastrowid
```

Tag conventions: `{module}.{intent}` snake_case. Examples:
- `digest.fetch_signals_for_synthesis`
- `morning_brief.predictions_resolved_30d`
- `positions.load_active_with_pnl`

Tags become grepable filters in production: `grep "morning_brief" bot.log`
shows every SQL touch in that module path.

Migrated sites as of 21/05/2026:
- intelligence/digest.py (2 sites)
- intelligence/morning_brief.py (11 sites)
- Pending: intelligence/price_monitor.py, shared/storage.py (selective)


### Lesson 31 — Schema audit BEFORE writing data invariants

When writing tests that query DB state, audit the actual schema first.
TODO.md assumptions may be stale or wrong.

Empirical context (Bash 175): TODO.md assumed `position_events.ts` column.
Actual schema has `timestamp`. Writing the test with `ts` would have
caused immediate failure on first run with "no such column: ts".

Run before invariant test: `sqlite3 data/bot.db "PRAGMA table_info(<table>)"`
for every table the test references. Note exact column names + types.
Then write the assertion.

Also check observed value ranges via `MIN()` / `MAX()` / `COUNT()` before
asserting bounds. If you'd planned `signals.score ∈ [0, 100]` but the
observed range is [1, 61], the assertion is either too loose (passes
trivially) or based on a spec you don't actually know. Omit invariants
whose spec you can't justify — false security worse than no test.

This is Lesson 21 (grep before invoke) applied to data tests.

## Lesson 32 (added 21/05/2026) — Compound script edits must be atomic

When a single Python script does multiple `str_replace` edits across
files, ALL edits must succeed or NONE land. Pattern:

```python
import sys
edits = [(path1, old1, new1), (path2, old2, new2), ...]
new_contents = {}
for path, old, new in edits:
    t = Path(path).read_text()
    if old not in t:
        print(f"[FAIL] anchor not found in {path}")
        sys.exit(1)
    new_contents[path] = t.replace(old, new, 1)
# Only AFTER all checks pass, write
for path, content in new_contents.items():
    Path(path).write_text(content)
```

Without this pattern, an AssertionError mid-script leaves files in a
half-edited state. The follow-up `git add` + commit will create a
partial commit whose message lies about what was changed.

Empirical: commit faa1ceb on 21/05 claimed 'pyproject.toml + CONVENTIONS.md
updated' but only CONVENTIONS.md was actually modified. Fixed in commit
following this Lesson addition.

Validation gate: after a multi-file edit script, ALWAYS check
`git diff --cached --stat` shows the expected file count before
committing. If short, stop and re-run.

## Lesson 33 (added 21/05/2026) — Bot running = SQLite write lock contention

DB writes via standalone scripts FAIL when bot is alive (`OperationalError:
database is locked`). SQLite WAL mode allows N readers + 1 writer; bot
holds write transactions during cron/handler operations.

Safe write pattern:
```bash
# 1. Kill bot with verification
pgrep -f bot.main  # note PIDs
for pid in $(pgrep -f bot.main); do kill -9 $pid; done
sleep 3
test "$(pgrep -f bot.main | wc -l)" = "0" || { echo "FAIL"; exit 1; }

# 2. Verify DB writable
python3 -c "import sqlite3; c=sqlite3.connect('data/bot.db',timeout=2); c.execute('BEGIN IMMEDIATE'); c.rollback()"

# 3. Write your data
# 4. Restart bot — VERIFY single instance
nohup python -m bot.main > bot.log 2>&1 &
sleep 10
test "$(pgrep -f bot.main | wc -l)" = "1" || { echo "Multiple bots running"; exit 1; }
```

Critical traps:
- `pkill -f bot.main` can FAIL SILENTLY on macOS (BSD pkill quirks).
  ALWAYS verify with `pgrep` after, never trust pkill exit code alone.
- `pgrep ... || echo "stopped"` is misleading — if pgrep prints PID and
  exits 0, the echo branch never fires. The PID print itself signals failure.
- Starting a new bot before old one is dead = TWO bots running, both
  fighting for DB lock + Telegram polling, both broken.

Empirical: 21/05/2026 orphans intent write took 3 attempts (Bash 215, 216,
217) because pkill failed silently, then a second bot was launched while
the first was still alive. Final Bash 217 used `kill -9 $(pgrep -f bot.main)`
with explicit count verification — worked first try.

Alternative pattern (if you must keep bot running): write via a Telegram
handler that goes through `shared/storage.py` with proper transaction
boundaries. Out-of-band script writes during bot uptime = avoid.

## Lesson 34 (added 21/05/2026) — Gates must hard-fail before commit

Multi-step Bash scripts that run gates THEN commit must explicitly
gate on each tool's exit/output. The pattern 'run gate → glance at
output → trust last step → commit' is unreliable.

Safe bash pattern:
```bash
ruff_output=\$(ruff check . 2>&1)
if echo "\$ruff_output" | grep -qE "Found [1-9]"; then
    echo "[FAIL] aborting"
    exit 1
fi
```

Combined with L29 (assert hard-fail) and L32 (atomic compound edit),
closes the silent-failure gap in 3-step refactor chains.

Empirical: 21/05/2026 — commit b512223 shipped 4 F821 latent because
ruff 'Found 4 errors' wasn't gated. Sunday cron would have crashed.
Caught by L34 enforcement in follow-up Bash session 229.

---

### L35 - Handler deletion sweep + hard-fail import gates (21/05/2026 Phase G bot down)

**Context** : Phase G deleted cmd_calendar_refresh from regime_calendar.py and bot/registry.py, but bot/main.py L52 still imported it. The script's import check (python3 -c 'import bot.main' printing OK on success) did not exit 1 on failure - so the script continued through pytest, restart (bot crashed silently in nohup background), and committed broken state. Bot stayed down until manually diagnosed.

**Two-part lesson** :

Part A - Deletion sweep must be repository-wide. When removing a handler function, grep ALL bot/ (not just registry.py + source file) :

    grep -rn 'cmd_FUNCTION_NAME' bot/ | grep -v __pycache__ | grep -v '.bak'

Any line returned outside the source file's docstring header is a reference that MUST be updated or removed. bot/main.py historically retains import statements from pre-refactor era.

Part B - Import gates MUST exit 1, not just print.

    # Wrong (silent fail):
    python3 -c 'import bot.main; print(OK)'

    # Right (hard-fail):
    python3 -c 'import bot.main' || { echo FAIL; exit 1; }

Any gate that prints without exit-1 is a useless gate. Audit all existing scripts for this pattern.

### L36 - Body extraction indent depends on source context (21/05/2026 Phase E)

**Context** : Phase E _cluster_impl + _buy_cluster_impl helpers extraction failed twice. First attempt dedented body by 4 spaces (assuming inside try: block like Phase C). Result: 25 ruff errors (F704 await outside function, F821 undefined names).

**Lesson** : check the indent level of the source block before extracting :
- Body inside try: block (8-space indent) -> dedent by 4 -> top-level function body (4-space)
- Body directly in function (4-space indent) -> NO dedent -> already correct for new function (4-space)

Also: imports declared BEFORE the parse marker (top of function) are NOT in the body extraction. Either move them to the helper or inject them at the helper's start. Phase E _buy_cluster_impl needed 'from shared import storage as storage_mod' injected because it was BEFORE the parse line in the original cmd_insider_buy_cluster.

### L37 - Templates Python generating Python code: no f-strings (21/05/2026 Phase D)

**Context**: Phase D extraction needed to embed Python helper code inside a Python script that modifies files. Initial draft used f-strings, but target Python code contains `{` `}` (dict literals, f-strings inside f-strings) which collide with f-string interpolation. Result: broken escape sequences `f"\'{\\" \\".join(args[2:])}\'"` unreadable and incorrect.

**Lesson**: When generating Python code from Python, use ONE of:
- Triple-quoted plain strings (no f, no interpolation)
- `.replace("___PLACEHOLDER___", value)` with explicit markers
- Pre-built complete strings, no interpolation

NEVER f-strings with target code containing `{` or `}`. The escape soup is unreadable and bug-prone.

**Empirical**: Phase D fix used backward-compat `parts = ["", ticker, field, value]` so the original body's `parts[3]` references work unchanged — sidesteps f-string entirely.

### L38 - exit 1 in zsh interactive paste kills shell session (21/05/2026 Phase D ruff gate)

**Context**: Phase D ruff gate used `ruff check . && echo OK || { echo FAIL; exit 1; }` pasted into interactive zsh. On FAIL, `exit 1` terminated the SHELL SESSION itself, not just the command. Lost cd, lost venv, had to restart terminal.

**Lesson**: In INTERACTIVE zsh paste, `exit 1` kills the shell session entirely. Use one of:
- Simple `echo "[FAIL]"` without exit (let user decide)
- Subshell: `( cmd && echo OK ) || echo FAIL`
- `false` (sets $? non-zero without killing shell)

In SCRIPTED execution (`bash script.sh`), `exit 1` is fine and expected. Distinction: interactive paste vs scripted file.

**Empirical**: Phase D ruff gate killed shell session after `[FAIL]`, forced restart. Cost ~2min recovery. Use `||` chains without exit for paste-context error reporting.

### L39 - pkill -f "python.*X" unreliable on macOS (21/05/2026 Phase D Telegram conflict cascade)

**Context**: 4 mes-bots-finance bots (PIDs 84875, 85232, 85244, 85284) accumulated over Phase D restart attempts, all alive simultaneously, all in Telegram Conflict retry loop. Multiple `pkill -9 -f "python.*bot.main"` calls reported [clean] but processes survived. New bot couldn't poll due to Telegram session lock held by orphans.

**Root cause**: macOS Python framework binary is `Python` (capital P at `/Library/Frameworks/Python.framework/.../Python`). pkill `-f` uses case-sensitive regex by default. Pattern `python.*bot.main` (lowercase p) does NOT match `Python -m bot.main` in process command line. pkill silently kills nothing, pgrep similarly reports nothing = false [clean].

**Lesson**: NEVER use `python` (lowercase) in pkill/pgrep patterns on macOS:
- USE: `pkill -f "bot.main"` (substring, case-independent because target string is literal)
- USE: `kill -9 <PID>` (explicit PID, zero ambiguity)
- AVOID: `pkill -f "python.*X"` — false negatives, silent no-ops

**Empirical**: ~30min Phase D recovery wasted on Telegram conflict cascade. Discovered via `ps auxww` revealing capital `P` in `/Library/Frameworks/.../Python -m bot.main`. Audit ALL existing crons + scripts for this pattern (uptime_monitor, restart scripts) to prevent future repeats.


## L40 — Read/display handlers must not have write side-effects (2026-05-22)

Incident: /thesis revisit affichait les questions de revisit ET appelait
storage.update_thesis_revisit() dans la même boucle. Afficher le prompt =
marquer reviewed. Combiné avec l'ignorance de ctx.args (full-scan systématique
de la due-list), un seul /thesis revisit 34 a mass-marqué les 33 theses actives
comme reviewed sans aucune review réelle. Corruption silencieuse de la discipline.

Regles:
1. Un handler qui prend un arg filtre optionnel (ID/ticker) DOIT l'honorer.
   Full-scan silencieux quand un arg est passé = bug. Résoudre l'arg, agir
   uniquement sur la cible.
2. Le marquage-as-done appartient à l'action de REPONSE de l'utilisateur, pas
   à l'affichage du prompt. Display = read-only; le side-effect (mark reviewed,
   increment) va sur la commande de suivi explicite.
3. Side-effects dans une boucle sur un set fetché, déclenchés par une seule
   action user, ont blast radius = taille du set. Toujours demander "si ce
   handler fire une fois, combien de rows mute-t-il?" Si >1 depuis une intention
   unique, redesign.

## L41 — Column-level restore from pre-corruption backup (2026-05-22)

Quand une colonne est corrompue sur N rows (pas un désastre full-DB), restore
juste cette colonne depuis un backup pré-corruption vérifié via ATTACH:

  ATTACH '/path/backup/bot.db' AS bk;
  UPDATE theses SET col = (SELECT bk.col FROM bk.theses bk WHERE bk.id = theses.id)
   WHERE id IN (SELECT id FROM bk.theses);
  DETACH bk;

Vérifier que le backup est pré-corruption (mtime UTC vs timestamp corruption UTC
— attention local-vs-UTC: mtime affiché en TZ locale, corruption stockée UTC).

Cross-db ATTACH UPDATE prend un write lock exclusif — FAIL "database is locked (5)"
même en WAL si le bot tient une connexion. STOP le writer (kill -9 PID) +
PRAGMA wal_checkpoint(TRUNCATE) avant le restore.


---

## 16. Concentration policy (ratifiee 25 mai 2026)

Gouverneur du risque = **cap de cluster correle**, pas le cap par ligne. Un book de N lignes exposees au meme driver n'est pas N paris, c'est 1 pari size N fois.

**Parametres** (source de verite: `config.yaml > concentration`):
- `cluster_max_pct: 0.57` -- plafond d'un cluster correle.
- `assumed_cluster_shock: 0.35` -- choc de reference (bear semi 2022-style).
- Derivation: `0.57 * 0.35 = 0.1995 < drawdown_stop_pct (0.20)`. Plafond cale juste sous le stop pour qu'un choc cluster ne le perce pas sur un seul evenement.
- `line_cap_by_conviction` -- taille max par ligne f(conviction): c5 8% / c4 6% / c3 4.5% / c2 3% / c1 2%. Remplace le flat `style.position_max_pct`.

**Cluster `semis_ai`**: noms correles sur le capex AI / cycle semi (liste dans config). Hyperscalers et power-for-AI = AI-adjacents, suivis hors cap.

**Reconciliation biais**: raboter l'overflow (8.5% -> 8%) n'est PAS le biais #1 (vendre trop tot) -- on garde le coeur qui court, on coupe ce qui depasse le budget. La sur-concentration est le biais #2 (greed / ne pas trimmer au top) applique aux actions, pas que la crypto.

**Enforcement**:
- Jusqu'au 10/06: manuel -- lecture du % cluster sur le dashboard (page Concentration), trim via /risk_check + /position_sell.
- Post-KPI#2: basculer `risk.validate_enabled: true` + wiring dans `risk_engine.validate()` -- check `line_cap_by_conviction[conv]` + somme ponderee du cluster vs `cluster_max_pct`, en WARN (pas hard block) sur buy/sell.

**Etat 25/05/2026**: cluster semis_ai ~73% (cible 57%); 4 lignes c5 >5% (4063.T 8.5 / ASML.AS 8.2 / TSM 7.7 / SNPS 7.0). Rebalance ~8K EUR vers drivers decorreles (healthcare/financials/defense/crypto -- deja dans l'univers, non tenus).

## Typographie & technique metal canonique (dashboard, 27/05/2026)

Tailles police (px) : titre page .phead h2 = 46 (w800, ls -.04em) ; gros chiffre hero .big = 46 ; chiffre cle .kv = 26 ; gauge label .gvm = 20 ; sous-titre .phead .sub = 12.

Technique metal texte = linear-gradient multi-stops + background-clip:text + -webkit-text-fill-color:transparent + color:transparent.
- Chiffres/gauge (.kv/.gvm/.big) : gradient 155deg keye sur la variable --c (couleur d'etat). .kv.bear/.acc/.warn/.id posent --c ; le 40 pose --c:var(--id) inline ; defaut --c = --ink.
- Titres (.phead h2) : chrome diagonal ~120deg, 2 speculaires, couleur DEDIEE (pas --c). Dark = silver clair brillant (#8b94a9 -> #fff -> #d8e0ec ...). Frost = graphite SANS blanc (#2b3340 -> #717d97 ...). Regle physique : un titre quasi-blanc disparait sur fond clair, le brillant vit en dark mode uniquement.
- Barre sticky .dband : verdict en metal d'etat ; textes secondaires .dx/.dn/.dc suivent la couleur d'etat (rouge alarme / vert calme).
