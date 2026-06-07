"""A4 cron daily : anchor thesis_integrity_log head externe.

Usage : python3 scripts/anchor_chain_head_daily.py [--push]

Sans cet anchor, A1-A3 (thesis_integrity_log) = theater (rewritable
silencieusement). Le run quotidien :
1. Calcule head courant (max seq)
2. Ecrit data/integrity_anchors/<date>.txt (git-trackable)
3. git tag -s integrity/<date>-<head8> (signed si gpg key configuree)
4. Update anchor_ref column en DB sur head seq
5. (Optionnel --push) git push origin --tags pour publier l'anchor offsite

Cron suggere (cron user crontab) :
  0 6 * * * cd /path/to/presage && /path/to/venv/bin/python3 scripts/anchor_chain_head_daily.py --push

APScheduler config dans bot/main.py (a wirer) :
  sched.add_job(anchor_chain_head_job, "cron", hour=6, minute=0)

Verify post-hoc :
  git tag -l 'integrity/*' --sort=-refname | head -10
  -> chaque tag pointe vers un commit ; le file data/integrity_anchors/<date>.txt
     fige le head a T0. Mutation locale chain detectee par re-run verify_chain.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("anchor")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--push", action="store_true",
                        help="git push origin --tags apres anchor")
    args = parser.parse_args()

    from shared import storage
    from shared.integrity import anchor_chain_head, verify_chain

    # Step 1 : check chain integrity AVANT d'ancrer
    chain = storage.get_thesis_integrity_chain()
    if not chain:
        log.info("thesis_integrity_log empty, nothing to anchor")
        return 0
    ok, broken_seq = verify_chain(chain)
    if not ok:
        log.error(
            f"CHAIN VERIFY FAILED at seq={broken_seq} -- "
            "anchoring would PERSIST corrupted state. ABORT."
        )
        return 2

    head = chain[-1]
    log.info(f"chain OK, head seq={head['seq']} hash={head['chain_hash'][:16]}...")

    # Step 2 : anchor
    result = anchor_chain_head(
        head_hash=head["chain_hash"],
        head_seq=head["seq"],
    )
    log.info(f"anchor result: {result}")

    # Step 3 : update DB anchor_ref
    if result.get("anchor_ref"):
        ok = storage.update_thesis_integrity_anchor(
            head["seq"], result["anchor_ref"]
        )
        log.info(f"DB anchor_ref update : {ok}")

    # Step 4 : optional push tags
    if args.push and result.get("git_tag_success"):
        try:
            r = subprocess.run(
                ["git", "push", "origin", "--tags"],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0:
                log.info("git push origin --tags : OK")
            else:
                log.warning(f"git push fail : {r.stderr[:200]}")
        except Exception as e:
            log.warning(f"git push exception : {e}")

    print()
    print(f"=== anchor done : {result.get('anchor_ref')} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
