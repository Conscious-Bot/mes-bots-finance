# /risk_check + /analyze v2 — Roadmap improvements

**Status**: Design phase, implementation post-J+30 (observation mode discipline)
**Origin**: Day 13 (2026-05-19) discussion post GEV test
**Trigger**: 11 juin 2026 (post KPI #2 batch resolution) ou earlier si KPI #2 GREEN forecast

---

## #0 CRITICAL — Newsletter signal injection (foundational)

**Gap diagnosed**: `/analyze` and `/risk_check` outputs do NOT cite newsletter signals from the signals table. The harvest (66 signals/30d, 100% materiality coverage, 27 active sources tier S/A/B) accumulates but doesn't flow into decision-time analysis.

**This breaks PHILOSOPHY.md core principle**: "le bot n'est plus le meme outil au bout de 6/12/24 mois" requires that accumulated context flows into decisions, which it currently doesn't for the 2 main decisional handlers.

**Fix**:
- `/analyze TICKER` auto-queries signals table: top N signals on ticker last 30d, sorted by materiality_v2 * source_credibility_tier
- Inject top 5-10 as structured context in prompt
- Dedup via echo cluster IDs
- Output cites: "Recent signal weight: SemiAnalysis Tier S 0.78 bullish HBM4 + 2 other Tier S/A sources confirming"
- Same pattern for `/risk_check` with extra weight on bear-side signals (anti-confirmation bias)

**Effort**: 6-8h (prompt eng + storage query helpers + output formatting)
**Priority**: P0 — foundational, all other improvements presuppose this loop closes

---

## 🧠 BRILLANT (qualitative leaps)

### #1 Reverse stress test (bidirectional, ADR 007 incarnation)
> "If GEV ramps to $1,500 (+50%), based on historical pattern PLTR/NVDA you have ~70% prob of selling at $1,300 (lock +30% vs ride to thesis target). Cost of sell-too-early bias: -$YY."

Effort: 2h (pure prompt eng + bias_tagger historical patterns query)
Priority: P1 — narrative pillar Path 5/6 (unicité différentiatrice)

### #2 Inverted framing — "What changes the verdict?"
> "What turns CONDITIONAL → GO: (a) thesis upgrade to long c4, (b) stop defined, (c) size $1,000, (d) bucket formalized. Time to satisfy: 30-45 min journaling."

Effort: 1h (prompt eng)
Priority: P1 — action gap closed

### #3 Historical analogues injection (memory loop)
> "Pattern match: similar 'add to existing thesis' on TICKER 2026-03-15. fomo+thesis_creep flagged then too. Outcome 60d later: -12%."

Effort: 4-6h (similarity search past risk_checks + outcomes table join)
Priority: P2 — requires PIT bitemporal (ADR 001) for clean implementation

---

## 📐 PRÉCIS (quantitative rigor)

### #4 Multi-scenario stress with probabilities
> "Stress A (30% prob): AI capex digestion → -X%. Stress B (20%): tariff escalation → -Y%. Weighted expected drawdown: -Z%."

Effort: 2-3h (prompt eng + Sonnet weighting call)
Priority: P1 — Brier-trackable, professional grade

### #5 Cluster sizing math explicit
> "Power_for_AI bucket: 0%. GEV $1,500 + ENR.DE planned $1,600 + 7011.T existing $2,200 = 13.4%. Cap 10% → max GEV today $400."

Effort: 2h (thesis_buckets table + positions math)
Priority: P1 — addresses real gap revealed in GEV test

### #6 Calibrated probability output for the trade
> "P(profitable @ 6mo | thesis + biases + regime): 42% vs 55% baseline. EV proposed: +$320. EV if override $1,500: -$180."

Effort: 4h (LLM probability estimation + post-decision tracking schema)
Priority: P2 — Brier-loop integration

---

## 🪞 CLAIR (legibility)

### #7 At-a-glance summary header
3-line tldr avant le détail: verdict + counter-proposal + key flag.

Effort: 30 min (template change)
Priority: P1 — instant clarté gain

### #8 Track record context line
> "Discipline streak: 0 overrides last 5 risk_checks (90d). Maintain by following counter-proposal."

Effort: 1h (risk_check_history aggregation)
Priority: P2

### #9 ASCII decision tree visualization
Path-dependence explicit instead of prose.

Effort: 1h (prompt template)
Priority: P3 — nice-to-have, lower leverage

---

## Implementation order post-J+30

1. **#0 newsletter signal injection** (P0, foundational, 6-8h)
2. **#7 header summary** (P1, 30 min, instant gain)
3. **#1 reverse stress test** (P1, 2h, narrative pillar)
4. **#2 inverted framing** (P1, 1h)
5. **#4 multi-scenario stress** (P1, 3h)
6. **#5 cluster sizing math** (P1, 2h)
7. **#9 ASCII decision tree** (P3, 1h)
8. **#3 historical analogues** (P2, 4-6h, requires ADR 001)
9. **#6 calibrated probability** (P2, 4h)
10. **#8 track record context** (P2, 1h)

**Total effort**: ~28h cumulative for full v2 upgrade.
**Phased rollout**: ship in batches of 2-3 improvements per session post-J+30.

---

## Cross-references

- ADR 007 Bidirectional Thesis Tracker (foundational mechanism)
- PHILOSOPHY.md philosophical loop principle
- KPI #5 (decisions journalisées)
- Path 5/6 narrative dimensions 1-2 (technique solidification + track record mesure)
