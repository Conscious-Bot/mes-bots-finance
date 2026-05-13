# mes-bots-finance — Fiche Technique (Lean)

**Version**: 13 mai 2026 (post Day 2 marathon + afternoon extension)
**Auteur**: Olivier Legendre
**État**: High Standard Mode active, 14 items shippés en une session, 49 tests passing

---

## Mission

Système d'intelligence finance personnelle en boucle fermée self-learning. **Mécanise la discipline** pour compenser deux biais asymétriques :
1. Vend winners trop tôt (locking-in + mean-reversion) — historique PLTR/NVDA
2. Ne vend pas crypto aux indicators tops (FOMO/greed)

Le bot **ne trade pas**. Il force la réflexion structurée pré-commit via thesis tracker bidirectionnel, calibration Brier, multi-round debate, risk_check Opus, journal auto-résolu.

---

## Stack contraintes

- Python 3.14, SQLite **WAL mode**, APScheduler, BGE-small-en-v1.5 local embeddings
- **PAS** FastAPI / Postgres / Redis / LangGraph
- Run local MacBook Pro, pas de cloud
- Anthropic Claude API (Haiku / Sonnet / Opus cascade)
- Coût observé: **$0.50/jour, projected $15/mo** (vs budget $50)

---

## État empirique (13 mai 2026 après-midi)

| Métrique | Valeur |
|---|---|
| Signaux ingérés 30d | 66 (100% materiality_v2 coverage) |
| Sources actives | 27 (post-dedup, post-backfill) |
| Tier S empirical | 5 (Adam Tooze, Chamath, Wall Street Rollup, Coin Metrics, SemiAnalysis) |
| Predictions ouvertes | 45 (cluster J+28 = 10 juin) |
| Predictions résolues 28d | 1 |
| Tests Hypothesis | 49/49 passing |
| Coverage math_helpers | 100% |
| Crons actifs | 22 |
| Handlers Telegram | 49+ (telemetry actif) |

---

## Architecture (7-stage conceptual)

1. **SUBSTRATE** — DB schema (15 tables), configs, secrets
2. **INGESTION** — Gmail (max_results=50), EDGAR, FRED, yfinance, CoinGecko
3. **ENTONNOIR** — signal_type Haiku + materiality_v2 Sonnet chained + echo BGE
4. **SIGNAUX** — insider clusters, 8-K cat, crypto zones
5. **SYNTHESIS** — multi-round debate, /analyze deep fiche, risk_check Opus
6. **APPROPRIATION** — position book, journal auto-resolve, bias_tagger
7. **RESTITUTION** — /brief 6 sections, /digest 2x/jour, /kpi_status, /cost_trajectory

---

## Quality artifacts (audit-grade)

- **Tests**: 49 Hypothesis property-based (math_helpers 100%, learning horizon 100%, materiality 17%, asymmetry 41%)
- **Backup**: daily 04:00 + integrity_check + 14d rotation + Makefile restore test
- **Concurrency**: SQLite WAL mode (N readers + 1 writer)
- **CI**: .github/workflows/ci.yml ready (Python 3.14 matrix + pytest + coverage XML artifact)
- **Telemetry**: middleware logue tous /commands → /handler_stats Pareto curve
- **Cost dashboard**: /cost_trajectory MTD + projection + budget alert
- **KPI runtime**: /kpi_status avec enforcement triggers

---

## Path 5/6 strategic target

**Path 5** (acquihire $200K-$1M, 18-24mo) ET/OU **Path 6** (Substack + prosumer subscription $100K-500K/an, 24-36mo).

### Dimensions roadmap

| Dim | État | Notes |
|---|---|---|
| 1. Technique solidification | ✅ DONE (this marathon) | 14 items, 49 tests, audit-grade |
| 2. Track record mesure | ✅ ACTIVATED | /kpi_status + weekly auto-post, timer J+28 = 10 juin |
| 3. Dépersonnalisation | ⏳ Month 6+ | Templated prompts + profile config |
| 4. Positionnement public | ⏳ Month 12+ | Substack + LinkedIn post-J+90 |

---

## KPIs enforcement runtime

| KPI | Target | Action si breach |
|---|---|---|
| **#2 NON-NEG** ≥5 predictions résolues 28d | ≥5 | Stop 5j build + force-use |
| #3 Brier <0.20 rolling 90d | <0.20 | Alert + revue méthodo si >0.25 |
| #4 0 panic sell core | 0 | Pause + bias analysis si ≥1 |
| #5 100% decisions matérielles journalisées | 100% | No new thesis si <90% |
| #6 TWR vs SPY/QQQ 12M | >-5pp | Revue strat trim. si <-5pp |

`/kpi_status` à tout moment + cron Sunday 22:30 Paris auto-post.

---

## Documents canoniques

| Fichier | Rôle |
|---|---|
| `SESSION_STATE.md` | Handoff sessions (canonical entry point reopen) |
| `TODO.md` | Backlog + Path 5/6 roadmap + dette closed |
| `PHILOSOPHY.md` | High Standard Mode principles |
| `CONVENTIONS.md` | Naming + structure code |
| `docs/SOURCES.md` v2 | Tiers S/A/B empirical composite_avg |
| `docs/failure_modes.md` | Top 5 failure scenarios + runbooks |
| `tests/` | 49 Hypothesis property-based tests |
| `scripts/backup.sh` + `Makefile` | Automation |
| `.github/workflows/ci.yml` | CI (pending repo push) |

---

## Principes directeurs (rappel)

1. Le bot ne trade pas, il force discipline pré-commit
2. Précision dans la mesure > surface monitorée
3. Cascade LLM: Haiku volume, Opus raisonnement structuré
4. Bidirectionnel: anti-vend-trop-tôt ET anti-tient-trop-long
5. Matière empirique > construction (KPI #2 NON-NEG)
6. High Standard: tests + cost modeled + observability avant feature
7. Pas de scope creep: stack contraint jusqu'à break explicite
8. Hygiene = feature
9. Backup + versioning obligatoire
10. Track record > features (Path 5/6 narrative)
