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

## 2026-05-15 evening — /thesis_list bug + add_thesis() vs insert_thesis() canonical divergence

User attempted /thesis_list in Telegram after logging 21 sector theses. Bot crashed silently with `telegram.error.BadRequest: Text is too long` (Telegram hard limit 4096 chars). Root cause investigation revealed TWO distinct bugs:

**Bug 1 — Telegram message size**: cmd_thesis_list at bot/main.py:115 calls await update.message.reply_text(msg) with no chunking. With 22 theses, msg = 47672 chars (well over Telegram's 4096 limit). Fixed via chunking pattern (~16 LOC added to cmd_thesis_list).

**Bug 2 — add_thesis() stores plain strings, list_active() expects JSON lists**: Output was not just too long, it was corrupted — `for d in thesis.get("key_drivers")` iterates char-by-char when key_drivers is plain string instead of JSON list. shared/storage.py has TWO insertion functions:
- `add_thesis()` (L68): stores drivers/invalidation/triggers as plain string verbatim — BROKEN for format_thesis_card consumers
- `insert_thesis()` (L288, L328): calls `_t_json.dumps(_to_list(...))` to convert to JSON list — CORRECT

NVDA dummy thesis (created Phase 2 marathon) was logged via insert_thesis() — worked fine. The 21 sector theses I added 2026-05-15 afternoon used add_thesis() — all broken on read.

Fixed via 3 data migrations: convert plain strings to JSON list for key_drivers, invalidation_triggers, triggers_profit_take across all affected theses. Used `to_jsonlist()` with separator heuristics (". " for drivers/invalidation, " OR " for triggers_profit_take).

**Sprint 1.2 P1 candidate**: Either deprecate add_thesis() (route all callers to insert_thesis()) or fix add_thesis() to also call _to_list+json.dumps. Currently two parallel APIs with divergent behavior = future bug magnet.

**Process lesson**: when CONVENTIONS §5 says "DB SQLite -> toujours via shared/storage.py", knowing WHICH function in storage.py to call matters. The signature `add_thesis(ticker, conviction, direction, horizon, drivers, invalidation, ...)` looks identical to insert_thesis but doesn't serialize properly. Add API choice documentation OR consolidate to single canonical entry point.

Also: NVDA dummy thesis (id=1) soft-deleted via update_thesis_status('deleted') to preserve audit trail and predictions integrity. 22 -> 21 active theses now match the 21 sector theses logged this afternoon.

## 2026-05-15 evening — Handler typo rate 10.8% empirical

Audit handler_calls telemetry (2.1 days, 74 calls, 36 unique handlers used).
Found 8/74 calls (10.8%) are typo variants of intended command:
- thesis_list intent: 5 variants (thesis_list, list_theses, list_thesis, theses_list, theses)
- orphan_tickers intent: 2 variants (orphan_ticker, orphan_tickers)
- health intent: healthy (typo)
- log_value/log_friction intent: log (typo)
- insider_cluster intent: insider_clusters (plural typo)

65 handlers exceeds memory ergonomics. Consolidation 65 -> ~20 verb-root
handlers spec'd in docs/personal/handlers-consolidation-plan.md. Execution
deferred to Sprint 1.2 post-J+28 (observation window protected).

Process lesson: every typo costs ~3-5 seconds (read error + retry).
At 4 typos/day average, that's ~15-20 sec daily friction tax. Annual = 1.5h.
Consolidation value is mostly UX/discipline, not perf. Justifiable but not urgent.


## 2026-05-15 evening late — Portfolio targets schema ship

Empirical discovery during portfolio import:
- User provided allocation document with 24 target positions
- Holdings list pivoted twice in same session (8 tickers -> 15 tickers TR exec + 6 PEA)
- Original target doc had inaccessible tickers (MTUS, KWEB, DIXON) reallocated
  on the fly during conversation
- 86% of holdings actuels NOT in target allocation = legacy portfolio requires
  active rebalancing over 8-12 weeks

Process lesson: portfolio audit empirique BEFORE any code touching positions
table. The 10-minute gap between user's two holdings lists revealed massive
divergence. Without this audit, drift report would have been computed on
stale data.

Implementation lesson: positions table needed account column (PEA vs TR) for
multi-broker tracking. ADR-003 documents the bitemporal pattern reuse from
ADR-001 credibility ledger.

Currency complexity: legacy import stores cost_basis in EUR uniformly. Native
currency tracking (Sprint 1.3 candidate) preserved as open question in ADR-003.

2026-05-17 | Day 10 D investigation | position_buy n=2 telemetry vs 0 position_events Day 9 — NOT A BUG. args_summary révèle invocations bare ou incomplètes (/position_buy, /position_buy TSLA) qui retournent usage help. Chain intègre. Optionnel future: add args_valid column à handler_calls pour distinguer invocations valides vs help-requests.

2026-05-17 | Day 10 D investigation | position_buy n=2 telemetry vs 0 position_events Day 9 = NOT A BUG. args_summary = "/position_buy" et "/position_buy TSLA" (args malformés) → cmd_position_buy retourne usage help gracefully sans raise. Chain intègre par design. Capture: telemetry compte TOUTES invocations y compris help-requests.
2026-05-21 05:05 | test phase L

2026-05-21 | /risk_check COHR | USD_AMOUNT required field semantically pour "ajout capital", pas pour "évaluation position existante sous stress" — friction quand l'usage est défensif (trim/exit) pas offensif
2026-05-21 | /thesis premortem ALAB | "Invalid id: ALAB" — handler accepte numeric ID seulement, pas de resolution ticker→active_thesis_id. Force /thesis list lookup intermédiaire
2026-05-21 | /thesis premortem 34 (ALAB) | feature gap : premortem ajouté Phase B7 (12/05), non-retroactif → indisponible sur ~21/33 theses anciennes. Backfill manuel ou exclusion explicite à documenter dans /thesis premortem help.
2026-05-21 | /thesis revisit 34 (ALAB) | spam Telegram multi-messages (likely thèse + signaux + prédictions + ?). Handler pré-canonical, dump-style. Besoin: review focusé (4 numbers + 1 question), pas dump exhaustif. → P1 rollout candidate.
2026-05-21 | /thesis set <field> <value> | help message ne précise pas la devise attendue. DB EUR-canonique, mais display USD partout. User doit convertir mentalement pour chaque set. → fix: aide explicite "valeur en EUR (storage canonique)" OU accepter "$230 USD" et auto-convertir.
2026-05-21 | schema theses | 3 colonnes target distinctes (target_price legacy, target_partial, target_full) toutes visibles dans help /thesis set → user choisit laquelle? Schema debt: legacy target_price probablement dead column. Audit needed.
2026-05-21 | env hygiene | cd vers tennis-bot + venv désactivé en cours de session. Récurrent. → candidat: alias shell `mbf` = cd mes-bots-finance && source venv/bin/activate, OU prompt qui affiche repo actif clairement.
2026-05-25 | /asymmetry carte partiel | le prompt "exécute ta prise partielle" se déclenche sur proximité cible PLEINE (d_tgt<=12 || frac>=75), jamais sur `price >= target_partial`. Wording "cible bientôt atteinte" induit un faux modèle (partiel = à la cible). Sous-prompte le partiel pour les paliers bas dans la bande → biais tenir-trop-longtemps encodé dans l'UI. Fix: gater sur target_partial franchi + dissocier le wording palier/cible. (render.py:935-941)
2026-05-26 | paste channel | blocs avec lignes '#' plantent en zsh interactif (command not found) -> echo-only

## 2026-05-28 — Audit decisions table post reconciliation Lasertec

2026-05-28 11:00 | /position_sell + /position_buy 6920.T->6857.T | reasoning auto-genere generique ("Buy via /position_buy" / "Sell via /position_sell"), pas de prompt pour la raison reelle au moment du trade. KPI #5 incremente sans substance. Workaround = UPDATE SQL post-trade (fait Day 17). Fix UX post-obs : soit prompt reasoning au capture-time dans cmd_position_buy/sell, soit /journal_decision separe pour narrer apres.

2026-05-28 11:05 | audit historique decisions id=10 (25/05) | reasoning riche mais thesis_id=NULL au capture (decision orphelin de these). Source pas claire (peut-etre /thesis_decision ou input manuel sans rattachement). Pattern dangereux : decisions orphelines ne comptent pas KPI #5 thesis-link coverage. Fix Day 17 via UPDATE thesis_id=52. A surveiller si recurrent dans les semaines a venir.

2026-05-28 11:45 | /insider_buy_cluster_stats broken | handler ne fonctionne pas (sortie vide ou erreur). Bloquant pour quantifier signal insider sur tickers semi. Decouvert en voulant calibrer trim cluster. Fix post-observation.

2026-05-28 12:00 | /digest macro signal -> trade decision gap | /digest a surface "insider selling cluster semis" mais sans drill-down ticker-specific. Lecture macro impossible a convertir directement en trade single-ticker. Soit /digest doit driller (top-N tickers cluster), soit accepter qu'il sert au framing thematique pas a l'execution.

2026-05-28 12:05 | TSM no documented thesis (vu via /risk_check) | pattern recurrent : positions actives sans thesis_id linke. Audit needed : combien de positions ont thesis_id=NULL ? Si >20%, KPI #5 thesis-link coverage fictive. Candidat audit batch post-observation.
2026-05-28 | /journal_decision build | decision_type a un CHECK enum (entry/scale_in/partial_exit/full_exit/override/no_action_flag) documente NULLE PART -> 2x rejet INSERT sur 'no_action'. A documenter CONVENTIONS.md.
2026-05-28 | /tiers | commande fantome : 6 invocations telemetrie, jamais enregistree. Help V4 l'annoncait "source tier ranking", intention reelle = conviction sizing. Gap help-spec vs mental model.
2026-05-28 | naming commandes | noms intuitifs inexistants tapes (/positions, /value_log) -> 5+2 tentatives mortes. Alias sur vocabulaire naturel manquants.
2026-05-28 | /signals_by_type catalyst | bucket catalyst bruite : opinion/narrative (Matt Levine, Stoller, Aave) classes catalyst. Calibration classifier post-10/06.
2026-05-28 | /signals_by_type | source_name = header From brut ("Name <email>") au lieu d'un nom propre. Display-polish.
2026-05-28 | /help | ~10 cmds sans docstring -> ligne vide (calendar, credibility, credit, exit, exit_force, feedback, ping, regime, resolve_now, thesis_list). Docstring = 1 ligne, cheap.
