# Sources Registry — Tier S/A/B

**Updated**: 13 May 2026 (refresh post 100% materiality_v2 coverage)
**Status**: Empirical baseline ANCRÉ. Tier assignments dérivés du composite materiality moyen.

## Méthodologie

Tier dérivé du **composite_avg materiality** sur 30j (rubric impact/reversibility/time scoré par Sonnet) :
- **Tier S** : composite_avg ≥ 5.5 OU paid sub irreplaceable
- **Tier A** : composite_avg 4.0-5.5
- **Tier B** : composite_avg 3.0-4.0 OU volume-noise pattern (haut n / bas composite)
- **Drop candidate** : composite_avg < 3.0 sur ≥3 signaux

## Tier S — Empirical (composite ≥ 5.5)

| Source | n_30d | composite_avg | impact_avg | Notes |
|---|---|---|---|---|
| **Adam Tooze (Chartbook)** | 1 | 7.0 | 4.0 | Macro deep, single but max impact |
| **Chamath Palihapitiya** | 2 | 6.4 | 3.5 | Tech/finance, signaux denses |
| **Wall Street Rollup** | 3 | 6.0 | 3.0 | High volume + high score — empirical Tier S |
| **Coin Metrics SOTN** | 1 | 6.0 | 3.0 | Crypto on-chain rigor |
| **SemiAnalysis** ($65/mo) | 1 | 5.8 | 3.0 | Vindication paid sub. EDA Primer just ingested ✓ |

## Tier A — Solid (composite 4.0-5.5)

| Source | n_30d | composite_avg | Notes |
|---|---|---|---|
| Ben Thompson (Stratechery) | 1 | 5.2 | Strategic S, empirical A on first signal |
| MoneyRadar Crypto | 1 | 5.2 | Crypto detail |
| Meilleurtaux Placement | 4 | 4.75 | FR PEA context, regular |
| Glassnode | 1 | 4.6 | Crypto on-chain |
| Matt Stoller | 1 | 4.2 | Antitrust |
| MoneyRadar | 1 | 4.0 | Crypto |

## Tier B — Probatoire ou volume-noise

| Source | n_30d | composite_avg | Notes |
|---|---|---|---|
| Investing.com | 5 | 3.92 | Volume sans qualité — noise candidate |
| **Short Squeez** | **22** | **3.69** | **EMPIRICAL DEMOTION: was Tier S on volume, reality = noise-at-scale** |
| Charles-Elias (Le Grand Bain) | 1 | 3.6 | FR macro |
| DeFi Education | 1 | 3.6 | DeFi |
| The Defiant | 1 | 3.6 | Crypto |
| Torsten Slok (Apollo) | 1 | 3.6 | Macro, demoted from intent A |
| Substack newsletter | 3 | 3.53 | Generic, à filter |
| Unusual Whales | 2 | 3.5 | Options flow |
| Noahpinion | 3 | 3.0 | Low composite malgré volume — borderline drop |

## Drop candidates (composite ≤ 2.4)

| Source | n_30d | composite | Notes |
|---|---|---|---|
| Snowball Yoann | 2 | 2.4 | Faible matérialité |
| Arthur Hayes | 1 | 2.4 | First signal low — re-eval J+60 |
| Doomberg | 1 | 2.4 | Re-eval J+60 |
| Marius (IIQ) | 1 | 2.4 | |
| Substack Post Weekender | 1 | 2.4 | Digest auto |
| Irina Slav (energy) | 1 | 2.4 | Energy commentary |
| Lyn Alden | 1 | 2.4 | Faible signal pas représentatif (1 signal) |
| Colossus | 1 | 2.4 | Marketing |
| Oaktree Email | 1 | 2.4 | Marketing |

## INV — Investigation needed (0 signaux ingérés)

Reste 13 sources avec 0 signals 30j. Hypothèses :
- Substack publish weekly/monthly (normal)
- Federal Reserve / BlackRock = marketing low-flow
- Hindenburg = activist short irrégulier par nature

À monitorer 60j sans action.

## Roadmap activation (non-actives)

| Source | Coût | Trigger |
|---|---|---|
| FMP Starter | $14/mo | Month 4-6 si track record Brier <0.20 justifie |
| Polygon.io | $29/mo | Month 12+ si options chains réellement actionnables |
| TradingView | — | REJECTED — pas d'API officielle |
| CoinGecko Pro | $129/mo | Si free 30/min plafond atteint |

## Changelog des actions

### 2026-05-13 (Day 2 marathon close)
- **Dedup**: Stratechery (Ben Thompson canonical) + Apollo (Torsten Slok canonical)
- **Backfill**: last_signal_at recomputed pour 27 sources
- **Materiality_v2 coverage**: 16% → 100% (51 signaux backlog scorés)
- **Architecture**: ingest_gmail_job chains materiality_v2 immédiat post-ingestion
- **SemiAnalysis**: paid $65/mo activé, EDA Primer ingéré (composite 5.8)

### Empirical promotions / demotions (vs initial baseline 2026-05-13 morning)
- **Promoted Tier S empirical**: Wall Street Rollup (composite 6.0 sur 3 signaux confirme volume + qualité)
- **DEMOTED from Tier S**: Short Squeez (22 signals mais composite 3.69 → noise-at-scale, pas signal-at-scale)
- **Confirmed Tier S strategic**: SemiAnalysis ($65/mo paid, premier signal composite 5.8)

## Review cadence

- **Hebdo**: Tier S — vérifier flow + alert si composite drift >1.0
- **Mensuel**: Tier A → graduation S ou démotion B selon composite trend
- **J+60**: Re-tier rigoureux avec Brier resolutions accumulées
- **J+90**: Drop list — sources < 2 signals OR composite_avg < 2.5 sustained

