"""S0 SOCLE : OTS anchor daily cron job.

Cf SPEC_SOCLE.md S5 (substrat de provabilite) + HANDOFF_SOCLE.md S0.
Wrapper APScheduler du script bash canonique scripts/integrity_anchor.sh.

Pourquoi un wrapper : APScheduler tient l'orchestration du bot ; le script
shell tient la logique d'ancrage (commit-reveal hiding sur predictions +
transparent sur theses, OTS stamp, git commit + push). Separation propre.

Daily 6h (avant l'ouverture marche, post-backup 4h, post-calendar 5h).
Pourquoi 6h : 1 anchor / jour suffit ; les calendars Bitcoin ont besoin
de ~quelques heures pour confirmation bloc (asynchrone).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger("bot")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "integrity_anchor.sh"


def integrity_anchor_daily_job() -> None:
    """Run OTS anchor on prediction + thesis chains, commit + push.

    Failure modes (logged, not raised - le bot continue) :
    - ledger vide (premiere fois) : OK, log info
    - ots binary absent : ERROR log
    - git push fail : WARN log (OTS reste la preuve trustless)
    - chain verify fail (L15) : ERROR log + abort sans commit (le script
      lui-meme abort via SystemExit dans le block python embarque)
    """
    if not _SCRIPT.exists():
        log.error("integrity_anchor.sh missing at %s", _SCRIPT)
        return
    try:
        result = subprocess.run(
            ["bash", str(_SCRIPT)],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            log.info("integrity_anchor OK : %s", result.stdout.strip().splitlines()[-1] if result.stdout else "")
        else:
            log.error("integrity_anchor failed rc=%d : %s", result.returncode, result.stderr.strip())
    except subprocess.TimeoutExpired:
        log.error("integrity_anchor timeout (600s) -- calendars OTS injoignables ?")
    except Exception as e:
        log.exception("integrity_anchor unexpected error : %s", e)
