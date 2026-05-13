# Data Lineage - mes-bots-finance

**Updated**: 13 May 2026

Visual flow from raw inputs to user-facing restitution. Mermaid renders natively in GitHub markdown.

## Main pipeline (Gmail-centric)

```mermaid
flowchart TB
    subgraph EXT[External Sources]
        G[Gmail Newsletters]
        E[SEC EDGAR 8-K]
        F[FRED macro 32 series]
        Y[yfinance 215 tickers]
        C[CoinGecko crypto]
        I[Insider Form 4]
    end

    G -->|gmail 1h max=50| G2[gmail_.fetch_emails]
    E -->|8k_scan 6:30| E2[edgar.scan_recent]
    F -->|calendar 5h| F2[fred.refresh_events]
    Y -->|price_monitor 15min| Y2[prices.fetch_daily]
    C -->|crypto 10h| C2[crypto.zone_check]
    I -->|insider 6h| I2[insider.scan_form4]

    G2 --> FILT{_is_onboarding_noise / _is_welcome_signal}
    FILT -->|filtered| DISC[Discard counter]
    FILT -->|valid| INS[storage.insert_raw_signal atomic]
    E2 --> INS
    F2 --> INS

    INS --> SIG[(signals table)]
    INS -->|chain| MAT[materiality_v2 Sonnet]

    SIG -->|signal_classify 30min Haiku| ST[signal_type]
    SIG -->|echo_clusters 1h BGE| EC[signal_embeddings]
    SIG -->|materiality_boost 1h| MB[materiality_boost factor]

    MAT --> SIG_ENR[(signals enriched)]
    ST --> SIG_ENR
    EC --> SIG_ENR

    SIG_ENR -->|/brief| BRF[Telegram 6 sections]
    SIG_ENR -->|daily_digest 7+19h| DIG[Unified narrative]
    SIG_ENR -->|score>=6| PRED[register_prediction horizon by signal_type]

    PRED --> P[(predictions table)]
    P -->|resolve cron 9:00| RES[outcome + return_pct + brier_score]
    RES -->|brier_recal 1st 6h| CRED[sources.credibility recalibrated]

    BRF --> USER[Telegram User]
    DIG --> USER

    Y2 --> POS[positions table]
    POS -->|/asymmetry| ASY[Asymmetry verdict]
    ASY --> USER

    I2 --> CLUSTER[insider_buy_cluster_log]
    CLUSTER -->|resolve_buy_cluster 8:15| USER
```

## Monitoring and meta crons

```mermaid
flowchart LR
    DB[(SQLite WAL)] -->|backup 4:00 daily| BAK[scripts/backup.sh + 14d rotation]
    LC[(llm_calls)] -->|weekly Sun 22:00| COST[/cost_trajectory MTD + projection + budget]
    P[(predictions)] -->|weekly Sun 22:30| KPI[/kpi_status 5 KPIs]
    D[(decisions)] -->|weekly Sun 22:30| KPI
    HC[(handler_calls)] -->|weekly Sun 23:00| HS[/handler_stats Pareto]

    BAK --> FS[~/backups/mes-bots-finance/]
    COST --> TG[Telegram notify]
    KPI --> TG
    HS --> TG
```

## LLM cascade flow

```mermaid
flowchart LR
    SIG[New signal] --> HK{Haiku extract tier}
    HK -->|signal_classify| TYPE[signal_type]
    HK -->|entity extraction| ENT[entities JSON]

    SIG --> SN{Sonnet enrich tier}
    SN -->|materiality_v2| MAT[impact+rev+time]
    SN -->|daily_digest 2x| DIG[unified narrative]
    SN -->|signal_scoring| SC[score 0-10]

    THESIS[Thesis decision] --> OP{Opus reasoning tier}
    OP -->|risk_check| RC[risk assessment]
    OP -->|multi-round debate| DEB[bull vs bear synthesis]
    OP -->|thesis_premortem| PM[Pre-mortem analysis]

    HK -.->|0.0005/call 116 calls 30d| COST1[~0.31 USD]
    SN -.->|0.04/call 82 calls 30d| COST2[~0.51 USD]
    OP -.->|0.10-0.30/call 3 calls 30d| COST3[~0.22 USD]
```

## Key invariants

- All math-critical operations have property-based tests in tests/ (49 tests Hypothesis)
- All ingestion paths use atomic INSERT+UPDATE pattern with last_signal_at propagation
- Chained materiality_v2 ensures 100% rubric coverage post-ingest
- Backup runs daily 04:00 Paris with integrity_check enforced
- WAL mode allows concurrent reads during writes
- 4 weekly Sunday summaries: cost 22:00, kpi 22:30, handler_stats 23:00, monthly recal 1st 6:00
