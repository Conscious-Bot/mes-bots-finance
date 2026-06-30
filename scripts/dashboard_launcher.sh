#!/bin/bash
# Launcher dashboard PRESAGE pour launchd (com.olivier.presage-dashboard).
# Appele par launchd au boot/login + sur restart KeepAlive.
# Ne PAS lancer manuellement -- launchd gere le lifecycle.
# Sert http://127.0.0.1:8000/dashboard.html (read-only sur data/bot.db).

cd /Users/olivierlegendre/mes-bots-finance

# Charger .env si present (memes secrets que le bot, ex: ANTHROPIC_API_KEY pour /chat).
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

source venv/bin/activate

# Pas de caffeinate : le dashboard est read-only, il n'a pas de cron a preserver.
# Le bot (com.olivier.presage) garde deja le Mac eveille si besoin.
exec python -m dashboard.serve
