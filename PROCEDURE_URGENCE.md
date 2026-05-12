# PROCEDURE URGENCE - Bot Finance

## SCENARIO 1 : BOT CRASHE

### Diagnostic (2 min)

    cd ~/mes-bots-finance
    pgrep -fl "python.*bot.main"
    tail -30 bot.log 2>/dev/null
    tail -50 uptime.log

### Restart

    source venv/bin/activate
    pkill -f "python.*bot.main" 2>/dev/null
    sleep 2
    python -c "import bot.main; print('syntax OK')"
    nohup python -m bot.main > bot.log 2>&1 &
    sleep 5
    pgrep -fl "python.*bot.main"
    tail -20 bot.log

### Si syntax FAIL

- NE PAS restart
- Restaurer depuis backup le plus recent :

    ls -lat data/backups/data_*.tar.gz | head -3
    ls bot/main.py.backup_avant_* 2>/dev/null
    cp bot/main.py.backup_avant_XXX bot/main.py
    python -c "import bot.main; print('OK')"

## SCENARIO 2 : DRAWDOWN ELEVE

### Si drawdown 8-20%

1. Pas de panique
2. Pas de modification code
3. Bot reduit deja sizing automatiquement (risk_engine)
4. Diagnostic : pourquoi les theses ont fail ?

    sqlite3 data/bot.db "SELECT * FROM theses WHERE status='invalidated' ORDER BY opened_at DESC LIMIT 10"

### Si drawdown > 20%

1. Bot bloque automatiquement nouvelles positions
2. Pause 7 jours minimum
3. Diagnostic profond :
   - Calibration : tes convictions sont-elles inflated ?
   - Regime : est-on en regime hostile ?
   - Sources : credibility des sources qui ont mene aux echecs ?
4. Re-evaluer config avant reprise

### Si drawdown > 40%

1. STOP TOTAL
2. Reactiver paper_only :

    python -c "from shared import storage; storage.update_state(paper_only=True)"

3. Analyse post-mortem complete
4. Backup et reset partiel si necessaire

## SCENARIO 3 : BUG DETECTE

### Action

1. NE PAS modifier en panique
2. Documenter le bug : description, reproduction, impact
3. Backup IMMEDIAT :

    tar czf data/backups/avant_fix_$(date +%Y%m%d_%H%M%S).tar.gz data/
    cp module_concerne.py module_concerne.py.backup_avant_fix_$(date +%Y%m%d)

4. Tester fix sur copie
5. Smoke test :

    python -m risk.sizing
    python -c "from shared import storage; storage.load_state(); print('OK')"

6. Deployer si tout OK

## SCENARIO 4 : TELEGRAM API DOWN

### Action

- Bot va failer ses sendMessage
- Errors logues dans bot.log
- Pas d'action requise (Telegram revient tres rarement > 1h)
- Verifier statut : https://status.telegram.org

## SCENARIO 5 : ANTHROPIC API DOWN

### Action

- Bot ne peut plus appeler Claude
- Tous les digests et analyses fail
- Verifier statut : https://status.anthropic.com
- Verifier credit restant sur console.anthropic.com
- Verifier que la cle API n'est pas expiree

## SCENARIO 6 : CRON NE TOURNE PAS

### Diagnostic

    crontab -l
    ls -lat uptime.log
    ls -lat data/backups/backup.log

### Fix

    crontab -l > /tmp/cron_backup.txt
    crontab -e

## CONTACTS / RESSOURCES

- Backups : data/backups/data_*.tar.gz (30 derniers jours)
- Backups nommes patches : */*.backup_avant_*
- Docs : TODO.md, PHILOSOPHY.md, CONVENTIONS.md
- Logs : bot.log, uptime.log, data/backups/backup.log
