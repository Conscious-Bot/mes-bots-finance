# Handlers Consolidation Plan — 65 → 16 verb-root (V3 FINAL)

**Created**: 2026-05-15 evening (Day 4 close)
**Status**: SPEC ONLY, execution Sprint 1.2 post-J+28 (2026-06-10+)
**Naming votes finalized**: 2026-05-15 evening session

---

## Naming principles (user-validated)

1. **Mot complet > abbréviation privée** (rejected `/PF`, kept `/portfolio`)
2. **Singulier > pluriel** (`/signal /insider /filing` not `/signals /insiders /filings`)
3. **Verbe ou nom-domaine, jamais composé** (no `/insider_detail`)
4. **Sub-actions = mot anglais simple** (`add`, `buys`, `cluster`, jamais `buy_cluster_stats`)
5. **Default action returns useful state** (`/portfolio` without args = list view)

---

## Empirical basis (unchanged from V2)

- 2.1d telemetry, 74 calls, 36 unique handlers used
- 10.8% typo rate (8/74) — primary driver for consolidation
- Pareto: 9 handlers = 54% volume, 16 = 73%
- 37 NEVER-USED = workflow-pending features (post-J+28 resolution activates journal, signal, analyze deep work)

---

## V3 Final Design — 16 handlers

### TIER S — Atomic (5)
No args, instant response. Daily ritual + bot health.
/brief         daily ritual (6 sections)
/digest        run digest pipeline now
/help          show all commands
/health        bot health snapshot
/ping          liveness probe

### TIER A — Verb-root (11)
Default action when no subcommand. Verb-root pattern via `args[0]` dispatch.
/log <kind> <msg>
kinds: value | friction
Default: error "specify value or friction"
/thesis [action]
actions: list (default) | add | set | note | premortem | revisit | exit
No-arg: list active theses (chunked)
/analyze TICKER [kind]
kinds: deep (default) | debate | asymmetry | risk SIDE USD | materiality | replay
Pattern: ticker first, kind optional, kind-args follow
/portfolio [action]
actions: list (default) | buy | sell | set | history | orphans | override
/journal [action]
actions: view (default) | review | unresolved | tag | bias
/signal [action]
actions: recent (default) | type | source | brier | half_life
/insider [action]
actions: recent (default) | cluster | buys | digest
/filing [action]
actions: recent (default) | history
/market <topic>
topics: macro | regime | crypto | credit | calendar | price TICKER
Default: error "specify topic"
/source [action]
actions: list (default) | tier | promote | brier_top
/admin <topic>
topics: stats | kpi | costs | llm | resolve | predictions | feedback
Default: error "specify topic"

**Total: 5 + 11 = 16 handlers** (was 65, -75%)

---

## Mapping 65 → 16 (canonical reference)

### Direct preserved (5)
- `/brief` → `/brief` ✓
- `/digest` → `/digest` ✓
- `/help` → `/help` ✓
- `/health` → `/health` ✓
- `/ping` → `/ping` ✓

### /log consolidation (was 2)
- `/log_value <msg>` → `/log value <msg>`
- `/log_friction <msg>` → `/log friction <msg>`

### /thesis consolidation (was 8)
- `/thesis_list` → `/thesis` or `/thesis list`
- `/thesis_add` → `/thesis add`
- `/thesis_set` → `/thesis set`
- `/thesis_note` → `/thesis note`
- `/thesis_premortem` → `/thesis premortem`
- `/thesis_revisit` → `/thesis revisit`
- `/exit` → `/thesis exit`
- `/exit_force` → `/thesis exit_force` (or `/thesis force_exit`)

### /analyze consolidation (was 6)
- `/analyze TICKER` → `/analyze TICKER` (deep default)
- `/analyze_debate TICKER` → `/analyze TICKER debate`
- `/asymmetry TICKER` → `/analyze TICKER asymmetry`
- `/risk_check TICKER SIDE USD` → `/analyze TICKER risk SIDE USD`
- `/materiality [args]` → `/analyze TICKER materiality` or `/admin materiality`
- `/debate_replay TICKER` → `/analyze TICKER replay`

### /portfolio consolidation (was 8)
- `/portfolio` → `/portfolio` (list default)
- `/position TICKER` → `/portfolio TICKER` (drill-down)
- `/position_buy` → `/portfolio buy`
- `/position_sell` → `/portfolio sell`
- `/position_set` → `/portfolio set`
- `/position_history` → `/portfolio history`
- `/orphan_tickers` → `/portfolio orphans`
- `/override` → `/portfolio override`

### /journal consolidation (was 6)
- `/journal` → `/journal` (view default)
- `/journal_review` → `/journal review`
- `/journal_unresolved` → `/journal unresolved`
- `/journal_tag` → `/journal tag`
- `/bias_review` → `/journal bias`
- `/history TICKER` → `/journal history TICKER` or `/portfolio history TICKER`

### /signal consolidation (was 6)
- `/echo_recent` → `/signal` (recent default) or `/signal recent`
- `/signals_by_type` → `/signal type`
- `/credibility` → `/signal source` or `/source list`
- `/sources_brier` → `/signal brier` or `/source brier_top`
- `/sources_half_life` → `/signal half_life`
- `/sources_health` → `/signal health` or `/source health`

### /insider consolidation (was 5)
- `/insiders` → `/insider` (recent default)
- `/insider_cluster` → `/insider cluster`
- `/insider_buy_cluster` → `/insider buys`
- `/insider_buy_cluster_stats` → `/insider buys stats`
- `/insider_digest` → `/insider digest`

### /filing consolidation (was 2)
- `/recent_8k` → `/filing` (recent default)
- `/eight_k_history` → `/filing history`

### /market consolidation (was 6)
- `/macro` → `/market macro`
- `/regime` → `/market regime`
- `/crypto` → `/market crypto`
- `/credit` → `/market credit`
- `/calendar` + `/calendar_refresh` → `/market calendar` (+ optional `refresh` arg)
- `/price_check TICKER` → `/market price TICKER`

### /source consolidation (was 3)
- `/tiers` → `/source` (list default)
- `/tiers_watch` → `/source tier`
- `/promote TICKER tier` → `/source promote TICKER tier`

### /admin consolidation (was 7)
- `/handler_stats` → `/admin stats`
- `/kpi_status` → `/admin kpi`
- `/cost_trajectory` → `/admin costs`
- `/llm_costs` → `/admin llm`
- `/resolve_now` → `/admin resolve`
- `/predictions` → `/admin predictions`
- `/feedback` → `/admin feedback`

---

## Typo absorption (aliases registered 30d backward-compat)

Empirically detected typos route to canonical:
```python
app.add_handler(CommandHandler("list_theses", cmd_thesis))    # 1 call
app.add_handler(CommandHandler("list_thesis", cmd_thesis))    # 1 call
app.add_handler(CommandHandler("theses_list", cmd_thesis))    # 1 call
app.add_handler(CommandHandler("theses", cmd_thesis))         # 1 call
app.add_handler(CommandHandler("thesis_list", cmd_thesis))    # 3 calls (legit, kept alias forever)
app.add_handler(CommandHandler("orphan_ticker", cmd_portfolio_orphans_alias))
app.add_handler(CommandHandler("healthy", cmd_health))
app.add_handler(CommandHandler("log", cmd_log_hint))  # replies "use /log value or /log friction"
app.add_handler(CommandHandler("insider_clusters", cmd_insider))
```

Old commands (e.g. `/position_buy`, `/macro`, `/insiders`) registered as aliases for 30d.

---

## Implementation strategy (Sprint 1.2 post-J+28)

### Phase 1 — Sprint 1.1 Monday 2026-05-19 (planned, mechanical)
- Extract current 65 handlers into bot/handlers/*.py modules
- ZERO consolidation logic at this stage
- Result: 10 modules, same 65 handlers

### Phase 2 — Sprint 1.2 post-J+28 (per-module ship)
For each verb-root in V3 design:
1. Create wrapper `cmd_<verb>(update, ctx)` in handlers/<verb>.py
2. Parse `ctx.args[0]` to determine action
3. Dispatch to existing impl (now private `_<verb>_<action>_impl`)
4. Register OLD handler names as aliases (backward compat)
5. Update /help to show verb-root pattern
6. Ship per verb-root (1 commit per module)

### Phase 3 — J+30 alias purge
- Re-check handler_calls telemetry
- Aliases with 0 calls in 30d → deregister
- Aliases still used → keep permanently (typing habit signal)

---

## Routing pattern (canonical)

```python
async def cmd_thesis(update, ctx):
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
            f"Unknown /thesis action: `{action}`\n"
            f"Available: {', '.join(dispatch.keys())}\n"
            f"Default (no action): list",
            parse_mode="Markdown",
        )
    ctx.args = remaining
    return await handler(update, ctx)
```

For `/analyze TICKER [kind]` pattern (ticker-first):
```python
async def cmd_analyze(update, ctx):
    """Verb-root /analyze: ticker first, kind optional."""
    args = ctx.args
    if not args:
        return await update.message.reply_text("Usage: /analyze TICKER [kind]")
    ticker = args[0].upper()
    kind = args[1].lower() if len(args) >= 2 else "deep"
    remaining = args[2:]
    dispatch = {
        "deep": _analyze_deep_impl,
        "debate": _analyze_debate_impl,
        "asymmetry": _analyze_asymmetry_impl,
        "risk": _analyze_risk_impl,
        "materiality": _analyze_materiality_impl,
        "replay": _analyze_replay_impl,
    }
    handler = dispatch.get(kind)
    if not handler:
        return await update.message.reply_text(
            f"Unknown /analyze kind: `{kind}`\n"
            f"Available: {', '.join(dispatch.keys())}",
            parse_mode="Markdown",
        )
    ctx.args = [ticker] + list(remaining)
    return await handler(update, ctx)
```

---

## KPIs for consolidation success (measured J+60 post Sprint 1.2 ship)

- **Typo rate**: <2% (currently 10.8%)
- **Mean unique handlers/week**: 6-8 (currently 15+ fragmented)
- **`/help` invocations**: drop expected (less lookup needed)

---

## Risks + mitigations

| Risk | Mitigation |
|------|------------|
| User taps less-discoverable subcommands | Verb-root `/thesis` without args shows actions; Telegram autocomplete shows 16 clean roots |
| Routing logic adds bugs | Property-based tests on dispatch dict per verb, smoke tests per verb-root |
| Old habits → friction during transition | Aliases for 30d + bot.set_my_commands hint + /help updated |
| `/analyze TICKER kind args` parsing ambiguity | Strict pattern: ticker[0], kind[1], rest from [2:]. Type errors → return usage hint |

---

## Status

- ✅ Spec V3 finalized (2026-05-15 evening)
- ⏳ Sprint 1.1 mechanical extraction (Monday 2026-05-19)
- ⏳ Sprint 1.2 consolidation per module (post-J+28 = 2026-06-10+)
- ⏳ J+30 alias telemetry review (~2026-07-10)

## Decision log

- **2026-05-15**: User vote `/PF` rejected after pushback (case-insensitive, zero discoverability, breaks consistency). Final = `/portfolio`.
- **2026-05-15**: Singular cohérent across signal/insider/filing/source/journal/market.
- **2026-05-15**: `/analyze TICKER [kind]` ticker-first verb-root, NOT separate handlers per kind.
- **2026-05-15**: No `/find` aggregator command (user did not vote yes).
