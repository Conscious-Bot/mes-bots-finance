# Handlers Consolidation Plan — 65 → 18 verb-root (V4 FINAL)

**Created**: 2026-05-15 evening (Day 4 close)
**Last revision**: 2026-05-15 evening (V4 = V3 + /find aggregator + /theses asymmetry)
**Status**: SPEC ONLY, execution Sprint 1.2 post-J+28 (2026-06-10+)

---

## Naming principles (user-validated)

1. **Mot complet > abbréviation privée** (rejected `/PF`, kept `/portfolio`)
2. **Singulier pour verb-root domain**, EXCEPT `/theses` (pluriel pour list canonical)
3. **Verbe ou nom-domaine, jamais composé** (no `/insider_detail`)
4. **Sub-actions = mot anglais simple** (`add`, `buys`, `cluster`)
5. **Default action returns useful state** (`/portfolio` no args = list view)
6. **Aggregator handler** for cross-domain instant dump (`/find TICKER`)

---

## Empirical basis (unchanged)

- 2.1d telemetry, 74 calls, 36 unique handlers used
- 10.8% typo rate (8/74) — primary driver
- Pareto: 9 handlers = 54% volume, 16 = 73%
- 37 NEVER-USED = workflow-pending (post-J+28)

---

## V4 FINAL Design — 18 handlers

### TIER S — Atomic (5)
/brief         daily ritual (6 sections)
/digest        run digest pipeline now
/help          show all commands
/health        bot health snapshot
/ping          liveness probe

### TIER A — Verb-root + special (13)
/log <kind> <msg>
kinds: value | friction
No default (require kind for safety)
/theses                       ← PLURIEL exception : list canonical
View all active theses (chunked output)
No args required. NO subcommands.
/thesis <action>              ← SINGULIER for actions on individual thesis
actions: add | set | note | premortem | revisit | exit | exit_force
No default (require action; redirect "/thesis" alone → "/theses")
/find TICKER                  ← NEW: cross-domain instant aggregator
Dumps for TICKER:
- Thesis status (if tracked) + key drivers + invalidation
- Position (if held) + cost basis + PnL
- Last price + 1d/7d/30d % change
- Recent signals (30d) ranked by materiality
- Insider activity (90d net buys/sells)
Zero LLM cost, instant DB read.
/analyze TICKER [kind]
kinds: deep (default) | debate | asymmetry | risk SIDE USD | materiality | replay
Pattern: ticker first, kind optional, kind-args follow
/portfolio [action]
actions: list (default) | buy | sell | set | history | orphans | override
/portfolio TICKER → drill-down on one position
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
/source [action]
actions: list (default) | tier | promote | brier_top
/admin <topic>
topics: stats | kpi | costs | llm | resolve | predictions | feedback

**Total: 5 + 13 = 18 handlers** (was 65, -72%)

---

## /theses vs /thesis asymmetry rationale

**Design**: 2 handlers for thesis domain instead of unified verb-root.

- `/theses` (handler `cmd_theses`) → list active theses, no args, chunked output
- `/thesis <action>` (handler `cmd_thesis_dispatch`) → operations on individual

**Justification**:
- User ergonomic preference: `/theses` reads naturally for "show me my theses"
- Avoids semantic friction: "/thesis list" is mildly awkward in English
- Cost: +1 handler vs strict singular rule (18 vs 17)
- Empirical typo absorption: `/list_theses`, `/list_thesis`, `/theses_list`, `/theses` (5 variants in 2d) all consolidate to `/theses`

**Other domains stay singular**: `/signal`, `/insider`, `/filing`, `/source` — the verb-root model with default = list works fine for these (less typo evidence).

---

## /find TICKER design

**Differentiation from existing commands**:

| Command | Cost | Speed | When to use |
|---|---|---|---|
| `/find TICKER` | $0 | instant (~100ms) | Daily check: "what does the bot know about NVDA right now?" |
| `/analyze TICKER` | $0.10-0.30 | 10-30s | Deep work: full LLM analysis (valuation + thesis quality + risks) |
| `/portfolio TICKER` | $0 | instant | Position-focused drill-down (only if held) |
| `/thesis TICKER` (if applied) | $0 | instant | Thesis-focused (only if tracked) |

**Implementation skeleton** (Sprint 1.2):
```python
async def cmd_find(update, ctx):
    args = ctx.args
    if not args:
        return await update.message.reply_text("Usage: /find TICKER")
    ticker = args[0].upper()

    sections = []
    # 1. Thesis
    thesis = storage.get_thesis_by_ticker(ticker, status="active")
    if thesis:
        sections.append(format_thesis_compact(thesis))
    # 2. Position
    pos = storage.get_position(ticker)
    if pos:
        sections.append(format_position_compact(pos))
    # 3. Price + returns
    sections.append(format_price_block(ticker))
    # 4. Recent signals (30d)
    sigs = storage.recent_signals_for_ticker(ticker, days=30)
    if sigs:
        sections.append(format_signals_block(sigs[:5]))
    # 5. Insider (90d)
    insider = storage.insider_net_for_ticker(ticker, days=90)
    if insider:
        sections.append(format_insider_compact(insider))

    if not sections:
        return await update.message.reply_text(f"No data for {ticker}.")
    await update.message.reply_text("\n\n".join(sections), parse_mode="Markdown")
```

---

## Mapping 65 → 18 (canonical reference)

[Section unchanged from V3, see git history pre-V4 for full table]

### Updates V3 → V4
- `/thesis_list` → `/theses` (was `/thesis`)
- Aliases absorption: `/list_theses` `/list_thesis` `/theses_list` → `/theses`
- NEW handler: `/find TICKER` (no equivalent in current 65)

---

## Implementation strategy (Sprint 1.2)

[Sections unchanged — see Phase 1/2/3 below]

### Phase 1 — Sprint 1.1 Monday 2026-05-19 (mechanical extraction)
Extract 65 handlers into bot/handlers/*.py. Zero consolidation.

### Phase 2 — Sprint 1.2 post-J+28
1. handlers/thesis.py: split into `cmd_theses` (list) + `cmd_thesis` (dispatch)
2. handlers/find.py: NEW aggregator (~80 LOC)
3. Other verb-roots: dispatch pattern per V3 routing template
4. Old handlers as aliases (30d backward-compat)

### Phase 3 — J+30 alias purge

---

## KPIs for success (J+60)

- Typo rate: <2% (currently 10.8%)
- /find usage: empirical signal that aggregator solves the need
- /help invocations: drop expected

---

## Status

- ✅ V4 spec final (2026-05-15 evening, post /find + /theses votes)
- ⏳ Sprint 1.1 Monday 2026-05-19 (mechanical)
- ⏳ Sprint 1.2 post-J+28 (consolidation + /find NEW handler)
- ⏳ J+30 alias telemetry review

## Decision log

- **2026-05-15 evening V1**: Initial draft 13 handlers
- **2026-05-15 evening V2**: 20 handlers (added Tier S/A frequent direct)
- **2026-05-15 evening V3**: 16 handlers (/portfolio not /PF, singulier cohérent, /admin, /analyze ticker-first)
- **2026-05-15 evening V4** (THIS): 18 handlers — added /find aggregator (user vote OUI) + /theses pluriel exception (user vote)
