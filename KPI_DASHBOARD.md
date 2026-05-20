# KPI DASHBOARD - Bot Finance

Metriques de performance et sante du bot.

## METRIQUES QUOTIDIENNES

### 1. Bot uptime

- Cible : > 95%
- Mesure : count "OK alive" / total lines uptime.log
- Alert : > 2h sans heartbeat

### 2. Signaux ingeres (Phase 2+)

- Cible : 10-50 signaux/jour
- Mesure :

    sqlite3 data/bot.db "SELECT count(*) FROM signals WHERE date(timestamp) = date('now')"

- Alert : 0 signal pendant 2 jours = bug ingest

### 3. Erreurs critiques

- Cible : 0
- Mesure : grep ERROR dans bot.log
- Alert : > 5 erreurs/jour

### 4. Backup quotidien

Two mechanisms run in parallel (Day 2 marathon legacy):

- **Primary** : 04:00 Paris, in-bot APScheduler `daily_backup_job` -> `scripts/backup.sh` -> `~/backups/mes-bots-finance/snapshot_YYYYMMDD_*.tar.gz` (tarball + DB snapshot + integrity_check + 14d rotation).
- **Secondary** (legacy) : 23:15 Paris, crontab `crons/daily_backup.sh` -> `data/backups/data_YYYYMMDD_*.tar.gz` (simple tar, 30d rotation).

- Cible : un `snapshot_*.tar.gz` dans `~/backups/mes-bots-finance/` cree chaque nuit (~04:00 Paris)
- Mesure primary : `ls -lat ~/backups/mes-bots-finance/ | head -5`
- Mesure secondary : `ls -lat data/backups/ | head -3`
- Alert : pas de backup primary depuis > 24h

## METRIQUES HEBDOMADAIRES

### 5. Theses actives vs invalidees

- Cible : ratio invalidations < 30%
- Mesure :

    sqlite3 data/bot.db "SELECT status, count(*) FROM theses GROUP BY status"

### 6. Source credibility evolution

- Top 5 et bottom 5 sources
- Identifier les sources a couper si credibility < 0.3 apres > 20 signaux
- Mesure :

    sqlite3 data/bot.db "SELECT name, credibility, n_signals FROM sources ORDER BY credibility DESC"

### 7. Calibration drift (Phase 5+)

- Cible : drift < 0.1 (10% gap entre prevu et reel)
- Mesure :

    sqlite3 data/bot.db "SELECT confidence_bucket, actual_rate, drift FROM calibration ORDER BY timestamp DESC LIMIT 10"

### 8. CLV moyen sur theses fermees (Phase 2+)

- Cible : positif (> 0)
- Mesure :

    sqlite3 data/bot.db "SELECT AVG(clv_30d), AVG(clv_90d) FROM theses WHERE status='realized'"

- Alert : CLV negatif sur 5+ theses recentes

## METRIQUES MENSUELLES

### 9. Win rate bot

- Cible : > 55%
- Necessite : > 30 predictions resolues
- Mesure :

    sqlite3 data/bot.db "SELECT outcome, count(*) FROM predictions WHERE resolved_at IS NOT NULL GROUP BY outcome"

### 10. Sharpe ratio des theses (Phase 5+)

- Cible : > 1.0 a > 1.5
- Necessite : > 30 theses resolues
- Calcule via PyPortfolioOpt en Phase 5

### 11. Distribution conviction

- Cible : convictions 1-5 reparties (pas 80% en 5 = inflation)
- Inflation watch : alerte si > 20% des theses ont conviction 5
- Mesure :

    sqlite3 data/bot.db "SELECT conviction, count(*) FROM theses GROUP BY conviction"

### 12. Patterns identifies (Phase 5+)

- Phase 5+ : croissance attendue de patterns avec accumulation data
- Mesure :

    sqlite3 data/bot.db "SELECT count(*) FROM patterns WHERE is_active = 1"

## SCRIPTS UTILES (quick view)

    sqlite3 data/bot.db "SELECT count(*) as theses_actives FROM theses WHERE status='active'"
    sqlite3 data/bot.db "SELECT count(*) as predictions_pending FROM predictions WHERE resolved_at IS NULL"
    sqlite3 data/bot.db "SELECT count(*) as signaux_24h FROM signals WHERE timestamp > datetime('now', '-1 day')"
    grep "OK alive" uptime.log | wc -l
    grep "FAIL" uptime.log | wc -l

## SIGNAUX D ALERTE

### ROUGE (action immediate)

- Drawdown > 20%
- Bot down > 2h
- 0 backup depuis > 48h
- 0 signaux ingeres depuis > 48h (Phase 2+)

### ORANGE (vigilance)

- Drawdown 10-20%
- Bot down 30 min - 2h
- Calibration drift > 0.15
- Inflation conviction > 25%

### VERT (normal)

- Drawdown < 10%
- Bot uptime > 95%
- Calibration drift < 0.1
- Distribution conviction equilibree

## REVIEW HEBDOMADAIRE (15 min, samedi)

1. Run scripts KPI ci-dessus
2. Check les 12 metriques
3. Tag signaux d alerte ROUGE / ORANGE / VERT
4. Document dans weekly_log.md (a creer plus tard)
5. Action items eventuels


---

## KPI #5 — Measurement Window Reset (21/05/2026)

### Empirical baseline post-investigation

Phase B5 journal logging chain (cmd_position_buy/sell → log_decision → bias_tagger
→ update_decision_bias_tags) is **validated functional live** as of 2026-05-20 12:21:58 UTC
via smoke test (decision #8 entry SMOKE / #9 full_exit SMOKE, both auto-tagged biases).

### Historical state (pre-21/05/2026)

- 20/21 active positions = bulk backfill 2026-05-15 via `scripts/import_positions_legacy.py`
  which intentionally bypasses cmd_position_buy handler (calls `positions_mod.add_buy()` direct).
  By design: legacy positions imported with current market price as cost basis = no real
  entry decision rationale to journal honestly.
- 1 historical /position_buy live test on 2026-05-13 13:35 (NVDA 0.1 @ 130 "test b2 flag off")
  predates Ship 5 of Day 2 marathon OR errored silent in except branch — no decision row created.
- 2 historical decisions (12/05 NVDA `no_action_flag`) via journal_bias.py handler,
  NOT via cmd_position_buy path.
- **Net: zero `entry` or `scale_in` decisions tracked before 21/05/2026.**

### Decision: forward-only honest tracking (option β)

KPI #5 measurement window **starts 21/05/2026**. All material decisions taken via
/position_buy /position_sell /no_action_flag (or other journal-instrumented handlers)
from this date forward count toward the 100% target.

Legacy 20 positions explicitly out-of-scope with documented rationale "pre-journal era,
bulk import design bypass." No retroactive backfill — that would be metric manipulation
inconsistent with PHILOSOPHY "Tout output non instrumenté est gaspillé" (the gasp is
historical, faking output ex-post falsifies track record).

### Measurement formula

KPI #5 = decisions_journaled / decisions_taken WHERE created_at >= '2026-05-21'

Action si breach (<90% over 30d rolling): pause new thesis creation, audit the gap source
(handler bug vs discipline lapse), fix root cause before resuming.

### Tracking query

```sql
SELECT COUNT(*) AS journaled, decision_type
FROM decisions
WHERE created_at >= '2026-05-21'
GROUP BY decision_type;
```

