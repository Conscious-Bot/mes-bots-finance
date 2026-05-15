# Handlers Consolidation Plan — 65 → 13-20 verb-root

**Created**: 2026-05-15 evening (Day 4 close)
**Status**: SPEC ONLY, execution Sprint 1.2 post-J+28 (2026-06-10+)
**Empirical basis**: 2.1 days of handler_calls telemetry (74 total, 36 unique)

---

## Why consolidate

### Empirical signal: typo rate
- 8/74 calls (10.8%) were typos: `list_theses`, `list_thesis`, `theses_list`, `theses` (4 variants for /thesis_list), `orphan_ticker` (vs `orphan_tickers`), `healthy` (vs `health`), `log` (vs `log_value`), `insider_clusters` (vs `insider_cluster`).
- Surface of 65 handlers exceeds memory ergonomics.

### Empirical signal: Pareto
- 9 handlers = 54% of volume (digest, brief, help, health, log_value, analyze, insiders, log_friction, thesis_list)
- 16 handlers = 73% of volume
- 37 handlers = NEVER-USED in 2.1 days

### Why NEVER-USED ≠ dead code
The 37 NEVER-USED handlers are predominantly workflow-pending features (journal review, debate, risk_check, signals_by_type, sources_brier, tiers). They activate post-J+28 (KPI #2 batch resolution) when the bot transitions from build to operational. Consolidate, don't purge.

---

## Design: V2 (recommended)

### TIER S — KEEP DIRECT (6 handlers)
Frequent + atomic + memorable. Coût subcommand non justifié./brief           — daily ritual
/digest          — digest now
/help            — list commands
/health          — bot status (alias /healthy)
/ping            — liveness
/thesis_list     — view all theses (used 3x in 2 days, will increase)

### TIER A — KEEP DIRECT pour Pareto top (4 handlers)
Used ≥3 times in window, will be daily./log_value <msg>      — instant logging, no friction
/log_friction <msg>   — instant logging, no friction
/analyze TICKER       — primary deep work entry
/insiders             — insiders dashboard

### VERB-ROOT — Consolidate the rest (10 handlers)/thesis <action>
add | set | note | premortem | revisit | exit | exit_force
(no action defaults to /thesis_list which stays as alias)/portfolio <action>
[list] | buy | sell | set | history | orphans | override
list as default action (no arg = portfolio view)/journal <action>
[view] | review | unresolved | tag | bias/signals <action>
echo | by_type | sources | brier | half_life | health/tiers <action>
[list] | watch | promote/market <topic>
macro | regime | crypto | credit | calendar | price TICKER/insider_detail <kind>
cluster | buy_cluster | buy_cluster_stats | digest/filings <kind>
recent_8k | 8k_history/predictions <action>
[list] | resolve_now | feedback/ops <topic>
stats | kpi | costs | llm | materiality

**Total: 6 (TIER S) + 4 (TIER A) + 10 (verb-root) = 20 handlers**

---

## Implementation strategy (Sprint 1.2 post-J+28)

### Phase 1 — Sprint 1.1 Monday 2026-05-19 (already planned, mechanical)
- Extract current 65 handlers into bot/handlers/*.py per category
- ZERO consolidation logic at this stage
- Output: ~10 modules, same handler count

### Phase 2 — Sprint 1.2 (post-J+28, by module)
For each verb-root in design:
1. Create wrapper handler `cmd_thesis(update, ctx)` in handlers/thesis.py
2. Parse `args[0]` to determine action
3. Dispatch to existing internal function (now private `_thesis_add_impl` etc.)
4. Keep OLD handler `cmd_thesis_add` registered as alias for 30j (backward compat)
5. Help text updated to show verb-root pattern
6. Ship per module: thesis (1 commit), portfolio (1), etc.

### Phase 3 — J+30 alias purge
- Re-check handler_calls telemetry
- For each old-name alias: if 0 calls in 30d, deregister
- For aliases still used: keep permanently (typing habit signal)

---

## Routing pattern (canonical per verb-root)

```pythonasync def cmd_thesis(update, ctx):
"""Verb-root /thesis: dispatch to action."""
args = ctx.args
if not args:
return await _thesis_list_impl(update, ctx)
action = args[0].lower()
remaining = args[1:]
dispatch = {
"list": _thesis_list_impl,
"add": _thesis_add_impl,
"set": _thesis_set_impl,
"note": _thesis_note_impl,
"premortem": _thesis_premortem_impl,
"revisit": _thesis_revisit_impl,
"exit": _thesis_exit_impl,
"exit_force": _thesis_exit_force_impl,
}
handler = dispatch.get(action)
if not handler:
return await update.message.reply_text(
f"Unknown /thesis action: {action}\n"
f"Available: {', '.join(dispatch.keys())}"
)
# Inject remaining args back into ctx for the impl function
ctx.args = remaining
return await handler(update, ctx)

---

## Backward-compat strategy

### Aliases (kept 30d post Sprint 1.2 ship per module)
```pythonapp.add_handler(CommandHandler("thesis_list", cmd_thesis))    # routes to /thesis list
app.add_handler(CommandHandler("thesis_add", cmd_thesis_add_alias))
app.add_handler(CommandHandler("list_theses", cmd_thesis))    # typo absorption
app.add_handler(CommandHandler("list_thesis", cmd_thesis))    # typo absorption
app.add_handler(CommandHandler("theses", cmd_thesis))         # typo absorption

### Typo absorption priority (from empirical data)
- `/list_theses`, `/list_thesis`, `/theses_list`, `/theses` → all route to `/thesis [args]`
- `/orphan_ticker` → `/portfolio orphans`
- `/healthy` → `/health`
- `/log` → reply "Did you mean /log_value or /log_friction?"

---

## KPI for consolidation success

Measured 30 days post Sprint 1.2 ship (J+60 from now):
- **Typo rate**: target <2% (currently 10.8%)
- **Mean unique handlers used per week**: target 8-12 (currently 15+ fragmented)
- **Handler discovery rate** (/help calls): expected to drop (less need to look up)

---

## Risks + mitigations

| Risk | Mitigation |
|------|------------|
| User taps less-discoverable subcommands | Tier S frequent kept direct + autocomplete shows verb-roots |
| Routing logic adds bugs | Property-based tests on dispatch table, smoke tests per verb |
| Old habits → friction during transition | Aliases for 30d + Telegram bot.set_my_commands hint |
| Telegram autocomplete shows 13 instead of 65 | Acceptable — discoverability via /help + verb-root /thesis without args shows actions |

---

## Status

- ✅ Spec written (2026-05-15)
- ⏳ Sprint 1.1 mechanical extraction (Monday 2026-05-19)
- ⏳ Sprint 1.2 consolidation per module (post-J+28 = 2026-06-10+)
- ⏳ J+30 alias telemetry review (~2026-07-10)
