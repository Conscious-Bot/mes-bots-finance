# Thesis Candidates Queue

**Created**: 2026-05-15 Day 4 afternoon
**Purpose**: Pre-thesis structured workspace for candidates surfaced via external analysis or watchlist enrichment. Candidates remain here until they pass all 4 Gates AND observation window expires (post-J+28).

**Status**: Inputs only. NO candidate in this file is currently a logged thesis. Source: external IA conversation 2026-05-15 morning on AI chokepoints / picks-and-shovels.

---

## Workflow

1. Candidate surfaced → added to "Pre-screen" section below
2. Apply Gates 1-4 (in TODO.md "Thesis candidates queue" section)
3. If passes ALL gates AND observation window expired (>2026-06-10) → eligible for config.yaml watch tier add
4. Soak in watch tier 28 days minimum, observe signal/materiality output
5. Run /analyze_debate, /asymmetry → if conviction holds → /thesis_set + /thesis_premortem
6. Move from this file to active thesis tracker (DB table theses)

---

## Pre-screen — Priority A (test seriously post-J+28)

### Kioxia Corporation (285A.T)
- **Thesis**: NAND pure-play, post-IPO Dec 2024, sous-couvert ex-Asie. NAND ASP stabilized H2 2024, QLC/PLC pricing dynamics begin to diffuse from HBM/DRAM cycle.
- **Mispricing hypothesis**: market regroupe Kioxia avec Micron (US-listed, US-covered) mais Kioxia est pure-play NAND alors que Micron est DRAM + NAND + HBM blend. Valuation gap potentiel.
- **Gates status**: Gate 1 OK (~95% NAND revenue). Gate 2 TO VERIFY (need empirical P/E vs Micron/Western Digital). Gate 3 — invalidation: NAND ASP declines >15% 2 consecutive quarters, OR Samsung capacity expansion accelerates >20% YoY 2026. Gate 4 — mispricing thesis: under-coverage ex-Asia + recency IPO + investor framework "Micron is the NAND play" missing Kioxia.
- **Horizon**: 12-18 months
- **NEXT STEP** post-J+28: pull P/E + EV/EBITDA + FCF yield vs Micron, validate or reject pure-play valuation gap

### Mitsubishi Heavy Industries (7011.T)
- **Thesis**: gas turbines + nuclear + defense conglomerate, P/E ~half of GE Vernova for similar exposure mix.
- **Mispricing hypothesis**: GEV rallied +300% on AI infra narrative, MHI under-covered ex-Asia. Same turbine backlog dynamics 2028-2029, same nuclear renaissance exposure, half the multiple.
- **Gates status**: Gate 1 NOT pure-play (conglomerate — adjustment needed in thesis weighting). Gate 2 OK on relative valuation. Gate 3 — invalidation: turbine order backlog declines, OR Trump 2.0 reduces tariff barriers benefiting Chinese alternatives. Gate 4 — clear mispricing if pure-asia coverage explains the discount.
- **Horizon**: 18-36 months
- **NEXT STEP** post-J+28: segment-level revenue breakdown, multiple comparison adjusted for non-power conglomerate drag

### Stevanato Group (STVN)
- **Thesis**: borosilicate Type I vials for GLP-1 + biologics. Oligopole Schott (privé) + Stevanato + Corning Valor + AGC. Capacity at 95%+ utilization industry-wide. FDA qualification times 5+ years = moat structurel.
- **Mispricing hypothesis**: market focuses on Lilly/Novo (35x P/E priced perfection); Stevanato as undercovered upstream container supplier with 5-year switching costs.
- **Gates status**: Gate 1 strong (~80% revenue pharma containers). Gate 2 TO VERIFY post-2024 rally. Gate 3 — invalidation: GLP-1 demand stalls/peaks, OR alternative container tech (plastic biocompatible) regulatory approval. Gate 4 — Lilly/Novo pricing in their margins, not their suppliers'.
- **Horizon**: 12-24 months
- **NEXT STEP** post-J+28: validate current multiple — if STVN traites >25x forward, mispricing thesis weakens

---

## Pre-screen — Priority B (qualification needed)

### Ypsomed (YPSN.SW), Lasertec (6920.T), Ferrotec (6890.T)
Same workflow, lower priority. See TODO.md.

---

## Pre-screen — Priority C (watch only, NOT to add to config.yaml)

DEME (DEME.BR), NKT (NKT.CO), Momentive (MTUS), Centrus (LEU), MP Materials (MP). These names have either (a) high recent volatility, (b) historical playbook risk (REE dumping), or (c) thesis dependence on hyperscaler capex maintaining at current pace (DeepSeek-style efficiency cannibalization tail risk).

---

## Anti-pattern checklist

Before promoting any candidate from this file to config.yaml, verify NONE of these apply:

- [ ] Thesis relies primarily on "narrative is undercovered" without specific mispricing math
- [ ] Multiple is already in top 40% of peer set (chokepoint thesis already priced)
- [ ] Invalidation is "narrative deteriorates" (non-falsifiable)
- [ ] You discovered this candidate in a 4h+ session (cognitive inflation risk)
- [ ] You haven't articulated why Mr Market is wrong in <3 sentences
- [ ] The candidate is among 5+ names from same conversation (batch-logging risk)

**ALL boxes above must be empty before any add to config.yaml.**

---

## Carry-forward

Candidates listed here represent intellectual matter from 2026-05-15 conversation, NOT decisions. Re-review this file 2026-06-15 (post-J+28 + 5 days buffer). Apply gates with fresh eyes. Reject 70%+. Promote 0-3 max.

