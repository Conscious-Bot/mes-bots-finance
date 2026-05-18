# ADR 008 - LLM Cascade Architecture (Haiku/Sonnet/Opus tier routing)

**Date**: 2026-05-18 (Day 12 extended)
**Status**: Active (retroactive, operational since Day 1 substrate 2026-05-11)
**Deciders**: Olivier Legendre
**Related**: ADR 004 (USD canonical), ADR 006 (Process discipline R19), ADR 007 (Bidirectional thesis tracker)

## Context

The bot performs heterogeneous LLM workloads with sharply different complexity:

- **High-volume classification**: signal_type tagging + materiality phase-1 rubric on every newsletter signal (50-100/jour at scale)
- **Medium-complexity synthesis**: digest writing 2x/jour, materiality_v2 chained scoring, /brief 6-section synthesis, multi-round debate
- **Low-volume deep reasoning**: /risk_check pre-trade, /thesis_premortem, /analyze deep fiche, asymmetry math counter-biais

Single-model approaches break either cost or quality:

- **All-Haiku**: cheap (~$3-5/mo at observed volume) but synthesis/reasoning quality insufficient for asymmetry math, multi-round debate, deep fiches
- **All-Sonnet**: middle ground (~$30-50/mo) but high-volume scoring on 50+ signals/jour eats budget
- **All-Opus**: gold standard (~$100-200/mo) but 15x Haiku cost for classification tasks that don't need depth

Solo build at $50/mo Anthropic budget = single-model approaches break Path 6 narrative ("$15/mo bot doing institutional-grade work" differentiation moat).

## Decision

**Three-tier cascade routing by task complexity matrix.**

Canonical tier mapping (config.yaml::tiers section):

| Tier | Model | Pricing (input/output per Mtok) | Tasks |
|------|-------|--------------------------------|-------|
| extract | Haiku 4.5 | $1.00 / $5.00 (cached $0.10) | signal_type Haiku classify, materiality rubric phase-1, Gmail extraction, EDGAR parsing |
| enrich | Sonnet 4.6 | $3.00 / $15.00 (cached $0.30) | materiality_v2 chained scoring, digest 2x/jour synthesis, /brief, multi-round debate |
| synthesize | Opus 4.7 | $15.00 / $75.00 (cached $1.50) | /risk_check, /thesis_premortem, /analyze deep fiche, asymmetry math counter |

Routing principle: **tier by complexity matrix, NOT by recency or hype**.

Decision matrix for new LLM features:

1. Volume > 10 calls/jour AND output structure simple (classification, extraction) -> Haiku
2. Output requires synthesis of 3+ inputs OR moderate reasoning chain -> Sonnet
3. Output drives risk decisions (sizing, stop, thesis invalidation, panic prevention) -> Opus
4. Adversarial multi-step reasoning (premortem, asymmetry counter-biais) -> Opus

Implementation: shared/llm.py::_resolve_model(tier) returns (model_id, pricing_dict). All LLM calls route through shared/llm.py::call(tier, prompt). Cost observability via _compute_cost() returning USD per call, aggregated by /llm_costs handler + /cost_trajectory weekly cron.

## Alternatives rejected

### 1. Single-model all-Sonnet
Quality acceptable for most tasks. Cost ~3x observed (~$45/mo vs $15/mo cascade). Breaks $50 budget headroom. Loses Path 6 differentiation. **Rejected: cost.**

### 2. Single-model all-Opus
Quality maxed but ~$150-200/mo at observed volume. Breaks $50 budget by 3-4x. Solo build economically not viable. **Rejected: cost prohibitive.**

### 3. Dynamic cascade with fallback (Sonnet fails -> upgrade Opus)
Sophisticated quality routing but unpredictable budget (Opus calls spike unannounced). Harder to forecast /cost_trajectory. Adds retry-logic + fallback-detection complexity to shared/llm.py. **Rejected: budget predictability + ops simplicity > marginal quality gain.**

### 4. Multi-provider hedging (Haiku + GPT-4o-mini + Mistral)
Theoretical cost reduction via competitive pricing. But: multi-API auth, multi-pricing tables, prompt drift between vendors, harder testing infrastructure, single-vendor lock-in trade vs ops complexity. **Rejected: scope creep, marginal cost savings < ops complexity.**

### 5. Embedding-only routing (BGE semantic similarity to past tier decisions)
Implementable since BGE-small-en-v1.5 already local (echo clustering). But: adds 2nd routing layer, mixes concerns with semantic dedup, harder to audit. Static decision matrix sufficient and more legible. **Rejected: complexity > value.**

## Empirical validation (Day 12 close, ~7 jours operational)

- **Observed cost**: $0.50/jour
- **Projected MTD**: $15/mo
- **Budget**: $50/mo
- **Headroom**: 70% (GREEN per /cost_trajectory)

Estimated volume distribution (verify via /llm_costs runtime):
- Haiku: ~95% of calls (signal scoring + ingestion classification)
- Sonnet: ~4% of calls (2 digests/jour + materiality_v2 + /brief)
- Opus: ~1% of calls (~5-10 /risk_check ou /thesis_premortem per semaine)

Estimated cost distribution (skewed by per-call cost):
- Haiku: ~30-40% of spend (volume)
- Sonnet: ~35-40% of spend (per-call cost compensates lower volume)
- Opus: ~25-30% of spend (low volume but 15x Sonnet per-call)

## Trade-offs

### Quality risk - Haiku misclassification cascade
If Haiku mis-tags signal_type, downstream materiality_v2 (Sonnet) wastes cycles on irrelevant scoring.
**Mitigation**: chained architecture (Haiku classify -> Sonnet score), monitored via materiality_v2 coverage KPI (100% as of Day 2 marathon, P1 dette closed).

### Cost risk - Opus overuse
Opus tasks blow budget if overused (premortem on every thesis instead of high-impact only).
**Mitigation**: /llm_costs handler + weekly /cost_trajectory cron Sun 22:00 + auto-alert via notify if MTD > 90% budget. Decision matrix point 4 narrows Opus eligibility.

### Model drift - Anthropic pricing changes
Already happened during Phase 1-2 (Sonnet 3.5 -> 4.6, Opus 4 -> 4.7).
**Mitigation**: config.yaml::pricing configurable per model, /llm_costs recompute uses current config. Monthly check baked into KPI review.

### Vendor lock-in - Anthropic single-source
If Anthropic API outage -> whole pipeline blocked (digest, scoring, synthesis all stop).
**Mitigation**: documented in PROCEDURE_URGENCE.md Scenario 5. No multi-vendor escape implemented (rejected alternative 4). Accepted risk for solo build economics.

## Cross-references

- config.yaml::tiers + config.yaml::pricing (canonical model + cost configuration)
- config.yaml::models (legacy aliases: signal_scoring, synthesis, deep_analysis - kept for backwards compat)
- shared/llm.py::_resolve_model, shared/llm.py::call, shared/llm.py::_compute_cost
- intelligence/signal_classify.py (Haiku tier)
- intelligence/materiality_v2.py (Sonnet tier, chained after signal_classify)
- intelligence/digest.py (Sonnet tier)
- intelligence/morning_brief.py (Sonnet tier)
- bot/handlers/llm_costs.py + intelligence/cost_trajectory.py (observability)
- ADR 004 (USD canonical migration - cost monitoring USD primary)
- ADR 006 (process discipline - prompt changes require R19 v5 gates)
- ADR 007 (bidirectional thesis tracker - /risk_check Opus is the discipline mechanism)
- PHILOSOPHY.md (principe "Cascade LLM: Haiku volume, Opus raisonnement structuré")
- FICHE_TECHNIQUE.md (stack contraintes - Anthropic Claude API cascade)

## Path 5/6 narrative role

Closes the **economic sustainability** axis of the audit narrative:

> "Comment ce bot fait du travail institutional-grade pour $15/mo ?"

Answer: cascade routing. Each LLM call goes to the cheapest tier capable of producing decision-grade output for that task. Volume tasks (Haiku) subsidize reasoning tasks (Opus). 70% budget headroom even at observed volume = scalable to 3x current load without breaking economics.

This is the differentiation moat versus:
- Substack subscribers paying $20/mo for ONE newsletter
- AI-coding-IDE subscriptions $20-200/mo for one workflow
- Institutional research seats $1000s/mo

## Status

**Active since 2026-05-11** (Day 1 substrate phase). **Formalized 2026-05-18** (Day 12 extended, retroactive ADR pattern after ADR 007).

R19 v3 gates: ruff + pytest 270 GREEN. Docs only.

## Open questions (deferred)

- **Q1**: /analyze default tier - currently Opus for "deep fiche", Sonnet for "quick". Empirically /analyze used ~3x/semaine. Formalize threshold rule (e.g. "Opus only if conviction >= 4 OR position size > 3% portfolio") in future ADR.
- **Q2**: Prompt caching strategy - Anthropic cached_input pricing 10x cheaper. Currently used implicitly via repeated system prompts. Formalize cache key strategy if MTD spend approaches 50% budget. Defer post-J+30.
- **Q3**: Haiku 4.5 -> Haiku 5 transition policy - when Anthropic ships next gen, A/B test or auto-upgrade ? Defer to event trigger.
