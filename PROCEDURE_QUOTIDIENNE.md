# PROCEDURE QUOTIDIENNE - Bot Finance

Routine matinale rapide (10-15 min) pour valider que tout fonctionne.
A faire chaque jour entre 8h et 12h Paris.

## ROUTINE MATINALE (10 min)

### 1. Bot tourne ?

    cd ~/mes-bots-finance
    pgrep -fl "python.*bot.main"

- 1+ ligne avec PID = OK
- Vide = bot down, voir PROCEDURE_URGENCE.md Scenario 1

### 2. Heartbeat recent ?

    cat data/bot_state.json | grep last_heartbeat_ts

Doit etre < 1h. Sinon le scheduler a un probleme.

### 3. Logs uptime nuit ?

    tail -20 uptime.log

Tous "OK alive" = bot vivant toute la nuit. Si "FAIL bot down" = downtime a identifier.

### 4. Alertes Telegram nuit ?

Regarde ton chat Telegram bot finance. Aucune alerte = OK.

### 5. Backup quotidien fait ?

    ls -lat data/backups/ | head -5

Un backup data_YYYYMMDD_*.tar.gz doit dater de cette nuit (~23:00).

### 6. Digest matinal recu ? (Phase 2+)

Regarde Telegram. Doit etre arrive vers 7h Paris.

### 7. Documentation rapide

Optionnel : ouvre daily_log.md (a creer en Phase 2), note :
- Etat bot
- Anomalies
- Decisions prises

## ROUTINE SOIRE (5 min, optionnel)

- Verifier signaux du jour (Phase 2+)
- Backup ad-hoc si modif code aujourd'hui

## EN CAS DE PROBLEME

Voir PROCEDURE_URGENCE.md
