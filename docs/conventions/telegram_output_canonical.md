# Telegram Output Canonical Format

**Status**: Approved 21/05/2026 evening based on /debt_status as reference template.
**Rollout**: Day 16+ progressive migration of high-traffic handlers.

## Anatomy
[EMOJI_TITLE] TITLE — [STATUS_EMOJI] STATUS_LABEL
[Composite/summary single line]
━ [SECTION_NAME] ([COUNT]) ━
[severity_emoji] [name padded]   [value right-aligned]  [tag]
[severity_emoji] [name padded]   [value right-aligned]  [tag]
...
━ [SECTION_2] ([COUNT]) ━
...
Run /handler_subcommand ... for [hint].

## Severity emoji palette

| Emoji | Level | Use cases |
|-------|-------|-----------|
| 🔴 | HIGH / CATASTROPHIC | Critical alerts, stop-loss, severe drift |
| 🟠 | ELEVATED / WARNING | Notable but not urgent |
| 🟡 | STRESS / WATCH / MEDIUM | Monitor, attention needed |
| 🟢 | NORMAL / OK / LOW | All clear, baseline |
| ⚪ | STALE / UNKNOWN | No data or unrecognized |

## Structural rules

1. Header + summary: 1-3 lines max above first section
2. Section dividers: `━ SECTION_NAME (count/aggregate) ━`
3. Body lines: monospace (HTML `<pre>` or backticks), columns aligned via padding
4. Severity emoji ALWAYS first char of each body row
5. Footer command suggestion in backticks, optional, last line
6. NO blank line within section, BLANK line between sections

## Reference: /debt_status (canonical)
💣 DEBT CRISIS MONITOR — 🟡 STRESS
Composite: 30.8 pts → Phase 2
━ Tier 1 (22.0pts) ━
🟢 30Y Treasury Yield (%)                 5.1160  P1
🟠 Gold Spot ($/oz)                        4,531  P3
...

## Rollout priority (Day 16+)

| Handler | Daily usage | Friction observed | Priority |
|---------|-------------|-------------------|----------|
| /brief | Daily ritual | Density, no severity grouping | P0 |
| /recent_8k | Investigation | 22 rows undifferentiated | P0 |
| /asymmetry (portfolio) | Decision-time | Currency label bug + density | P0 |
| /thesis health | Weekly | Already OK-ish | P2 |
| /portfolio_views/* | Daily | TBD per user observation | P1 |
| Other handlers | Lower frequency | Observe before redesign | P3 |

## Anti-patterns

- `!` `!!` text severity markers (use emoji)
- Dense entry lists without section grouping
- Description lines indented under header (doubles vertical space)
- No header/no summary/no count totals
- Tables in markdown (broken on Telegram mobile)
- Mixed currency labels (€ prefix on USD values, see ADR 005 / SK hynix bug)

## Implementation notes

Telegram supports HTML `<pre>...</pre>` for monospace blocks. Use for column-aligned content. Headers/emoji remain in regular text mode.

For Python: `update.message.reply_text(text, parse_mode=ParseMode.HTML)` with `<pre>` wrap for tables, leave headers outside `<pre>` for emoji rendering.
