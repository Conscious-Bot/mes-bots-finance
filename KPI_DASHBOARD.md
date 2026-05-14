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

    sqlite3 data/bot.db "SELECT correct, count(*) FROM predictions WHERE outcome_evaluated_at IS NOT NULL GROUP BY correct"

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
    sqlite3 data/bot.db "SELECT count(*) as predictions_pending FROM predictions WHERE outcome_evaluated_at IS NULL"
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
