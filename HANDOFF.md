# HANDOFF — mes-bots-finance

> **READ THIS FIRST.** This file is the canonical entry point for any new
> Claude conversation or human re-entry. It supersedes scattered "reopen
> entry point" sections in `SESSION_STATE.md` for orientation purposes.
>
> If you're a Claude assistant opening this project: read this file before
> proposing any action. The default answer to "should I do X" is usually
> "no, wait until 10 June 2026 batch resolution or a real Telegram alert."

**Last verified state**: 2026-05-14 afternoon (Day 3 close)
**Mode**: Observation pure until 2026-06-10
**Bot status**: PID 8112 alive since 2026-05-14 03:30 CEST

---

## TL;DR

Personal finance bot project. Currently in **observation mode** — 28-day data
accumulation window ending 2026-06-10 (KPI #2 batch resolution of 45 open
predictions). Code freeze. No new features, tickers, sources, or refactors.
The work IS observation: daily `/brief` ritual on Telegram, plus
`/log_friction` and `/log_value` capture for Phase 2 wedge decision.

---

## Empirical state at last close (2026-05-14 afternoon)

| Domain | Value |
|---|---|
| Bot | PID 8112 alive since 03:30 CEST 2026-05-14 |
| Predictions | 45 open, 1 resolved, batch resolution 10-11 June 2026 |
| Tests | 117 passing (Hypothesis + smoke + sizing) |
| Linting | ruff 0 / mypy 0 on 14 strict-typed modules |
| Crons | 22 active (incl. backup 04:00, weekly summaries Sun 22:00 / 22:30 / 23:00) |
| LLM cost | $1.16 over 7d → $5/mo projected = 10% of $50 budget |
| BaseDataSource modules | 4 (GmailSource, EightKSource, BuyClusterSource, abstract base) |
| DB schema version | Alembic 0001 (28 tables stamped) |
| Backups | Primary 04:00 → `~/backups/mes-bots-finance/` ; Secondary 23:15 → `data/backups/` |

---

## Reopen checklist (~5 min on session start)

```bash
cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate
pgrep -fi "python.*bot.main"                     # NOTE: -fi (post 2026-05-14 fix)
bash crons/uptime_monitor.sh && tail -3 uptime.log
git log --oneline -10
```

**All green** (bot alive, OK alive logged, no surprise commits) → observation continues, nothing to do.

**Bot down** → `PROCEDURE_URGENCE.md` scenario 1 (now uses `pgrep -fli`).

**Anything else wrong** → see "When something breaks" below.

---

## Default operating mode (until 2026-06-10)

**DO**:
- Daily `/brief` on Telegram (~5 min)
- `/log_friction <text>` when bot annoys you
- `/log_value <text>` when bot provides real decision help
- Watch Telegram alerts (now functional post case-bug fix)
- Read weekly auto-summaries: Sun 22:00 cost / 22:30 KPI / 23:00 handler stats

**DO NOT**:
- Add tickers, sources, handlers
- Touch code for "small fixes" or refactors
- Re-scope sprints
- Open terminals to "just check"
- Re-implement features without first running:
  `grep -i "feature_name" SESSION_STATE.md && git log --oneline --grep="feature_name"`

---

## Open action items (postmortem 2026-05-14, none urgent)

| Échéance | AI | Effort | Status |
|---|---|---|---|
| 2026-05-15 (closed 2026-05-14) | ~~#5 purge or annotate `uptime.log` pre-fix false FAILs~~ DONE: archived to `uptime.log.pre_case_fix_20260514`, main log filtered to >= 12:26 with explanatory header | 30 min | ✅ done |
| 2026-05-21 | #3 `scripts/bot_health_check.sh` multi-signal alive check | ~1h | open |
| 2026-05-21 | #4 smoke test `pgrep -fi` regression guard in `tests/test_smoke_observation.py` | ~30 min | open |
| 2026-05-28 | #6 TZ standardization across logging components | ~2h | open |
| post-J+28 | #7 (P2) `bot_state.json` stale fields refresh | ~1h | open |
| post-J+28 | #8 (P0 process) `CONVENTIONS.md` rules: detector-validation + recon-before-ship | ~30 min | open |

**None block observation. Only #5 might be done before 2026-05-21 if desired.**

---

## Key meta-lessons (do not lose)

1. **Detectors backing KPIs need independent validation.** Case-sensitivity bug
   made KPI #1 unmeasurable for 3+ days. See
   `docs/post-mortems/2026-05-14-uptime-monitor-case-bug.md`.

2. **Grep SESSION_STATE + git log before scoping a sprint on a named feature.**
   Re-implementing existing work = dette + drift. On 2026-05-14 Claude nearly
   re-shipped Sprint 1.4 cost alert that already existed as "Ship C"
   (`weekly_cost_summary_job` at `bot/main.py:1173`, shipped Day 2 afternoon).

3. **TZ inconsistency across components** (until AI #6 resolves):
   - `bot.log` + `bot_state.json` = CEST (APScheduler `Europe/Paris`)
   - `backup.log` = UTC (explicit `date -u`)
   - Shell scripts (uptime, daily_backup) = system local (KST for user)
   - Double-check timezone when interpreting any timestamp.

4. **macOS process detection**: `pgrep -f "python..."` is case-sensitive and
   won't match `/.../Python.app/.../Python` (capital P). Always use `-fi`.
   Applied in `crons/uptime_monitor.sh` and `PROCEDURE_URGENCE.md`.

---

## Strategic context (one-paragraph)

mes-bots-finance is a self-learning thesis tracker mechanizing discipline
against two asymmetric biases: (1) selling winners too early (PLTR @$9,
NVDA @$130 in personal history), (2) holding crypto past indicator tops.
Stack: Python 3.14, SQLite WAL, APScheduler, Claude Haiku/Sonnet/Opus
cascade. Path 5/6 target: acquihire (18-24 months) or Substack + prosumer
subscription (24-36 months). High Standard Mode active since 2026-05-13:
**precision in measurement > surface monitored**. The next 28 days (until
2026-06-10) are the first real track record window — 45 predictions
resolve in batch, KPI #2 is the non-negotiable metric. Don't break the window.

---

## Reference docs (read order if more context needed)

| Doc | Purpose |
|---|---|
| **HANDOFF.md** (this file) | Canonical entry point — read first |
| `SESSION_STATE.md` | Full chronological session log (grows by accretion) |
| `TODO.md` | Closed work archive + KPI tables |
| `FICHE_TECHNIQUE.md` | Lean: mission + stack + KPI definitions |
| `PHILOSOPHY.md` | High Standard Mode principles |
| `CONVENTIONS.md` | Code/data conventions, type hints policy |
| `PROCEDURE_QUOTIDIENNE.md` | Daily 10-min health check |
| `PROCEDURE_URGENCE.md` | Emergency runbooks (bot crash, drawdown, API down) |
| `docs/post-mortems/` | Incident postmortems + template |
| `docs/runbooks/` | Per-failure ops runbooks (5 currently) |
| `docs/adrs/` | Architecture decision records |
| `VALUE_LOG.md` + `friction.md` | User wedge-signal capture for Phase 2 |

---

## When something breaks

1. Real Telegram alert → check `bot.log`, `uptime.log`, `data/bot_state.json` (in that order)
2. Bot down → `PROCEDURE_URGENCE.md` scenario 1
3. Cron loop / API stuck → `docs/runbooks/<topic>.md`
4. New incident → write postmortem using
   `docs/post-mortems/2026-05-14-uptime-monitor-case-bug.md` as template
5. Confused / drift suspected → re-read this HANDOFF.md, then check
   `SESSION_STATE.md` tail for the latest session entry

---

## Maintenance of this file

Update **in place** (not append) at session close when:
- New commits change empirical state (test count, modules, PID, etc.)
- New open AIs added or closed
- Operating mode changes (e.g., post-J+28 transition out of observation)
- Strategic context shifts (Path 5/6 dimension activation)

**Do NOT let this file accumulate session-by-session log entries** — that is
`SESSION_STATE.md`'s job. Keep HANDOFF.md as a snapshot, not a journal.
Target: under 200 lines, one or two screens, no chronological history.

---

**End of handoff.** Anyone reading this: respect observation mode. The right
answer to "should I do X" between now and 2026-06-10 is almost always
"no — wait for the batch resolution or a real alert."


## Evening pre-flight Day 3 (14 May 2026 ~14h KST) — refresh

Pre-flight Sprint 1.1 recon found and fixed 1 real defect + 2 doc drifts:

- **Fixed**: /position_buy /position_sell double-registered (commit c6d959a).
  Postmortem: `docs/post-mortems/2026-05-14-duplicate-position-handler-registration.md`
- **Doc drift corrected**: bot/main.py = 3314 LOC (not 2428). SESSION_STATE v3 refreshed.
- **Doc drift tolerated**: mypy 2 errors pre-existing baseline; pyproject.toml strict
  override = 11 modules (not 14). Both documented in SESSION_STATE.

Empirical refresh: bot PID 10657, 23 commits Day 3, 117/117 tests, ruff 0, mypy 2 tolerated.

### Open AIs updated

| AI | Échéance | Effort | Status |
|---|---|---|---|
| #9 SQL audit decisions for dup KPI #5 entries since 2026-05-13 18:00 KST | 2026-05-21 | ~1h | NEW |
| #10 Handler-registration uniqueness AST smoke test | Sprint 1.1 chunk 1 | ~20min | NEW |

AIs #3, #4, #6, #7 from morning postmortem remain open per original schedule.


## AI #9 CLOSED 2026-05-14 14h30 KST

Empirical audit (handler_calls + position_events + positions + decisions
cross-check) proves the dup handler registration was DEAD CODE in
python-telegram-bot v21+, NOT double-firing. 0 duplicates in any table.
KPI #5 was never corrupted.

Postmortem at `docs/post-mortems/2026-05-14-duplicate-position-handler-registration.md`
now has "CORRECTION 2026-05-14 14h30 KST" section. Original analysis
preserved; correction supersedes impact claims.

Fix c6d959a remains valid as code hygiene (dead-code removal).
AI #10 (handler-uniqueness AST smoke test) UNCHANGED — still ships Monday.

---

## Day 3 evening Tier 1+2 final (14 May 2026, post 26678e9)

Canonical state. Supersedes earlier HANDOFF sections.

### Empirical
- 31 commits Day 3, PID 10657 vivant
- 124 tests passing (119 + 5 from AI #3 regression guards)
- 30 DB tables, 45 open predictions due 2026-06-10
- Cost: 5 dollars/mo projected, 10% budget GREEN
- Bot health: GREEN via scripts/bot_health_check.sh (8 signals)
- Sprint 1.1 baseline chunk 0 captured at 2158adf (98 functions hashed)

### AIs closed Day 3 (7)
#3, #4, #5, #6-Phase-0, #8, #9, #10

### AIs open
- #6 Phase 1-6: TZ migration storage+edgar+intelligence, 4-5h, tracked in ADR 002
- #7: bot_state.json refresh, 1h, post-J+28
- #11: SQL audit predictions for TZ-offset, 1h, post-J+28 batch
- P3 NEW: KPI_DASHBOARD.md outcome_evaluated_at to resolved_at, 15min

### Reopen reflexes (revised)
1. cd to mes-bots-finance and source venv/bin/activate
2. ./scripts/bot_health_check.sh
3. python scripts/sprint_1_1_checkpoint.py list-chunks
4. cat HANDOFF.md
5. cat docs/sprint-1.1-plan.md

### Observation discipline
KPI #2 timer: 27d to 2026-06-10. No new features. Sprint 1.1 STRICT mode Monday 2026-05-19.


---

## Day 3 FINAL state (14 May 2026 evening close, post 347c59b)

Canonical state. Supersedes all earlier HANDOFF sections.

### What shipped today (36 commits)
- 7 AIs closed (#3 #4 #5 #6-P0 #8 #9 #10), 1 new captured (#12)
- Sprint 1.1 equivalence checkpoint harness + chunk 0 baseline
- Multi-signal bot health check (8 signals) + 5 regression tests
- 2 real-world findings caught by health check (TZ drift + schema drift)
- Docs aligned with current predictions schema
- GitHub repo public + 3-cycle CI iteration
- Type stubs pinned (types-requests + mypy>=2.1.0)
- Appropriation 4-phase roadmap defined

### Empirical state
- 124 tests passing, 0 ruff, 0 mypy on 19 CI modules
- Bot health GREEN, 45 open predictions due 2026-06-10
- Cost: 5 dollars/mo projected, 10% budget
- GitHub: https://github.com/Conscious-Bot/mes-bots-finance

### Open AIs
- #6 Phase 1-6 TZ migration (4-5h, ADR 002)
- #7 bot_state.json refresh (1h, post-J+28)
- #11 predictions TZ-offset audit (1h, post-J+28)
- #12 storage.py legacy dead code (30-60min, post-J+28)
- Appropriation Phase 1 pre-conditions (30min, post Sprint 1.1)

### Next reopen checklist
1. cd ~/mes-bots-finance and source venv/bin/activate
2. ./scripts/bot_health_check.sh
3. git log --oneline -5
4. cat HANDOFF.md
5. python scripts/sprint_1_1_checkpoint.py list-chunks

### Sprint 1.1 Monday 2026-05-19
STRICT mode, pre-flight artifacts in place. See docs/sprint-1.1-plan.md.

### Appropriation roadmap
4 phases defined Day 3 close. See FICHE_TECHNIQUE.md and TODO.md for detail. Phase 1 trigger: Sprint 1.1 complete.

### Observation discipline
KPI #2 timer 27d to 2026-06-10. NO new features. NO new tickers. NO new sources.
