# Sprint 1.1 — bot/main.py refactor plan

**Drafted**: 2026-05-14 afternoon (Day 3 close, post-marathon)
**Status**: PLAN ONLY. Execution starts Monday 2026-05-18 or 2026-05-19 after pre-flight.
**Estimated effort**: ~45h per SESSION_STATE:374 (Day 3 morning carry-forward). 5 days × 9h focused work, with 17% buffer.
**Branch**: `refactor/handlers-split-2026-05-19` (to create Monday)

---

## Goal & scope

Split `bot/main.py` (3314 LOC at refactor start) into a domain-organized
`bot/handlers/*.py` structure. **Behavior must be 100% identical pre/post
refactor** — verified via smoke tests + manual Telegram exercises after each
chunk. No new features, no renaming, no consolidation. Pure cut+paste
restructure with import wiring.

Target: `bot/main.py` < 1000 LOC (init + scheduler + cron job functions kept
in place). New `bot/handlers/*.py` files at 100-400 LOC each, grouped by
domain.

## Why now (Phase 1 sequencing)

Per `SESSION_STATE.md:374` (Day 3 morning carry-forward), Sprint 1.1 was
scheduled for week of 18-25 May after Sprint 1.2 + 1.3 closure. With
Sprint 1.4 confirmed already-shipped Day 2 (Ship C, meta-lesson in commit
8757baa), Sprint 1.1 is the only Phase 1 sprint left before Sprint 1.6 PIT
(gated by KPI #2 GREEN on 10 June).

Refactoring before Phase 2 (Decision Journal, J+90→J+150) prevents Decision
Journal from being built on a 2428-LOC monolith. Smaller surface = lower
risk in Phase 2.

## Risk analysis

1. **Import cycle** (HIGH): `bot/main.py` imports handlers, handlers may need
   shared state from `bot/main.py`. Mitigation: extract shared state to
   `bot/_app.py` first.

2. **Handler lost from registration** (HIGH): extract `cmd_xxx` without
   updating `application.add_handler(CommandHandler("xxx", cmd_xxx))` =
   silent loss of `/xxx`. Mitigation: count handlers registered before+after,
   must match. Per-chunk Telegram smoke check.

3. **Cron job disconnect** (HIGH): same as #2 for `*_job` and
   `sched.add_job(...)`. Mitigation: count `add_job` calls before+after.

4. **Bot down during observation** (MEDIUM): if refactor breaks startup,
   KPI #2 timer is at risk for that day. Mitigation: each chunk produces a
   working bot, max 30 min downtime per chunk, `misfire_grace_time` handles
   missed cron firings.

5. **Module-level state breaks** (MEDIUM): globals, singletons,
   `app.bot_data` patterns may not survive split. Mitigation: identify all
   module-level state in pre-flight, hoist to `bot/_app.py` or `shared/`.

6. **Doc stale `bot/main.py:NNNN` line refs** (LOW): existing docs point to
   line numbers. Mitigation: use symbol-based refs (`bot/handlers/<D>.py:cmd_X`).

## Pre-flight checklist (Monday morning before any code change)

```bash
# 1. Clean state
git status                                              # MUST be clean
git log --oneline -5                                    # confirm latest
pgrep -fi "python.*bot.main"                             # bot alive

# 2. Recon-before-ship rule (CONVENTIONS.md §17)
grep -i "Sprint 1.1\|handlers-split\|refactor.*main" SESSION_STATE.md HANDOFF.md
git log --oneline --grep="Sprint 1.1\|refactor"
# If anything found beyond this plan -> investigate before starting

# 3. Snapshot
cp data/bot.db data/bot.db.pre_sprint_1_1_$(date +%Y%m%d)
cp data/bot_state.json data/bot_state.json.pre_sprint_1_1
cp bot/main.py bot/main.py.pre_sprint_1_1_$(date +%Y%m%d)

# 4. Baseline (must pass before starting)
pytest -v 2>&1 | tee baselines/pytest-pre-sprint-1-1.log
ruff check . 2>&1 | tee baselines/ruff-pre-sprint-1-1.log
mypy shared intelligence 2>&1 | tee baselines/mypy-pre-sprint-1-1.log

# 5. Counts (record for end-of-sprint comparison)
echo "Handlers: $(grep -cE 'add_handler|CommandHandler' bot/main.py)"
echo "cmd_* defs: $(grep -cE '^async def cmd_|^def cmd_' bot/main.py)"
echo "Crons: $(grep -cE 'sched\.add_job' bot/main.py)"
echo "LOC: $(wc -l < bot/main.py)"

# 6. Branch
git checkout -b refactor/handlers-split-2026-05-19

# 7. Create skeleton
mkdir -p bot/handlers baselines
touch bot/handlers/__init__.py
```

## Handler taxonomy (DRAFT — validate with recon Monday)

Proposed 8-10 domain split. Final names + grouping decided after re-reading
each handler's body Monday. Target file sizes 100-400 LOC.

| Domain | File | Probable handlers | LOC est. | Risk |
|---|---|---|---|---|
| anti_erosion | `bot/handlers/anti_erosion.py` | /log_value, /log_friction | 80 | LOW |
| observability | `bot/handlers/observability.py` | /cost_trajectory, /llm_costs, /handler_stats, /kpi_status, /health | 250 | LOW |
| admin | `bot/handlers/admin.py` | /override, /paper_only, /reset_state | 150 | MED |
| positions | `bot/handlers/positions.py` | /position_buy, /position_sell, /portfolio | 200 | MED |
| sources | `bot/handlers/sources.py` | /tiers, /promote, /sources_brier, /sources_health, /orphan_tickers | 250 | MED |
| signals | `bot/handlers/signals.py` | /signals_by_type, /materiality, /materiality_debug, /recent_8k, /insider_buy_cluster_stats | 300 | MED |
| thesis | `bot/handlers/thesis.py` | /asymmetry, /risk_check, /thesis_premortem, /analyze, /analyze_debate | 400 | HIGH |
| ritual | `bot/handlers/ritual.py` | /brief, /help, /start | 200 | HIGH (integrates many domains) |
| analytics | `bot/handlers/analytics.py` | /macro, /calibration, /patterns | 200 | MED |
| crons (stay) | `bot/main.py` | 22 *_job + scheduler setup + telemetry middleware | ~700 | — |

Plus `bot/_app.py` for shared state + Telegram Application init (~200 LOC).

## Extraction order (safest first)

1. **anti_erosion** — easiest, validates protocol
2. **observability** — low coupling, read-mostly
3. **admin** — touches bot_state but bounded
4. **positions** — touches positions_mod + decisions journal
5. **sources** — DB reads
6. **signals** — DB + scoring
7. **analytics**
8. **thesis** — biggest, LLM-heavy, last among handlers
9. **ritual** — /brief integrates many, near-last
10. **bot/main.py cleanup** — remove orphan imports, normalize structure

Crons stay in bot/main.py. Separate sprint if needed later.

## Per-chunk procedure (~30-60 min each)

For each domain `<D>`:

```bash
# 1. Create file
touch bot/handlers/<D>.py

# 2. Move functions: handler defs + private helpers used only by them
#    (manual edit, NOT sed - sed on Python is dangerous for indented blocks)

# 3. Add imports at top of bot/handlers/<D>.py
#    - from telegram import Update
#    - from telegram.ext import CallbackContext (or whatever signature uses)
#    - from shared import storage, llm, notify, config
#    - from intelligence import ... (per usage)

# 4. In bot/main.py:
#    - Remove the moved function defs
#    - Add: from bot.handlers.<D> import cmd_X, cmd_Y, cmd_Z
#    - Verify add_handler calls still reference the imported names

# 5. Static checks
python -c "import bot.main; print('import OK')"
ruff check bot/ shared/ intelligence/
mypy bot/handlers/<D>.py

# 6. Test suite
pytest tests/test_smoke_observation.py -v
pytest -v --tb=short

# 7. Live runtime
pkill -f "python.*bot.main" ; sleep 2
nohup python -m bot.main > bot.log 2>&1 &
sleep 10 && tail -30 bot.log         # scheduler init OK, no error

# 8. Telegram smoke (manual)
#    - /help: must list all expected commands (count unchanged)
#    - /<one-cmd-from-D>: verify expected response

# 9. Commit
git add bot/handlers/<D>.py bot/main.py
git commit -m "Sprint 1.1 chunk <N>/10: extract <D> handlers

- Moved: cmd_X, cmd_Y, cmd_Z to bot/handlers/<D>.py
- bot/main.py: 2428 -> NNN LOC (-MMM)
- Smoke tests pass, /<D>-cmd verified in Telegram
- Detector validation: positive=PASS (bot started, handler responds),
  negative=N/A (no detector code touched)"
```

## Smoke test protocol (3 layers, after each chunk)

**Layer 1 — Static (~30s)**:
```bash
python -c "import bot.main"
ruff check bot/ shared/ intelligence/
mypy <strict-typed-modules>
```

**Layer 2 — Tests (~2 min)**:
```bash
pytest tests/test_smoke_observation.py -v
pytest -v --tb=short
```

**Layer 3 — Live (~5 min)**:
- Bot restart + scheduler init log clean
- `/help` in Telegram (command count unchanged)
- `/brief` in Telegram (6 sections produced)
- One handler from extracted domain (response correct)
- 5 min later: uptime.log shows "OK alive"

ANY layer fails → STOP, diagnose, rollback if needed.

## Rollback plan

After each chunk, the previous commit is a known-good point.

```bash
# Soft rollback (preferred):
git reset --hard HEAD~1
pkill -f "python.*bot.main" ; sleep 2
nohup python -m bot.main > bot.log 2>&1 &

# If multiple chunks corrupted:
git checkout main
git branch -D refactor/handlers-split-2026-05-19
# Restart Sprint 1.1 with lessons learned
```

The `bot/main.py.pre_sprint_1_1_*` snapshot from pre-flight is the absolute
rollback (replace + restart).

## Acceptance criteria (sprint done when ALL true)

- [ ] bot/main.py < 1000 LOC
- [ ] bot/handlers/ contains 8-10 domain files, 100-400 LOC each
- [ ] Handler count post-refactor == pre-refactor (recorded in pre-flight)
- [ ] Cron count post-refactor == pre-refactor
- [ ] All tests pass (target 117+ green, no regression)
- [ ] ruff 0 / mypy 0 on previously strict-typed modules
- [ ] Bot starts cleanly, scheduler init log unchanged
- [ ] /help command count unchanged
- [ ] /brief produces same 6-section output
- [ ] 24h smoke run: no Telegram alerts triggered
- [ ] HANDOFF.md updated (handler taxonomy + new structure noted)
- [ ] Branch merged via `--no-ff` (preserve chunk history), branch deleted

## Time estimate (5 days × 9h focused, 17% buffer)

| Day | Chunks | Hours | Notes |
|---|---|---|---|
| Mon 05-19 | Pre-flight + anti_erosion + observability | 7h | Build confidence on protocol |
| Tue 05-20 | admin + positions | 8h | First state-touching chunks |
| Wed 05-21 | sources + signals | 9h | Largest single day |
| Thu 05-22 | analytics + thesis | 9h | Thesis is biggest single chunk |
| Fri 05-23 | ritual + bot/main.py cleanup | 7h | /brief is final integration test |
| Sat 05-24 | 24h smoke run + merge | 4h | Sun 05-25 = green, merge |

**Risk**: if a chunk takes 50% longer, total still fits with buffer used.

## Open questions to answer Monday before starting

1. **Effort reconciliation**: docs disagree (4h vs 45h). Real estimate after
   counting LOC-per-handler + cron complexity. If real <20h, compress.

2. **Branch strategy**: chunk commits on feature branch then `merge --no-ff`,
   OR squash-merge. **Default**: chunk commits + no-ff merge (preserve history
   for rollback granularity).

3. **Bot uptime**: restart after each chunk (~5-10 min × 10 = 1h downtime)
   acceptable during observation (misfire_grace_time covers cron misses)?
   **Default**: yes, restart-per-chunk.

4. **Test gap on /brief**: smoke tests check imports + key handlers exist,
   not behavior. Add 1 integration test (`tests/test_brief_smoke.py`) before
   starting, OR rely on manual Telegram check. **Default**: manual check
   sufficient given /brief is the final integration validation anyway.

5. **Telemetry middleware**: currently wraps every handler at registration.
   Move to bot/_app.py with explicit decorator, or apply in
   bot/handlers/__init__.py at import time? Resolve during pre-flight by
   reading the current implementation.

## References

- `bot/main.py` (3314 LOC at 2026-05-14)
- `SESSION_STATE.md:374` (Day 3 morning carry-forward, week 18-25 May)
- `TODO.md:178` (P3 architectural choice)
- `CONVENTIONS.md §16` (detector validation — for any new test added)
- `CONVENTIONS.md §17` (recon-before-ship — runs as pre-flight step 2)
- `docs/post-mortems/2026-05-14-uptime-monitor-case-bug.md` (template if anything breaks)
- `HANDOFF.md` (operational state, update post-sprint)

---

**End of plan. Sprint 1.1 starts Monday 2026-05-19 after pre-flight on Monday morning.**


## Pre-flight findings 14 May 2026 evening (added pre-Monday)

Pre-flight recon during the evening of 2026-05-14 (post Day 3 close session)
discovered and resolved several anomalies that affect this plan.

### Corrected facts

| Was | Now | Source |
|---|---|---|
| bot/main.py 2428 LOC | **3314 LOC** | `wc -l bot/main.py` post Phase 2.D fix |
| 22 cron jobs | **23** | `grep -c sched.add_job` |
| ~64 handlers | **65 unique** CommandHandlers | Phase 2 recon |
| Strict-typed = 14 modules | **11** (pyproject truth) | Phase 1 audit |

### Anomalies caught (handled before Sprint 1.1 start)

1. **Double handler registration** /position_buy /position_sell — fixed in
   commit c6d959a. Postmortem: docs/post-mortems/2026-05-14-duplicate-position-handler-registration.md
   New AIs opened: #9 (SQL audit), #10 (AST smoke test).
2. **Mypy 2 errors baseline** — tolerated, NOT blocker. Pre-existing in
   non-strict modules. Sprint 1.1 acceptance criteria updated to maintain
   <=2 mypy errors, not "0 mypy errors".

### Effort re-estimate (PENDING Monday pre-flight)

Original 45h estimate was for 2428 LOC. Actual 3314 LOC (+36%). **Plan effort
estimate flagged TO BE RE-VALIDATED MONDAY**.

Monday pre-flight Step 6 (counts recorded) becomes critical. Possible outcomes:
- LOC/handler ratio similar → effort scales linearly to ~60h, plan needs 6 days
- LOC/handler ratio lower → effort doesn't scale linearly, stays near 45h
- Ratio very low → bigger handlers inflate LOC, fewer moving parts, <45h

### Acceptance criteria updated

Add to checklist:
- [ ] Mypy errors post-refactor <= 2 (pre-existing baseline maintained)
- [ ] AI #10 (handler uniqueness AST smoke test) PASS
- [ ] No commits between pre-flight branch creation and Monday start

### References

- Postmortem: docs/post-mortems/2026-05-14-duplicate-position-handler-registration.md
- Recon details: SESSION_STATE.md "Day 3 evening pre-flight v3" section
