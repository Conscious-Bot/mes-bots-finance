"""Sprint 8 — Backfill pre_mortems on active theses missing one.

Usage :
    venv/bin/python -m scripts.backfill_pre_mortems         # dry-run (count + cost estimate)
    venv/bin/python -m scripts.backfill_pre_mortems --run   # actually generate
    venv/bin/python -m scripts.backfill_pre_mortems --run --limit 5  # cap batch

Why : 40 theses actives sans pre_mortem -> copilot voit "(no pre-mortem on file)"
et perd un anchor majeur dans l'argumentaire. Sprint 8 = re-generation batch
Opus pour rattraper la dette.

Cost estimate : ~$0.03 par these (Opus 2k out) * 40 = ~$1.2.
"""

import argparse
import logging
import sys
import time

from intelligence import pre_mortem as pm_mod
from shared import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("backfill_pre_mortems")


def fetch_missing(limit: int | None = None) -> list[dict]:
    """Read active theses without pre_mortem."""
    q = (
        "SELECT id, ticker, opened_at, conviction, direction, horizon, "
        "key_drivers, invalidation_triggers, entry_price, target_partial, "
        "target_full, stop_price "
        "FROM theses WHERE status='active' AND pre_mortem IS NULL "
        "ORDER BY conviction DESC, opened_at ASC"
    )
    if limit:
        q += f" LIMIT {int(limit)}"
    with storage.db() as cx:
        rows = cx.execute(q).fetchall()
    cols = [
        "id", "ticker", "opened_at", "conviction", "direction", "horizon",
        "key_drivers", "invalidation_triggers", "entry_price", "target_partial",
        "target_full", "stop_price",
    ]
    return [dict(zip(cols, r, strict=False)) for r in rows]


def run_backfill(theses: list[dict], dry_run: bool = True) -> dict:
    out = {"ok": 0, "fail": 0, "elapsed_s": 0.0}
    t0 = time.time()
    for i, th in enumerate(theses, 1):
        log.info(f"[{i}/{len(theses)}] {th['ticker']} c{th['conviction']} (opened {th['opened_at'][:10]})")
        if dry_run:
            continue
        try:
            pm_json = pm_mod.generate_pre_mortem(th)
            if pm_json:
                storage.update_thesis_pre_mortem(th["id"], pm_json)
                out["ok"] += 1
            else:
                out["fail"] += 1
                log.warning("  failed: generate_pre_mortem returned None")
        except Exception as e:
            out["fail"] += 1
            log.warning(f"  failed: {type(e).__name__}: {e}")
        time.sleep(0.5)  # tiny rate-limit cushion
    out["elapsed_s"] = round(time.time() - t0, 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="actually generate (otherwise dry-run)")
    ap.add_argument("--limit", type=int, default=None, help="cap number of theses processed")
    args = ap.parse_args()

    theses = fetch_missing(limit=args.limit)
    log.info(f"Active theses without pre_mortem : {len(theses)}")
    if not theses:
        return 0
    cost_estimate = len(theses) * 0.03
    log.info(f"Cost estimate (Opus ~$0.03/pre_mortem) : ~${cost_estimate:.2f}")

    if not args.run:
        log.info("DRY-RUN — no Opus calls made. Re-run with --run to execute.")
        run_backfill(theses, dry_run=True)
        return 0

    log.info(f"RUNNING backfill on {len(theses)} theses...")
    res = run_backfill(theses, dry_run=False)
    log.info(f"DONE : ok={res['ok']} fail={res['fail']} elapsed={res['elapsed_s']}s")
    return 0 if res["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
