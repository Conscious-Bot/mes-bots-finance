# mes-bots-finance — Fiche Technique (Lean Edition)

**Version** : 13 mai 2026 — High Standard Mode (post pivot Path 5/6)
**Auteur** : Olivier Legendre
**État** : Solidification en cours, ~37 unit tests passing, math invariants locked

---

## Mission

Système d'intelligence finance personnelle en boucle fermée self-learning. **Mécanise la discipline** pour compenser deux biais asymétriques :
1. Vend winners trop tôt (locking-in + mean-reversion) — historique PLTR/NVDA
2. Ne vend pas crypto aux indicators tops (FOMO/greed)

Le bot **ne trade pas**. Il force la réflexion structurée pré-commit via thesis tracker bidirectionnel, calibration Brier, multi-round debate, risk_check Opus, journal auto-résolu.

---

## Architecture (7-stage conceptual pipeline, async DAG en réalité)

1. **SUBSTRATE** — DB schema, configs, secrets
2. **INGESTION** — Gmail, EDGAR, FRED, yfinance, CoinGecko crons
3. **ENTONNOIR** — Filter+score signals (signal_type Haiku + materiality_v2 Sonnet + echo BGE)
4. **SIGNAUX** — Event detection (insider clusters, 8-K cat, crypto zones)
5. **SYNTHESIS** — Multi-round debate, /analyze deep fiche, risk_check Opus
6. **APPROPRIATION** — Position book, journal auto-resolve, bias_tagger, pre-mortem
7. **RESTITUTION** — /brief 6 sections, /digest 2x/jour unified narrative

Voir `docs/REFERENCE_SCHEMA.md` pour data lineage détaillée (à créer P1).

---

## Stack contraintes

- Python 3.14, SQLite, APScheduler, BGE-small-en-v1.5 embeddings local
- **PAS** FastAPI / Postgres / Redis / LangGraph
- Run local MacBook Pro, pas de cloud déploiement
- Anthropic Claude API (Haiku/Sonnet/Opus cascade)
- Coût : ~$8-15/mo en usage régulier

---

## Principes directeurs (high standard mode)

1. **Le bot ne trade pas**, il force la discipline pré-commit
2. **Plus de précision dans la mesure > plus de surface monitorée**
3. **Cascade LLM** : Haiku volume, Opus raisonnement structuré uniquement
4. **Bidirectionnel** : anti-vend-trop-tôt ET anti-tient-trop-long égale importance
5. **Matière empirique > construction** : KPI #2 ≥5 predictions résolues à J+28 ou stop build
6. **Velocity solidified** : tests + cost modeled + observability avant chaque feature
7. **Pas de scope creep** : SQLite/APScheduler local jusqu'à ce que ça casse explicitement
8. **Hygiene = feature** : audit GREEN avec coverage avant new builds
9. **Versioning + backup obligatoire** : git + tarball + DB snapshot quotidien
10. **Tracker track record > tracker features** — Path 5/6 = personal brand + measured discipline

---

## KPIs avec enforcement

| KPI | Cadence | Seuil dégradation | Action |
|---|---|---|---|
| **#2 NON-NEG** ≥5 predictions résolues J+28 | Hebdo | <5 à J+28 | Stop 5j build, force-use |
| **#3** Brier <0.20 rolling 90j | Hebdo | >0.25 | Alert + revue méthodo |
| **#4** 0 panic sell thesis core | Mensuel | ≥1 panic sell | Pause + bias analysis |
| **#5** 100% decisions matérielles journalisées | Mensuel | <90% | Aucune nouvelle thèse jusqu'à backfill |
| **#6** TWR vs SPY/QQQ glissant 12M | Mensuel | <-5pp | Revue stratégique trimestrielle |

---

## Documents compagnons

| Fichier | Rôle |
|---|---|
| `SESSION_STATE.md` | Handoff entre sessions |
| `TODO.md` | Backlog organisé + roadmap Path 5/6 |
| `PHILOSOPHY.md` | Principes directeurs + biais comportementaux |
| `CONVENTIONS.md` | Naming + structure code |
| `PROCEDURE_QUOTIDIENNE.md` | Ritual quotidien checklist |
| `PROCEDURE_URGENCE.md` | Crisis recovery procedures |
| `KPI_DASHBOARD.md` | Tracking KPIs explicites |
| `ARCHITECTURE.md` | 7-stage pipeline détaillé |
| `AUDIT_*.md` | Code audit reports timestamped |
| `tests/` | Property-based tests Hypothesis sur math critique |
| `scripts/backup.sh` | Daily backup automation |
| `Makefile` | test / test-cov / backup / test-restore |

---

## Path 5/6 Strategic Target

**Path 5** (acquihire $200K-$1M, 18-24mo) ET/OU **Path 6** (Substack + prosumer subscription $100K-500K/an, 24-36mo).

Voir TODO.md section "Path 5/6 Strategic Pivot" pour roadmap 4 dimensions (Solidification / Track Record / Dépersonnalisation / Positionnement public).
