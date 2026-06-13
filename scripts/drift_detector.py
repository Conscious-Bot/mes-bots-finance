"""Drift detector — alerte Telegram si VM derriere origin/main.

Cure session 13/06 : pendant 292 commits le code VM a derive sans qu'on le
sache (jusqu'a ce que le Telegram Conflict revele le split-brain). Cause
racine = INVISIBILITE du drift, pas absence d'auto-deploy.

Ce script ne deploie RIEN. Il detecte + alerte. Le deploiement reste un
acte humain gate (pull + alembic-avec-3-gardes + restart + healthcheck) :
cf CLAUDE.md "Migration coeur sur table sous cron" — auto-deployer du code
non-revu en prod = violation directe.

Threshold defaut = 5 commits behind. Au-dela = alerte Telegram une fois par
jour (pas plus, anti-spam). Override via env var DRIFT_THRESHOLD.

Usage :
  python3 scripts/drift_detector.py
  DRIFT_THRESHOLD=10 python3 scripts/drift_detector.py

Idempotent. Logge dans /tmp/drift_detector.log avec timestamp pour audit.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOG_FILE = Path("/tmp/drift_detector.log")
DEFAULT_THRESHOLD = 5


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}\n"
    LOG_FILE.write_text(LOG_FILE.read_text() + line if LOG_FILE.exists() else line)
    print(line, end="", file=sys.stderr)


def git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def send_telegram(text: str) -> bool:
    """Envoie alerte Telegram via .env credentials. Retourne True si OK."""
    import urllib.parse
    import urllib.request

    env_path = REPO / ".env"
    if not env_path.exists():
        log(f"ERROR : .env introuvable a {env_path}")
        return False

    env = {}
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")

    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log("ERROR : TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant dans .env")
        return False

    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with urllib.request.urlopen(url, data=data, timeout=10) as resp:
            ok = resp.status == 200
            log(f"Telegram send : HTTP {resp.status}")
            return ok
    except Exception as e:
        log(f"Telegram send failed : {e}")
        return False


def main() -> int:
    threshold = int(os.environ.get("DRIFT_THRESHOLD", DEFAULT_THRESHOLD))

    try:
        git(["fetch", "--quiet", "origin"])
        behind = int(git(["rev-list", "--count", "HEAD..origin/main"]))
        head = git(["rev-parse", "--short", "HEAD"])
        origin_head = git(["rev-parse", "--short", "origin/main"])
    except RuntimeError as e:
        log(f"ERROR git : {e}")
        return 1

    log(f"VM HEAD={head} origin/main={origin_head} behind={behind} threshold={threshold}")

    if behind == 0:
        log("Sync : VM est a jour avec origin/main")
        return 0

    if behind <= threshold:
        log(f"OK : VM {behind} commits behind (sous threshold {threshold}), pas d'alerte")
        return 0

    # Alerte
    msg = (
        f"⚠️ DRIFT DETECTOR — VM derriere origin/main\n"
        f"VM HEAD : {head}\n"
        f"origin  : {origin_head}\n"
        f"behind  : {behind} commits (threshold {threshold})\n\n"
        f"Action : SSH VM + git pull + alembic upgrade head (avec 3 gardes) + restart bot.\n"
        f"Ne PAS auto-deployer (violerait doctrine migration-sous-cron CLAUDE.md)."
    )
    if send_telegram(msg):
        log(f"ALERTE envoyee : {behind} commits behind")
    else:
        log(f"ALERTE ECHOUEE (Telegram down ?) : {behind} commits behind")
    return 0


if __name__ == "__main__":
    sys.exit(main())
