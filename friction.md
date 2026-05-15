# FRICTION LOG — mes-bots-finance

Track every moment where the bot frustrated, missed, or felt clunky.
One line per entry. Don't fix on the spot — accumulate, prioritize later.

Format suggestion: `YYYY-MM-DD | context | what was missing/annoying`

Captures the wedge-feature signal for Phase 2 decision (Decision Journal vs Behavioral Graph).

---

## 2026-05

2026-05-13 15:56 | l'assistant a trop souvent insisté sur son envie que j'arrete ou fasse une pause, cela me deplait bcp, ensuite je pense que l'on a encore trop de handlers , je pense que jai besoin de le familiariser avec les outils, renommer et mieux comprendre les features, jaimerais enregistrer mes propres positions actuelles au bot pour voir en reel ce que son utilisation me fournirait.

## 2026-05-14 — Day 3 close friction batch (6 items, post-CI green)

### /brief specific
- `/brief` feels less interesting than `/digest`. Relative preference signal — when both available, user gravitates to digest.
- `/brief` truncates newsletter summaries mid-sentence. Concrete UX flaw, breaks readability.
- Unclear if `/brief` captures real value. Fundamental purpose question, not just polish.

### /brief vs /digest relationship
- `/brief` and `/digest` should probably be reviewed and possibly consolidated together. Two morning rituals competing for same attention slot.

### Handler metrics proliferation
- Too many handlers expose metrics/numbers in isolation. Could be unified into 1 handler + explanations. User does not understand all of them himself — they are dumped without context.

### Pipeline-wide signal
- Whole pipeline (ingestion → sources → interpretation → summary) could be improved. Not a single bug, a coherence question.

### Best features (expansion candidates)
- `/analyze` and `/orphan_ticker` are the most achieved features. Want to expand reach and catalog on these specifically.

### Disposition (deferred per observation window + Sprint 1.1 baseline + fatigue)
- Items 1-4: input for future `/brief` and `/digest` redesign sprint, post Sprint 1.1 close.
- Item 5: handler metrics consolidation sprint, separate scope.
- Item 6: pipeline-wide review, Phase 3 scope (~juillet 2026 earliest).
- Item 7: expansion candidates for `/analyze` and `/orphan_ticker`, post-J+28 batch resolution.
2026-05-15 04:31 | it seems that i did the digest feature and nothing came when i actually belive my mail is loaded on new newsletters with interesting content
2026-05-15 05:34 | comment est ce possible qu'il n y est aucun signal pertinent sur les dernières 24h

## 2026-05-15 — empirical validation of items 4, 5, 6

User reported /digest "bizarre — aucun signal pertinent ces dernieres 24h" despite 16 signals ingested in window.

Investigation revealed pipeline coherence gap: `signals.score` column deprecated since 2026-05-13 (materiality_v2 introduction Day 2 marathon), but /digest still filters on it. 31 of 92 signals have NULL score, all from May 13 onward. /digest filter `COALESCE(s.score, 0) >= 3` excludes all NULL scores → empty digest.

This empirically validates friction items 4 (/brief + /digest review together), 5 (metrics handlers without explanation), and 6 (whole pipeline coherence). User's intuition was correct: the friction was a real architecture gap, not just UX preference.

Full analysis: `docs/pipeline-coherence-audit.md`. Disposition: Sprint 1.2 critical input, no fix during observation window.

## 2026-05-15 — backup architecture drift + Makefile glob bug (Phase E audit)

Phase E pre-conditions sweep for Appropriation Phase 1 surfaced dual-script backup configuration mismatch:
- `crons/daily_backup.sh` (in crontab, 23:15 Paris) writes lean 2-file backup (DB + state.json) to `data/backups/`. Insufficient for disaster recovery — no code, config, or docs in archive.
- `scripts/backup.sh` (NOT in crontab) writes full 18M tarball with project files + atomic SQLite backup + 14d rotation to `~/backups/mes-bots-finance/`. Ran today at 04:00 Paris via unknown trigger mechanism — not visible in crontab or launchd output.

Day 2 marathon claim "✅ #2 Daily backup 04:00 + restore test + 14d rotation" was empirically misaligned: 04:00 schedule applies to scripts/backup.sh which isn't scheduled; 23:15 cron uses crons/daily_backup.sh which doesn't match Makefile restore test target paths.

Makefile glob bug: `ls -t ~/backups/mes-bots-finance/bot.db.*` matched SQLite SHM/WAL artifacts (sqlite3 fail "file is not a database 26"). The Day 2 "✅ restore test PASS" claim had never actually executed end-to-end until 2026-05-15 audit caught it.

Disposition: Makefile glob fix shipped 2026-05-15 (1-line ops, no behavior change). Dual-script drift documented for Sprint 1.2 reconciliation — decide: (a) unify on scripts/backup.sh + schedule via cron, (b) remove crons/daily_backup.sh, (c) keep both with explicit separation. Also investigate 04:00 mystery trigger mechanism.

## 2026-05-15 — Phase C audit: uncommitted WIP was actively broken (reverted)

Phase C Sprint 1.1 mental rehearsal surfaced uncommitted local edits on two files that broke verify checkpoint 0 silently and would have shipped active regressions to the health check:

1. tests/test_smoke_observation.py +80 lines duplicated already-committed tests (commit 26678e9). Python silently deduped function names (last def wins), but the duplicate block contained `HEALTH_SCRIPT = REPO_ROOT / ...` where REPO_ROOT was undefined. Ruff caught F821, breaking pytest collection entirely.

2. scripts/bot_health_check.sh L89-93 removed ZoneInfo Europe/Paris fallback in favor of pure UTC. Empirically broken: bot writes last_heartbeat_ts in Paris local without offset (AI #6 deferred). UTC interpretation makes timestamp appear in the future, triggering false "clock skew?" WARN.

3. scripts/bot_health_check.sh L244-245 renamed column resolved_at -> outcome_evaluated_at. Empirically wrong: predictions table column IS resolved_at (verified via .schema). outcome_evaluated_at does NOT exist. SQL errors silently swallowed by `|| echo 0`, making /health report "0 open predictions" when reality is 45 — false-GREEN on a KPI #2 critical metric.

KPI_DASHBOARD.md side-finding: it documents the same non-existent column (outcome_evaluated_at) on its win-rate query (line ~100). Documentation drift — the column never existed under that name. Track for Sprint 1.2 docs reconciliation.

Disposition: full revert via `git checkout HEAD --`. Verify restored to 9/9 PASS. Health check now reports correctly (heartbeat fresh + 45 open predictions).

Process lessons (codify if recurrence):
- Recon-before-ship (§17): grep for existing test names BEFORE adding new ones with same name
- Empirically check schema BEFORE writing column renames in scripts
- Final verify checkpoint MUST be re-run after any WIP, else drift accumulates silently
- Silent SQL error swallowing (`|| echo 0`) hides schema drift — consider failing loud instead

## 2026-05-15 — Phase B: AsyncIOScheduler structural fragility confirmed

Phase B audit of 23 sched.add_job sites in bot/main.py confirms Day 3 evening postmortem hypothesis empirically:
- 23/23 jobs are async def (all run in event loop)
- 0 uses of asyncio.to_thread, run_in_executor, asyncio.wait_for
- Zero sync-I/O isolation, zero timeout protection

Day 3 catastrophic "missed by 31min" hang was structural, not a fluke. Chronic "missed by 20-33s" entries in bot.log are sub-threshold manifestations of the same fragility. P0 suspects (hourly, sync remote APIs): ingest_gmail_job, score_pending_signals_job, scheduled_materiality_v2_job, scheduled_classify_signal_types_job.

Sprint 1.2 P0 fix architecture: wrap each sync-I/O job with `asyncio.wait_for(asyncio.to_thread(impl), timeout=N)`. ~2h critical path on 4 P0 jobs, ~6h full sweep on 23 jobs. No fix during observation — bot_health_check.sh + manual restart covers risk window.

Full risk-ranked table + recommended architecture in `docs/post-mortems/2026-05-14-apscheduler-hang-restart-cascade.md` Phase B section.

## 2026-05-15 afternoon — universal scaling temptation flagged

User raised possibility of "rendre le bot universel" supportant "milliers de tickers". This represents a fundamental shift from Path 5/6 High Standard Mode philosophy (precision in measurement > surface monitored) toward broad coverage. Flagged for cold-decision ADR rather than ad-hoc TODO line.

Symptoms suggesting universal scaling NOT yet justified:
- Current 178 tickers + 1 thesis = signal/decision ratio already misaligned
- 45 predictions clustered J+28 = horizon diversification not yet validated empirically
- /digest broken, materiality_v2 not yet wired to all downstream consumers
- AsyncIOScheduler structural fragility = 5x universe = 5x event-loop blocking probability
- KPI #2 NOT YET MEASURED — 0 empirical evidence current pipeline produces calibrated predictions

Universal scaling without prior track record evidence violates the central PHILOSOPHY constraint: "Plus de précision dans la mesure > plus de surface monitorée."

Decision deferred to ADR-002. To be drafted post-J+28 with empirical inputs from first KPI #2 batch resolution. Until then, NO universe expansion beyond max 3 thesis-candidate adds from queue.

Cross-ref: TODO.md "Thesis candidates queue" section, docs/thesis-candidates-queue.md, ADR-002 (to be drafted).

## 2026-05-15 — Universe expansion Option 2 (3 tickers, no thesis)

Post-thesis-candidates-queue creation, user opted for "Option 2": limited universe expansion (3 tickers added to config.yaml watch tier) WITHOUT logging any thesis. Justification:
- Universe expansion ≠ thesis logged ≠ position taken
- Bot begins ingesting signals on Kioxia/MHI/Stevanato, preparing post-J+28 evaluation
- Existing 45 predictions cohort untouched → KPI #2 batch resolution 2026-06-10 not contaminated
- 27-day soak before any /thesis_set or position action

Discipline boundary respected: cognitive momentum from external IA conversation converted into prep-work (universe + queue), not impulsive logging. Test of Option 2 success: at 2026-06-11, how many of these 3 candidates survive a fresh /analyze_debate + /asymmetry pass?

Process note: this is the FIRST universe modification during the observation window. Treating as one-time exception, not pattern. Future candidates remain in thesis-candidates-queue.md until post-J+28 default.

## 2026-05-15 afternoon -- 21 sector theses logged + watch tier 96 tickers

User feedback this session: "il n y a que les imbeciles qui ne changent pas d'avis". Acknowledged my earlier rigidity. Pivoted from "queue only, no thesis logging" to "log structured theses for cold review J+30+". 5 sector narratives with 21 ticker-level theses provide much richer learning substrate than 0-3 individual theses.

Structural innovation: theses grouped by sector_thesis_id embedded in `notes` column (storage schema doesn't support sector grouping natively; using Option B from earlier framing -- tags in notes for parseability). Allows synchronous sector-level review while preserving ticker-level granularity.

Discipline preserved:
- NO position commit (direction='watch' default)
- Soak period 27 days minimum before any /thesis_revisit promotion to long/short
- Sector-level invalidation tracking separate from ticker-level
- No schema change (sector_thesis_id is convention, not column)

This is the moment where the bot transitions from "system in waiting" to "operational personal tool with substrate to learn from". KPI #5 (decisions journalisees) trajectory shifts: from 0 material thesis decisions to 21 future revisit decision points scheduled.
