# Flow 4 — Schedule → Execution → Marker

**Trace** : launchd → bot.main → APScheduler jobs (cron + interval + date) + crons externes (uptime_monitor, j_day_watcher, preflight). Markers DB/log/notify.

## Scheduler topology

Trois layers de scheduling, indépendants :

| Layer | Géré par | Lifecycle | Survives |
|---|---|---|---|
| L1 — bot process | launchd `com.olivier.presage` | RunAtLoad + KeepAlive crash | Mac reboot, bot crash (ThrottleInterval 30s restart) |
| L2 — APScheduler in-process | AsyncIOScheduler (Europe/Paris TZ) | dies with bot process | bot crash restart via launchd |
| L3 — system cron | crontab user | OS managed | Mac reboot ; PAS Mac asleep |

Plus :
- `dashboard/serve.py` : process MANUEL, **non-supervisé** par launchd. Die = stay die jusqu'à restart user. Gap connu.
- caffeinate : invoké par `scripts/bot_launcher.sh`, garde Mac awake tant que bot run.

## APScheduler jobs (live audit, `bot/main.py:226-285`)

| Job | Type | Schedule | Misfire grace |
|---|---|---|---|
| heartbeat | interval | every 1h | 3600s |
| ingest_gmail_job | interval | every 1h | 3600s |
| price_monitor_job | cron | 14-22h every 15min mon-fri | 3600s |
| daily_calendar_refresh_job | cron | 05:00 daily | 3600s |
| daily_backup_job | cron | 04:00 daily | **14400s (4h)** |
| daily_crypto_zone_job | cron | 10:00 daily | 3600s |
| recalibrate_credibility_brier_job | cron | day 1, 06:00 | 3600s |
| monthly_track_record_snapshot_job | cron | day 1, 08:00 | **86400s (24h)** |
| **j_day_batch_close_job** | **date** | **2026-06-10 09:30 once** | **43200s (12h)** |
| weekly_v2_vigilance_check_job | cron | mon 07:00 | 3600s |
| weekly_calibration_audit_job | cron | sun 22:00 | 3600s |
| monthly_bot_preferences_synthesis_job | cron | day 1, 04:00 | 86400s |
| cron_tier1_daily | cron | 06:00 daily | 3600s |
| cron_tier2_weekly | cron | mon 06:30 | 3600s |
| cron_tier3_monthly | cron | day 1, 07:00 | 3600s |
| daily_digest_job | cron | 19:00 daily | 7200s |
| **morning_chain** (insiders+filings+score+digest+monitors+resolves) | cron | 06:00 daily | **14400s (4h)** |
| evening_chain (snapshot+grade+counterfactual_resolve) | cron | 23:00 daily | 14400s |
| weekly_chain_saturday | cron | sat 18:00 | 86400s |
| weekly_chain_sunday | cron | sun 19:00 | 86400s |
| scheduled_classify_signal_types_job | interval | every 30min | 3600s |
| scheduled_recompute_materiality_boost_job | interval | every 1h | 3600s |
| scheduled_materiality_v2_job | interval | every 1h | 3600s |

**Total : ~24 APScheduler jobs.** `coalesce=True` global → si bot down 2h, le job rate les 2 fires mais ne tire qu'1 fois post-restart (anti-storm).

## System cron jobs (`crontab -l`)

| Schedule | Script | Rôle |
|---|---|---|
| `*/5 * * * *` | uptime_monitor.sh | check `pgrep bot.main` → uptime.log + Telegram si down (rate-limited 1h) |
| `30 10 10 6 *` | j_day_watcher.sh | J-day primary check à 10:30 |
| `0 14 10 6 *` | j_day_watcher.sh | J-day backup à 14:00 |
| `0 9 9 6 *` | j_day_preflight_notify.sh | J-1 preflight push à 09:00 |

## Plugs solidity

| Plug | Status | Notes |
|---|---|---|
| launchd `com.olivier.presage` | **solide** : RunAtLoad + KeepAlive (Crashed=true) + ThrottleInterval=30s + caffeinate -dimsu | restart automatique sur crash, sleep impossible tant que bot vit |
| APScheduler coalesce=True | **solide** : missed-fires don't catch-up storm | post-wake = 1 fire propre, pas 5 en cascade |
| misfire_grace_time tuning | **par job** : critique (J-day=12h, backup=4h, monthly=24h) plus large. Default 1h. | conscient. J-day spec 12h grace = robuste si bot down au moment exact 09:30 |
| `scheduler.get_jobs()` log au start (line 289-291) | **solide** : dump réel scheduler state, pas hardcoded string qui drift | critique cf comment ligne 287. Permet vérification avant J-day. |
| morning_chain dependency on `daily_resolve_job` | **solide** : sequences.py orchestre l'ordre intra-chain | dependency entre jobs gérée explicitement |
| `j_day_batch_close_job` lookup `daily_resolve_job` complétion | **gap mineur** : j_day fire 09:30, dépend que morning_chain (06:00) ait fini avant. 3h de marge ÷ misfire_grace_time 4h sur morning_chain → en théorie, edge case où morning_chain manqué et catched-up à 09:55 (après j_day) | improbable mais possible. À J-day : si bot up à 06:01, morning_chain commence normal, j_day fire bien à 09:30 sur DB cohérente. |
| crontab → script execution | **solide** : système cron + shell script |
| Telegram error_handler global (bot/main.py:295) | **solide** : catche toute exception handler + envoie msg au user | mitigation de mon P1 Flow 3 : un crash handler n'est pas silent — le user voit "[BOT ERREUR] TypeName: message". Mauvais UX mais pas silencieux. Re-qualifié **P2** au lieu de P1. |

## Failure modes

| Étape | Failure | Détection | Récupération | Severity |
|---|---|---|---|---|
| Mac asleep at 09:30 J-day | caffeinate prevents idle sleep but NOT battery exhaustion | uptime_monitor log entries cessent + healthchecks ping miss | healthchecks.io alarm 4h grace | **P1** addressed by user-action "stay plugged in" + healthchecks |
| bot crash mid-morning_chain | launchd restart in 30s | uptime_monitor le voit dans next cycle (5min) | coalesce=True → morning_chain re-fire propre si dans grace 4h | **P2** OK |
| APScheduler scheduler thread death | non-monitored (process alive, scheduler thread dead) | aucune — bot process alive sait pas scheduler dead | manuel | **P2** Pattern 1 — couvert par #100 post-J-day |
| `j_day_batch_close_job` fire timing | misfire grace 12h | dump au start log les next_run_time | bot down 12h+ : job skipped, jour suivant 06:00 morning_chain ré-attempts NO — date trigger one-shot, pas de retry | **P1** if bot down >12h on 10/06. Mitigated by healthchecks.io ping miss → alarm. |
| `dashboard/serve.py` death | manuel-only process | uptime_monitor NE COUVRE PAS serve (different process) | manuel | **P2** gap connu |
| crontab job miss (cron daemon down) | jamais arrivé sur Mac local, mais possible | aucune | manual restart cron | **P3** très improbable |
| timezone drift entre APScheduler (Europe/Paris) et crontab (system local) | system local = Europe/Paris confirmé | aucune surveillance auto | crash mauvaise heure | **P3** silently OK aujourd'hui |
| cron output silent (script crash) | seul stderr / log file capte | logs si scripts écrivent | manual log inspection | **P3** acceptable |

## Coupling assessment (3 patterns)

| Pattern | Évaluation |
|---|---|
| **Pattern 1 (liveness ≠ functionality)** | scheduler thread vs process alive = gap #100. dashboard/serve.py process vs bot process = gap. Telegram polling vs sendMessage = gap. Tous **non couverts pré-J-day**, mais le J-day specifically a healthchecks.io comme cover layer. |
| **Pattern 2 (snapshot drift)** | Schedules sont la source de truth, pas un snapshot. N/A. |
| **Pattern 3 (multi-path)** | `cron_tier1_daily` apparaît DEUX FOIS dans bot/main.py (ligne 255 ET 279). De même `cron_tier2_weekly` (256+280) et `cron_tier3_monthly` (257+281). **Duplicate job registrations** — APScheduler probablement double-fire. **Vérifier.** |

## Resilience layer integration

| Item | Status |
|---|---|
| LLMUnavailableError catch dans jobs | À vérifier per job. `materiality_v2.score_pending_signals_v2` ✓ catch. `signal_scorer_v2` via `learning.auto_register_predictions` ✓ catch. Autres jobs : à auditer. |
| Cost cap soft → Haiku | actif globalement via `_resolve_model`, transparent pour les jobs |
| llm_status set on cron-driven LLM call | ✓ via `call()` success/failure paths |
| Healthchecks ping post-J-day | ✓ wired dans `j_day.py` |
| **Healthchecks ping pour les AUTRES jobs critiques** | **gap** : aucun autre job ne ping healthchecks. monthly_track_record (day 1, 08:00) pourrait silently fail un mois et tu le verrais qu'au J+30 |

## Duplicates dans ce flux

- **`cron_tier1_daily` / `cron_tier2_weekly` / `cron_tier3_monthly` enregistrés DEUX FOIS** dans `bot/main.py` (ligne 255-257 ET 279-281). APScheduler `add_job` avec même func ID ne dédupplique pas — soit silent ignore second registration, soit DOUBLE-FIRE. **À vérifier dans `_job_lines` log au start.** Si double-fire confirmé → P1, debt_monitor s'exécute 2× par jour.
- Pas d'autre duplicate job détectée.

## Dead code dans ce flux

- Aucune fonction job orpheline détectée — toutes utilisées par main.py ou sequences.py.

## Action items Flow 4

| Item | Priority | Disposition |
|---|---|---|
| **Verify `cron_tier*` double registration** (lignes 255-257 vs 279-281) | **P1** | Trivial à vérifier : `_job_lines` au start contient-il 2 entries ? Si oui, supprimer les redondantes. Avant J-day. |
| **Vérification scheduler dump au start** : pre-J-day verify le log `Scheduler started with N jobs` contient bien `j_day_batch_close_job` avec `next_run` = 2026-06-10 09:30 | **P1** | Si bot a été restarté récemment, `bot.log` contient la dernière dump. Si J-day job absent, BIG problem. Avant 09/06. |
| Pre-J-day verify timezone (Europe/Paris cohérent entre APScheduler et system cron) | **P2** | sanity check : `date` + `python -c "import datetime; print(datetime.datetime.now())"` should agree. |
| Healthchecks ping pour monthly_track_record + weekly_calibration | **P2** | post-J-day, étendre le pattern healthchecks aux autres jobs critiques |
| serve.py supervised by launchd ? | **P2** | Optionnel : créer un second launchd plist. Petit. |
| Telegram error_handler — re-qualifier Flow 3 P1 en P2 | adjustment | comme noté ci-dessus, ce handler évite le silent — UX dégradé acceptable |

**Deux P1 nouveaux ici** : double registration `cron_tier*` à vérifier, et scheduler dump verification avant J-day.
