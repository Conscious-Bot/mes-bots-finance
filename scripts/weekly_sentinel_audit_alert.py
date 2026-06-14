#!/usr/bin/env python3
"""
Weekly sentinel audit alert — Sunday morning Telegram reminder.

Fires from launchd LaunchAgent `com.olivier.presage-weekly-audit.plist`
every Sunday at 09:13 local. Sends a Telegram alert summarizing pending
sentinelles state + urging /sentinel-status invocation in Claude Code.

Lightweight by design : just count pending + flag urgent deadlines (<30d).
Full Bigdata fact-check happens when user actually runs /sentinel-status.
"""
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime
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


def sentinel_summary() -> str:
    if not DB_PATH.exists():
        return "[WEEKLY SENTINEL AUDIT]\nDB not found at expected path. Run /sentinel-status manually."

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.execute(
        """SELECT id, ticker, claim_type, target_date
           FROM predictions
           WHERE origin='manual' AND outcome IS NULL
           ORDER BY target_date"""
    )
    rows = list(cur)
    today = datetime.now().date()
    red, yellow, green = 0, 0, 0
    urgent_pids = []
    for pid, ticker, _ctype, td in rows:
        if not td:
            yellow += 1
            continue
        try:
            d = datetime.fromisoformat(td).date()
            days = (d - today).days
            if days < 30:
                red += 1
                urgent_pids.append((pid, ticker or "-", days))
            elif days < 90:
                yellow += 1
            else:
                green += 1
        except (ValueError, TypeError):
            yellow += 1

    n = len(rows)
    msg = [
        "[WEEKLY SENTINEL AUDIT]",
        f"Pending sentinelles : {n}",
        f"  RED (<30j)    : {red}",
        f"  YELLOW (30-90j): {yellow}",
        f"  GREEN (>90j)   : {green}",
    ]
    if urgent_pids:
        msg.append("")
        msg.append("URGENT (RED) :")
        for pid, ticker, days in urgent_pids[:5]:
            msg.append(f"  pid={pid} {ticker} ({days}j)")
    msg.append("")
    msg.append("Run /sentinel-status in Claude Code for full fact-check + actions.")
    return "\n".join(msg)


def main():
    msg = sentinel_summary()
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
