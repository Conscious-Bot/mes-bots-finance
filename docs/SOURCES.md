# Sources Registry — Tier S/A/B

**Updated**: 13 May 2026
**Status**: Baseline empirique. Tiers provisoires jusqu'à 60j de données + Brier resolution active.

## Critical findings (empirical recon 30d)

- **62 signaux ingérés** sur 31 sources actives (39 configurées, **8 dormantes**)
- **Materiality_v2 coverage 16%** (10/62) → P1 dette: throughput rubric à améliorer
- **Tous credibilities à default 0.5** (range 0.40-0.55) → ledger inactif, KPI #2 critique
- **Bug data integrity**: `sources.last_signal_at` NULL pour majorité des sources malgré `n_signals > 0` → P1 dette: audit multi-code-paths d'insertion
- **SemiAnalysis ($65/mo)**: 0 signaux 30j → P0.7 investigation Gmail filter (paid sub gaspillé sinon)

## Tier methodology

| Tier | Critères | Action |
|---|---|---|
| **S** | Paid sub irremplaçable OU n_signals_30d ≥ 10 OU strategic reputation | Garder + monitor hebdo |
| **A** | n_signals_30d ≥ 2 + score_avg ≥ 3.5 | Garder + monitor mensuel |
| **B** | Single signal OR récente (<30j) OR score_avg < 3 | Probatoire — réévaluer J+60 |
| **INV** | Reputation haute mais 0 signaux | Investigate ingestion (Gmail filter / sub status) |

## Active registry (avec empirical data)

### Tier S — Irremplaçable / High volume
| Source | n_30d | score_avg | n_v2 | Notes |
|---|---|---|---|---|
| Short Squeez | 22 | 4.0 | 8 | High volume, 36% v2 coverage, ratio bruit/signal à mesurer rigoureusement |
| **SemiAnalysis** ($65/mo) | 0 | — | — | **INVESTIGATE Gmail filter — paid sub gaspillé** |

### Tier A — Signal régulier, bon score
| Source | n_30d | score_avg | n_v2 | Notes |
|---|---|---|---|---|
| Wall Street Rollup | 3 | 7.0 | 0 | High score, volume OK — strong A |
| Chamath Palihapitiya | 2 | 7.0 | 0 | High score, faible volume |
| Ben Thompson (Stratechery) | 1 | 7.0 | 0 | Strategic S, single-signal-30d |
| Adam Tooze (Chartbook) | 1 | 7.0 | 0 | Macro deep |
| Meilleurtaux Placement | 3 | 4.3 | 1 | FR PEA context |
| Coin Metrics SOTN | 1 | 6.0 | 0 | Crypto deep |
| MoneyRadar | 1 | 6.0 | 0 | Crypto |
| MoneyRadar Crypto | 1 | 6.0 | 0 | Crypto |
| The Defiant | 1 | 5.0 | 0 | Crypto |
| Marius (Invest in Quality) | 1 | 4.0 | 0 | Equity quality |
| Unusual Whales | 2 | 4.0 | 0 | Options flow |
| Charles-Elias (Le Grand Bain) | 1 | 4.0 | 0 | FR macro |
| DeFi Education | 1 | 4.0 | 0 | DeFi |
| Torsten Slok (Apollo) | 1 | 4.0 | 0 | Macro |

### Tier B — Probatoire / noise candidate
| Source | n_30d | score_avg | Notes |
|---|---|---|---|
| Investing.com | 4 | 1.8 | Noise candidate, volume sans qualité |
| Noahpinion | 3 | 2.0 | Low score malgré volume — borderline drop |
| Snowball Yoann | 2 | 2.5 | Faible signal |
| Substack newsletter | 2 | 4.5 | Generic Substack, à filtrer |
| Matt Stoller | 1 | 3.0 | Antitrust, irregulier |
| Doomberg | 1 | 1.0 | Faible signal sur 30j — re-eval J+60 |
| Lyn Alden | 1 | 1.0 | Faible signal sur 30j |
| Glassnode | 1 | 3.0 | Crypto on-chain, occasionnel |
| Irina Slav (energy) | 1 | 2.0 | Energy commentary |
| Colossus | 1 | 1.0 | Faible |
| Oaktree Email | 1 | 1.0 | Marketing |
| Substack Post Weekender | 1 | 2.0 | Digest |

### INV — Investigate ingestion (reputation high, signals zéro)
| Source | Tier intent | Action |
|---|---|---|
| **SemiAnalysis** ($65/mo) | S | Vérifier label Gmail "Newsletters" + filtre regex sender |
| Arthur Hayes | A | Substack envoie-t-il? Vérifier subscription active |
| Apollo Global Mgmt | A | Vérifier qu'agm@apollo.com est dans filter |
| Stratechery (email@stratechery.com) | S | Doublon avec Ben Thompson address? Dédupliquer |
| Substack Macro Compass (Alf) | A | Vérifier fréquence envoi |
| The Crypto Quant | B | Faible activité prob normal |
| Melody Wright | B | Faible activité prob normal |
| The Asianometry Newsletter | A | Substack mensuel, normal de 0 sur 30j |
| Bourseko | B | FR newsletter, vérifier sub |
| Hindenburg Research | A | Activist short, irregulier par nature |
| BlackRock | B | Marketing low signal |
| St. Louis Fed Research | A | Macro academic, irregulier |
| Federal Reserve Education | B | Educational, low signal |

## Roadmap activation (NON ACTIVES)

| Source | Coût | Trigger d'activation |
|---|---|---|
| FMP Starter | $14/mo | Month 4-6 si track record Brier <0.20 + signal density justifie |
| Polygon.io | $29/mo | Month 12+ si options chains réellement actionnables |
| TradingView | — | **REJETÉ** — pas d'API officielle publique, scrapers TOS-violating |
| CoinGecko Pro | $129/mo | Si > 100 calls/min besoin (actuellement free suffit) |

## Bugs / dette identifiée durant recon

1. **last_signal_at NULL malgré n_signals > 0** — audit multi-paths INSERT INTO signals
2. **materiality_v2 coverage 16%** — pipeline throughput insuffisant, audit cron `materiality_v2 1h`
3. **SemiAnalysis 0 signaux** — paid sub potentiellement gaspillé, investigation urgente
4. **Doublons sources Stratechery** — Ben Thompson <email@stratechery.com> vs Stratechery <email@stratechery.com> — dédupliquer

## Tier change log

### 2026-05-13 — Initial empirical baseline
- 31 sources actives documentées
- 13 sources INV (investigation ingestion)
- All credibilities at default 0.5 — ledger inactif jusqu'à Brier resolution
- Tier S réservé Short Squeez (volume) + SemiAnalysis (irremplaçable, à débugger)

## Review cadence

- **Hebdo**: Tier S — vérifier flow continue
- **Mensuel**: Tier A → graduation S ou démotion B
- **J+60**: Re-tier rigoureux sur Brier accumulé
- **J+90**: Drop list — sources 0 signal HIGH (impact≥4) 60j

