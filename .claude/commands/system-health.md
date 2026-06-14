---
description: Recon rapide PRESAGE — bot VM alive, drift detector, alembic head Mac vs VM, last close, cron status
---

# /system-health — Recon démarrage session

**Pourquoi** : début de session, avant tout chantier, vérifier que le système est dans un état attendu. Catch les surprises (bot down, drift detector rouge, alembic Mac vs VM divergé, cron stale). Sauvé 30 min de debug "ah le bot était down depuis hier".

**Quand l'invoquer** : début de chaque session non-triviale, ou quand suspect d'un dysfonctionnement.

## Etapes

1. **Bot VM alive** (Hetzner prod) :
   ```bash
   ssh hetzner 'systemctl --user is-active presage-bot.service'
   # OR pgrep -f "python.*-m bot.main"
   ```
   Attendu : `active`. Si `inactive/failed` → investiguer immediately.

2. **Drift detector status** (mémoire `13/06 close`) :
   ```bash
   ssh hetzner 'cat ~/presage/data/drift_status.json'
   ```
   Attendu : `behind=0` ou très faible. Si `behind>5` → git pull Mac vs VM divergé.

3. **Alembic head Mac vs VM** :
   ```bash
   # Mac
   cd /Users/olivierlegendre/mes-bots-finance && venv/bin/alembic heads
   # VM
   ssh hetzner 'cd ~/presage && venv/bin/alembic heads'
   ```
   Attendu : même head (actuellement 0061 ou plus). Si différent → migration en attente.

4. **Last close date** :
   ```bash
   grep -nE "^## Close" SESSION_STATE.md | tail -3
   ```
   Si > 7j ancien → session-rupture, re-onboarding plus long anticipé.

5. **Cron sanity** via table `scheduler_runs` (migration 0062, audit 14/06/2026) :
   ```python
   import sqlite3
   from datetime import datetime, timedelta
   conn = sqlite3.connect('data/bot.db')
   conn.row_factory = sqlite3.Row

   # Last fire per chain step (inside morning/evening chain _safe_run)
   cur = conn.execute('''
       SELECT job_name,
              MAX(started_at) AS last_started,
              SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS n_success,
              SUM(CASE WHEN status='fail'    THEN 1 ELSE 0 END) AS n_fail,
              AVG(duration_s) AS avg_dur_s
       FROM scheduler_runs
       WHERE started_at >= datetime('now', '-7 days')
       GROUP BY job_name
       ORDER BY MAX(started_at) DESC
   ''')
   rows = [dict(r) for r in cur]

   # Expected cadences (en heures depuis dernier tir attendu)
   EXPECTED_HOURS = {
       'snapshot': 25, 'portfolio_grade': 25, 'counterfactual_resolve': 25,
       'daily_resolve': 25, 'kill_criteria_check': 25, 'group_cap_check': 25,
       'over_cap_check': 25, 'stale_target_check': 25, 'decision_anniversary': 25,
       'resolve_journal_decisions': 25, 'resolve_buy_cluster_returns': 25,
       # weekly steps (sat/sun chains)
       'data_clusters': 8 * 24,
   }
   ```
   Pour chaque row, flagger :
   - **GREEN** : last_started < EXPECTED_HOURS * 1
   - **YELLOW** : last_started entre 1x et 2x EXPECTED_HOURS
   - **RED** : last_started > 2x EXPECTED_HOURS (silent-dead candidate)
   - **FAIL-LOOP** : n_fail >= 3 sur dernier 7j (cron meurt en boucle)

   Pour les crons TOP-LEVEL non encore tracked dans _safe_run (heartbeat,
   ingest_gmail_job, daily_backup_job, etc.) : pas de coverage scheduler_runs
   pour l'instant. Future iteration : ajouter @scheduler_run_logged decorator
   sur leurs entrypoints.

6. **Pytest baseline** (rapide, sans full run) :
   ```bash
   cd /Users/olivierlegendre/mes-bots-finance && venv/bin/pytest --co -q | tail -3
   ```
   Confirme N tests collected attendu (baseline 1892+).

7. **LLM cost cumulative** (si tracking actif) :
   Vérifier `data/llm_usage.json` ou équivalent : budget restant ce mois.

8. **Dashboard health** :
   ```bash
   curl -s http://127.0.0.1:8000/dashboard.html -o /dev/null -w "%{http_code}"
   ```
   200 = vivant. 0/connection refused = `serve.py` down → `python3 -m dashboard.serve`.

## Output au user

Tableau compact :
```
ASPECT                | STATUS  | DETAIL
----------------------+---------+--------------------------------
Bot VM (Hetzner)      | GREEN   | active since 2026-06-13
Drift detector        | GREEN   | behind=0
Alembic head sync     | GREEN   | 0062 == 0062 (post audit 14/06)
Last close            | GREEN   | 2026-06-13 (1 day ago)
Cron freshness        | YELLOW  | group_cap_check 26h stale
Pytest collect        | GREEN   | 1892 tests
Dashboard serve       | RED     | not running (http=0)
```

Si tout GREEN → "Système OK, prêt pour chantier."
Si YELLOW/RED → action recommandée par item.

## Anti-patterns

- ❌ Skip system-health "parce qu'on est pressé" → cas typique d'investiguer 30 min un bug qui était un bot down depuis 6h
- ❌ Trust pgrep seul (memory uptime case-bug 2026-05-14) → multi-signal observability
- ❌ Modifier le repo avant de savoir si Mac/VM sont alignés sur alembic head

## Reference

- Memory : `hetzner_migration_triggered`, `13/06 close cutover Mac→VM complet`
- Script existant : `scripts/bot_health_check.sh` (peut être leveraged)
- Table `scheduler_runs` (migration 0062, audit cron 14/06/2026) — source
  unique de vérité pour cron last-fire. Helpers : `shared/storage.py:
  insert_scheduler_run_start / update_scheduler_run_end / get_last_scheduler_run`.
- Doctrine : memory `feedback_red_team_verify_before_assert` (verify, jamais à l'intuition)
