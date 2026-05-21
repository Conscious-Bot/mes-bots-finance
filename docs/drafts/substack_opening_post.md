# How I caught a 1,600x bug in my personal investing tool

*And why the discovery method matters more than the bug.*

---

## The bug

Nine days ago, my personal investing dashboard told me I had paid **$0.76 per share** for SK hynix. The actual price was **$1,216**. A 1,600x error, sitting quietly in production, contaminating my P&L for over a week.

I caught it by accident. The morning brief showed SK hynix up +167,195%. I should have caught it the same day. I didn't, because the rest of my portfolio displayed sane numbers, so my eye glossed over the anomaly as a display glitch.

The fix took six minutes to write. The audit that revealed *why* the bug existed took six hours. That asymmetry is the actual point of this post.

---

## Context: why I built this

I have two asymmetric biases in my investing, both expensive, both empirically documented:

1. **I sell winners too early.** PLTR, NVDA — I've trimmed both into multi-baggers because mean-reversion intuitions overrode my own thesis.
2. **I don't sell crypto at indicator tops.** Greed override.

Most investing tools optimize for *information access*: news feeds, screeners, charts. I don't need more information. I need mechanized discipline that fires when my biases would otherwise dominate.

So I built one. Closed-loop self-learning system: it ingests newsletters and filings, scores their materiality, tracks every prediction with a measurable horizon, computes Brier calibration from outcomes, and forces structured thinking before any buy/sell via a `/risk_check` command that won't let me lie to myself about why I'm doing what I'm doing.

Stack: Python, SQLite, APScheduler, Telegram. No Postgres, no Redis, no FastAPI, no cloud. Runs on my laptop. The boring stack is the point — every layer of infrastructure that doesn't earn its complexity is a tax on the only thing that matters: signal-to-discipline ratio.

---

## The bug, properly

`positions.avg_cost` is the column that stores what I paid per share. In my code, four different display handlers wanted to convert that value to USD for display.

The comments on top of those handlers, written eight days before the bug surfaced, all said the same thing:

> `avg_cost` is stored in **native currency** (JPY for `.T` tickers, KRW for `.KS`, EUR for `.PA`, USD otherwise). Multiply by `fx_native_to_USD` for display.

So all four handlers did exactly that:

```python
avg_cost_usd = avg_cost * fx_native_to_USD
```

For my SK hynix position, that became:

```python
avg_cost_usd = 1043.06 * 0.000727  # KRW→USD = $0.76
```

The bug is obvious in hindsight. The reality is that `avg_cost` was **never** stored in native currency. The broker import script, written by someone (me) on a different week with different assumptions, stored it in EUR. The "native storage" claim in the comments was **aspirational** — a design intent that never landed in production code.

So I had EUR-stored values being multiplied by native→USD rates as if they were KRW. SK hynix: $1,043 EUR became $0.76 "USD." Shin-Etsu Chemical: €38.52 became $0.21. Lasertec Corp: €208 became $1.14.

Six months of compounded confidence in my dashboard, undermined by a comment that lied.

---

## The audit method

Here's the part that generalizes.

When I sat down to fix the bug, the obvious move was to flip a few signs in the four broken handlers. Native → EUR canonical, multiply differently, ship the patch. But I wasn't yet sure which way to flip. The comments said "native". The morning brief disagreed. The other handlers used different conventions inconsistently. Which one was the actual truth of the database?

The textual evidence was contradictory. So I derived truth from data instead.

I ran a single query: for each of my 21 active positions, divide the stored `avg_cost` by the current live price in EUR. If `avg_cost` was native-stored, the ratios would cluster on the native→EUR fx rate (around 0.005 for JPY tickers, 0.0006 for KRW, 1.17 for USD). If `avg_cost` was EUR-stored, all ratios across all native currencies would cluster around 1.0.

The empirical output:

| Ticker | Native | avg_cost | live_EUR | ratio |
|---|---|---|---|---|
| 000660.KS | KRW | 1043.06 | 1028.34 | 1.014 |
| 4063.T | JPY | 38.52 | 37.35 | 1.031 |
| 6920.T | JPY | 208.22 | 192.33 | 1.083 |
| ASML.AS | EUR | 1309.00 | 1249.00 | 1.048 |
| AMD | USD | 386.34 | 355.25 | 1.087 |
| ... (21 total) ... |||||
| **Range** | mixed | varied | varied | **[0.937, 1.147]** |

All 21 ratios near 1.0, regardless of native currency. **EUR canonical confirmed**, definitively. Had storage been native, KRW would have ratio 169,200%, JPY 18,293%. Instead, tight cluster around 1.0.

The data settled the question that comments couldn't.

---

## What I codified

I wrote this finding up as ADR 005 (Architecture Decision Record #5) in the project. Then I added Lesson 15 to my CONVENTIONS.md, which is the file I read at the start of every session to remember what I've already learned:

> **Lesson 15 — Empirical verification applies beyond SQL.**
> 
> Storage convention claims in comments are documentation of *intent at time of writing*; the actual storage IS what storage IS. When auditing a system claim, derive truth from **data**, not from **text**.

The full lesson includes a tooling pattern — the cross-currency ratio audit, generalized — so the next time I read a comment that asserts a data convention before modifying logic depending on it, I have a 10-line script ready to verify rather than trust.

---

## Why I'm writing this

Twenty days from now, 45 predictions I've registered in this system resolve simultaneously. On June 10, 2026, I'll publish the Brier score — the empirical measure of whether my conviction-weighted predictions matched reality. Either mechanized discipline beats my gut over 12 months, or it doesn't, and the data will tell.

The KPI dashboard updates every Sunday at 22:30 Paris time and posts itself to my Telegram. The track record is the thesis.

There's a second reason worth naming. The discipline I'm trying to mechanize for my own investing is the same discipline I should have applied to my own engineering. The bug existed because I trusted my own past comment. Comments are a form of self-deference. Self-deference compounds badly over months.

If you're building your own tooling — investing or otherwise — subscribe to see the Brier number on June 10, whether it vindicates the method or kills it.

---

*Next post: the bidirectional discipline framework — why catching yourself selling winners too early is a different problem than catching yourself holding losers too long, and why most "stop-loss" tools only solve half of it.*

