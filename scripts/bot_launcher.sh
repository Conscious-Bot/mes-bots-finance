#!/bin/bash
# Launcher PRESAGE pour launchd (com.olivier.presage).
# Appele par launchd au boot/login + sur restart KeepAlive.
# Ne PAS lancer manuellement -- launchd gere le lifecycle.

cd /Users/olivierlegendre/mes-bots-finance

# Charger .env si present (TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, etc.)
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

source venv/bin/activate

# caffeinate -dimsu : empeche Mac sleep tant que le bot vit (-d display, -i idle,
# -m disk, -s system, -u user activity). launchd survit au sleep mais APScheduler
# ratera ses crons -> on bloque le sleep pour preserver la fraicheur.
exec caffeinate -dimsu python -m bot.main
