# Glossary - mes-bots-finance

**Purpose**: project-specific terminology for Path 5/6 readability.

---

## Core concepts

**Brier score**: Quadratic loss measuring calibration of probabilistic predictions. (probability - outcome)^2. Range [0,1], 0 = perfect, 0.25 = always 0.5, 1 = catastrophically wrong. Used for monthly source credibility recalibration.

**Credibility ledger**: Per-source trust score in [0,1]. Updated based on prediction outcomes (correct +0.03, incorrect -0.05, asymmetric penalty). Default 0.5 for new sources.

**Materiality composite**: 0-10 score from 3-axis rubric: impact_magnitude (1-5), reversibility (1-5, inverted), time_to_realization (urgent/medium/slow/na). Formula: (imp*0.5 + (6-rev)*0.3 + time_factor*0.2) * 2. Replaces monolithic score with explicit reasoning.

**Echo cluster**: Group of semantically similar signals detected via BGE-small-en-v1.5 embeddings + cosine similarity. Prevents over-weighting same narrative repeated across sources.

**Half-life**: Per-source decay rate of signal relevance in days. Computed empirically. Used for time-weighted aggregation.

**Signal type**: Haiku-classified label: catalyst (event-driven), data (macro print), opinion, narrative (slow-burn theme), noise. Determines downstream processing.

**Thesis (bidirectional)**: Investment hypothesis with explicit entry / target_partial / target_full / stop_price. Bidirectional means both anti-vend-trop-tot (force exit at targets) AND anti-tient-trop-long (force exit at stop) discipline.

**Asymmetry ratio**: Upside_to_target / |downside_to_stop| at current price. Verdicts: STRONG_RUN (>3), FAVORABLE (1.5-3), BALANCED (0.7-1.5), UNFAVORABLE (0.3-0.7), FLIPPED (<0.3), STOP_BREACHED, TARGET_HIT.

**Pre-mortem**: Imagined future failure analysis written BEFORE trade entry. Forces enumeration of how thesis could be wrong.

**Panic sell**: Heuristic: full_exit decision on a thesis BEFORE triggered_partial_at OR triggered_stop_at. Indicates exit not driven by thesis-defined triggers.

---

## Behavioral framework

**Bias asymetrique**: Olivier's documented pattern: sells stock winners too early (PLTR @9, NVDA @130) AND fails to sell crypto at indicator tops (FOMO on BTC/ETH).

**Bias tags**: Manual or auto-attached labels on decisions: regret_avoidance, fomo, anchor_bias, recency_bias, confirmation_bias. Used for bias_review retrospectives.

**Risk_check**: Pre-trade Opus call that ingests journal + bias history + thesis + current state, outputs structured risk assessment. Forces deliberate pre-commit reflection.

---

## LLM cascade

**Tier extract (Haiku)**: Cheap, high-volume tasks: signal_type classification, entity extraction, basic scoring. ~$0.0005/call.

**Tier enrich (Sonnet)**: Mid-cost reasoning: materiality_v2 rubric, digest narrative, signal scoring. ~$0.04/call.

**Tier reasoning (Opus)**: Expensive structured analysis: risk_check, multi-round debate, decision pre-mortem. ~$0.10-0.30/call. Used sparingly.

---

## Pipeline stages

**Substrate**: DB schema (15 tables), config.yaml, .env secrets.

**Ingestion**: Gmail OAuth (gmail 1h, max=50), EDGAR 8-K (cron 6:30), FRED macro (calendar 5h), yfinance (price_monitor 15min), CoinGecko (crypto 10h), insider Form 4 (insider 6h).

**Entonnoir**: Filter+score pipeline: signal_classify Haiku, materiality_v2 Sonnet chained post-ingest, echo cluster dedup.

**Synthesis**: Multi-round debate (Opus), /analyze deep fiche, risk_check.

**Appropriation**: Position book tracking, journal auto-resolve, bias_tagger, pre-mortem.

**Restitution**: /brief (6 sections), /digest (Sonnet narrative 2x/day), /kpi_status, /cost_trajectory.

---

## KPIs

**KPI #2 NON-NEG**: 5+ predictions resolues rolling 28d. Breach action: stop 5d build + force-use.

**KPI #3**: Brier rolling 90d < 0.20. Action if >0.25: alert + revue methodo.

**KPI #4**: 0 panic sells thesis core. Action if 1+: pause + bias analysis.

**KPI #5**: 100% decisions materielles journalisees (reasoning 30+ chars + bias_tags). Action if <90%: no new thesis until backfill.

**KPI #6**: TWR vs SPY/QQQ 12M > -5pp. Not yet implemented (requires positions integration).

---

## Sources tiers

**Tier S**: composite_avg 5.5+ OR paid sub irreplaceable. Examples: Adam Tooze, Chamath, Wall Street Rollup, Coin Metrics, SemiAnalysis ($65/mo).

**Tier A**: composite_avg 4.0-5.5. Solid signal, monthly monitor.

**Tier B**: composite_avg 3.0-4.0 OR volume-noise pattern (Short Squeez 22 signals avg 3.69).

**Tier INV**: Reputation high but 0 signals 30d. Investigate ingestion.

**Drop candidate**: composite_avg <2.5 sustained sur 3+ signals.

---

## Path 5/6 strategy

**Path 5**: Acquihire ($200K-$1M, 18-24mo). Target: family offices, RIA, fintech B2B.

**Path 6**: Substack + prosumer subscription ($100K-500K/an, 24-36mo). Requires 12-24mo public track record.

**High Standard Mode**: Operating posture post 13 mai pivot. STOP velocity-shipping. Every ship: tests + cost modeled + observability + failure modes + doc.

**4 Dimensions roadmap**: Dim 1 Solidification technique (DONE) / Dim 2 Track record mesure (ACTIVATED) / Dim 3 Depersonnalisation (month 6+) / Dim 4 Positionnement public (month 12+).

---

## Architectural primitives

**WAL mode**: SQLite Write-Ahead Logging. N readers + 1 writer concurrent. Activated 13 mai.

**Bitemporal ledger**: Append-only history with valid_from/valid_to (world time) + created_at (transaction time). Proposed in ADR 001. Implementation deferred to juin 2026.

**Atomic insert pattern**: INSERT INTO signals + UPDATE sources.n_signals + last_signal_at in same transaction, try/except IntegrityError for duplicate gmail_id. Reference: shared/storage.py:insert_raw_signal.

**Chained ingestion**: ingest_gmail_job triggers materiality_v2 immediately post-INSERT. Reduces latency from 0-60min to seconds.
