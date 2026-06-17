#!/usr/bin/env python3
"""
Weekly triggers-check alert — Monday morning Telegram reminder.

Fires from launchd LaunchAgent `com.olivier.presage-weekly-triggers.plist`
every Monday at 09:00 local. Sends a Telegram alert summarizing thesis
triggers state + urging /triggers-check invocation in Claude Code.

Lightweight by design : count active theses, total triggers, fired triggers
via cross-ref module. Full Bigdata.com fact-check happens when user actually
runs /triggers-check.
"""
import json
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB_PATH = REPO / "data" / "bot.db"


def load_telegram_creds():
    """Read .env and extract Telegram bot credentials."""
    env_path = REPO / ".env"
    if not env_path.exists():
        return None, None
    token, chat_id = None, None
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            token = line.split("=", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("TELEGRAM_CHAT_ID="):
            chat_id = line.split("=", 1)[1].strip().strip('"').strip("'")
    return token, chat_id


def send_telegram(text: str) -> bool:
    token, chat_id = load_telegram_creds()
    if not token or not chat_id:
        print("ERROR: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env", file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"ERROR telegram send: {e}", file=sys.stderr)
        return False


def triggers_summary() -> str:
    if not DB_PATH.exists():
        return "[WEEKLY TRIGGERS CHECK]\nDB not found. Run /triggers-check manually."

    sys.path.insert(0, str(REPO))
    try:
        from shared.invalidation_triggers import get_trigger_status_per_thesis
        get_trigger_status_per_thesis.cache_clear()
        all_status = get_trigger_status_per_thesis()
    except Exception as e:
        print(f"ERROR cross-ref module: {e}", file=sys.stderr)
        all_status = {}

    cx = sqlite3.connect(str(DB_PATH))
    rows = cx.execute(
        "SELECT ticker, conviction, invalidation_triggers FROM theses WHERE status='active' ORDER BY conviction DESC, ticker"
    ).fetchall()
    cx.close()

    n_theses = len(rows)
    total_triggers = 0
    fired_tickers: list[tuple[str, int, int, int]] = []  # (ticker, conviction, fired, total)

    for ticker, conviction, raw in rows:
        try:
            triggers = json.loads(raw) if raw else []
        except json.JSONDecodeError:
            triggers = []
        total_triggers += len(triggers)
        status_list = all_status.get(ticker, [])
        n_fired = sum(1 for x in status_list if x.get("fired"))
        if n_fired > 0:
            fired_tickers.append((ticker, conviction, n_fired, len(triggers)))

    total_fired = sum(f for _, _, f, _ in fired_tickers)

    msg = [
        "[WEEKLY TRIGGERS CHECK]",
        f"Active theses : {n_theses}",
        f"Total triggers : {total_triggers}",
        f"Fired triggers : {total_fired}/{total_triggers}",
    ]
    if fired_tickers:
        msg.append("")
        msg.append("FIRED (action requise) :")
        for ticker, conv, fired, n in fired_tickers[:10]:
            msg.append(f"  {ticker} (c{conv}) : {fired}/{n} fired")
    else:
        msg.append("")
        msg.append("Aucun trigger fired actuellement. Toutes thèses INTACTES.")
    msg.append("")
    msg.append("Run /triggers-check in Claude Code for full Bigdata.com fact-check + rewrites.")
    return "\n".join(msg)


def main():
    msg = triggers_summary()
    print(msg)
    ok = send_telegram(msg)
    if ok:
        print("[OK] Telegram alert envoyee")
        sys.exit(0)
    else:
        print("[FAIL] Telegram send failed", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
