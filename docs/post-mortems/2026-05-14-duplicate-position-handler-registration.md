# Postmortem 2026-05-14 — Duplicate /position_buy and /position_sell handler registration

**Discovery date**: 2026-05-14 evening, during pre-flight recon for Sprint 1.1.
**Severity**: High principle (KPI #5 data integrity), Low magnitude (~18-22h window, observation mode).
**Status**: Fixed in commit c6d959a. Data audit pending (AI #9).

## Discovery context

CONVENTIONS §17 (recon-before-ship, shipped earlier today as part of AI #8) mandated
a structural recon of bot/main.py before scoping Sprint 1.1. The recon extracted
all `app.add_handler()` calls and revealed:

- 67 CommandHandler registrations
- 65 unique command names
- 2 commands registered TWICE: `/position_buy` and `/position_sell`

Function definition count was 2 (cmd_position_buy at L2801, cmd_position_sell at
L2900). Registration count was 4 (L3278 + L3279 + L3306 + L3307).

## Root cause

Ship 5 (2026-05-13, Day 3 morning marathon) repaired the Phase B5 journal logging
regression. Two parallel cmd_position_buy/sell defs existed:

- Phase B5 versions (L1888-region) with full journal_mod integration
- Later simpler shadowing versions (L2830-region) without journal integration

Ship 5 deleted the simpler shadowing versions, keeping Phase B5. ruff F811 was the
original detector for the dup-def regression.

**The defect**: Ship 5 deleted the dead defs but NOT the corresponding
`add_handler()` calls. After def deletion, both registration sites pointed to the
SAME surviving function name. python-telegram-bot does NOT deduplicate handlers
by command name — it fires all of them in registration order. Every
/position_buy and /position_sell invocation fired the handler TWICE.

## Impact

For every position_buy/sell since Ship 5 (2026-05-13 18:00 KST) until fix
(2026-05-14 13:43 KST):

- 1st call: cmd_position_buy → positions_mod.add_buy (writes position_event)
  → storage.log_decision (writes decision_id N) → bias_tagger.auto_tag_biases (N)
- 2nd call: positions_mod.add_buy idempotent on (ticker, ts) → no dup position_event
  likely. But storage.log_decision writes ANOTHER entry (decision_id N+1) →
  bias_tagger re-tags (N+1)

Net effect: decisions table likely contains DUPLICATE entries since Ship 5. KPI #5
(100% decisions journalisées) shows roughly 2x real count for those commands.

- Window: ~18-22h
- Volume: low (observation mode, minimal position activity per /portfolio)
- Severity principle: HIGH (Path 5/6 narrative depends on KPI #5)
- Severity magnitude: LOW (likely 0-3 actual dups in window)

Caught BEFORE Sprint 1.1 began → validates §17 recon-before-ship value.

## Fix

Commit c6d959a (2026-05-14 13:43 KST). awk-filter removes the SECOND occurrence
of each duplicate registration line. Keeps first (L3278 + L3279, original Phase
B5 block). Removes L3306 + L3307 (supplementary block).

Function defs UNTOUCHED. 2 lines deleted. bot/main.py: 3316 → 3314 LOC.

### Detector validation (CONVENTIONS §16)

- **positive=PASS**: post-fix reg count = 2, def count = 2, `import bot.main` OK,
  ruff 0 errors, bot restart clean (PID 10657, scheduler init log OK), 117/117
  pytest pass
- **negative=PASS**: pre-fix reg count = 4 = exact bug state the fix was gated to
  detect (`if [ "$DEF_CT" = "2" ] && [ "$REG_CT" = "4" ]`)

## Prevention

ruff F811 catches duplicate function defs but NOT duplicate add_handler calls
(syntactically valid Python).

Candidates (Monday decision):

1. **Handler-registration uniqueness smoke test** (AI #10, ~20min). Parse
   bot/main.py with ast, walk all add_handler calls, assert unique command
   names. Catches future re-occurrence at test-time.

2. **CONVENTIONS §18 delete-companion rule** (defer, only if pattern recurs).
   When deleting a function def, grep all add_handler / scheduler.add_job
   references to it and delete those too. Document the coupling.

3. **Registry pattern** (implicit via Sprint 1.1 refactor). Once handlers live
   in bot/handlers/*.py, registration via dict comprehension. Dict key
   collision = ImportError at module load = mechanical prevention.

Recommendation: ship #1 (AI #10) at Sprint 1.1 chunk 1 or pre-flight Monday.
Defer #2. Adopt #3 implicitly via refactor architecture.

## AIs

| ID | Action | Due | Effort |
|---|---|---|---|
| #9 | SQL audit decisions table for duplicate entries (ticker, action, abs(time_diff)<60s) since 2026-05-13 18:00 KST. If >=1 dup: decide cleanup vs annotate. | 2026-05-21 | ~1h |
| #10 | Add AST-based handler-registration uniqueness smoke test to tests/test_smoke_observation.py | Pre-flight Monday or chunk 1 | ~20min |

## References

- Fix commit: c6d959a
- Original Ship 5: SESSION_STATE.md Day 3 morning marathon close
- CONVENTIONS §17 found this — validates the rule
- CONVENTIONS §16 detector validation embedded in fix command
- Adjacent: 2026-05-14-uptime-monitor-case-bug.md (same session, similar root pattern)

---

## CORRECTION 2026-05-14 14h30 KST (added after AI #9 audit)

The IMPACT section above is OVERSTATED. Empirical audit (AI #9, closed this
date) proves the dup handler registration did NOT cause double-firing in
python-telegram-bot v21+.

### Evidence

`handler_calls` table for `/position_buy` invocations EVER:

| id | timestamp UTC | args |
|---|---|---|
| 22 | 2026-05-13 13:35:27 | `/position_buy NVDA 0.1 130 test b2 flag off` |
| 23 | 2026-05-13 13:40:12 | `/position_buy 1000 100 test gate on with massive size` |

The 2 entries are **4 minutes 45 seconds apart** with **completely different
args**. These are two separate user invocations, NOT one invocation
double-fired. If the dup had actually double-fired, invocation 22 alone
would have produced 2 handler_calls entries (the middleware fires once per
Telegram message regardless of how many CommandHandlers match in subsequent
groups) within milliseconds. Observed 4-minute spacing definitively
confirms separate invocations.

Data effects observed:
- Invocation 22 -> 1 position (#6 NVDA 0.1@130), 1 position_event (#5),
  1 decision row (#7). **Single set of writes**, not doubled.
- Invocation 23 -> 0 rows anywhere (presumably blocked by `risk_engine.validate()`
  given qty 1000 * $100 = $100K position > `position_max_pct=0.05` cap).

### Why the dup was dead code in python-telegram-bot v21+

Per `requirements.txt`: `python-telegram-bot>=21.0`. The v21+ default
`Application.process_update()` semantics within a single handler group
(group=0 for our CommandHandlers): the FIRST matching handler runs, subsequent
same-group handlers are NOT invoked (`block=True` default). The second
`add_handler(CommandHandler("position_buy", cmd_position_buy))` at L3306
was therefore **unreachable** — dead code, not double-fire trigger.

### Corrected impact assessment

- **No data corruption**. KPI #5 entries are NOT doubled.
- Fix in commit c6d959a is still correct — it removed dead code (smaller
  cognitive surface, ruff-cleaner, defends against PTB version upgrades
  that might change group semantics). But it did NOT fix a runtime bug.
- Original "Severity: HIGH principle, LOW magnitude" claim reduced to
  "Severity: LOW (code smell, dead code)".

### Why the over-claim happened

The original analysis assumed python-telegram-bot fires all matching handlers
in a group. This is true for aiogram and PTB v13 in some configs. It is
FALSE for PTB v21+ default. I did not verify library behavior empirically
(no docs read, no reproducer test, no AST inspection) before writing the
impact section. The hypothesis was embedded in the commit message
(c6d959a) before any audit.

### Meta-leçon

Postmortem impact sections deserve the same empirical discipline as code
(CONVENTIONS §16 detector validation). Hypothesis-as-fact in a postmortem
is the same class of error as untested KPI detector. When audit pending,
label "SUSPECTED, pending AI #N" rather than asserting.

This finding does NOT yet add a CONVENTIONS rule — per §16 recurrence
criterion (capture on pattern repeat). Logged as known meta-pattern for
the next postmortem.

### AI #9 outcome: CLOSED

- 0 duplicates in decisions table
- 0 unexpected position_events or positions
- KPI #5 was never corrupted
- No retroactive cleanup needed

### AI #10 status: STILL VALID

Handler-registration uniqueness AST smoke test remains scheduled for
pre-flight Monday or Sprint 1.1 chunk 1. Reasoning:
- Dead-code dup registrations are still bad (confusing, ruff-invisible)
- Defends against PTB version upgrades that might change group semantics
- Low cost (~20min), catches the issue in <1s in CI vs expert recon
