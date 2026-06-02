"""Telecharge tous les favicons des tickers PRESAGE en local.

Source primaire : Google favicon API (sz=128 pour quality max)
Source secondaire : DuckDuckGo icons (HD: 256x256)
Output : dashboard/static/brand/logos/{TICKER}.png

Apres run, le dashboard fonctionne 100% offline (pas de fetch externe au
chargement). Re-run safe : skip si fichier deja present (ou --force pour ecraser).

Usage:
  python3 scripts/download_logos.py        # incrementiel
  python3 scripts/download_logos.py --force # re-download tout
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.ticker_logos import TICKER_DOMAIN

LOGOS_DIR = ROOT / "dashboard" / "static" / "brand" / "logos"
LOGOS_DIR.mkdir(parents=True, exist_ok=True)

# Default Google favicon "globe" placeholder = 726 bytes. Skip si on get ca.
GOOGLE_DEFAULT_SIZE = 726


def fetch_google(domain: str) -> bytes | None:
    """Try Google favicon API. Return bytes or None si pas de vrai favicon."""
    url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
    try:
        r = requests.get(url, allow_redirects=True, timeout=15)
        if r.status_code != 200:
            return None
        # Google returns 726b default globe if no favicon found
        if len(r.content) <= GOOGLE_DEFAULT_SIZE + 50:
            return None
        return r.content
    except Exception as e:
        print(f"    google fetch error: {e}", file=sys.stderr)
        return None


def fetch_ddg(domain: str) -> bytes | None:
    """Try DuckDuckGo icons (HD 256x256) en fallback."""
    url = f"https://icons.duckduckgo.com/ip3/{domain}.ico"
    try:
        r = requests.get(url, allow_redirects=True, timeout=15)
        if r.status_code != 200 or len(r.content) < 200:
            return None
        return r.content
    except Exception as e:
        print(f"    ddg fetch error: {e}", file=sys.stderr)
        return None


def main(force: bool = False) -> None:
    n_saved, n_skipped, n_failed = 0, 0, 0
    n_total = len(TICKER_DOMAIN)
    for i, (ticker, domain) in enumerate(TICKER_DOMAIN.items(), 1):
        # Sanitize ticker pour filename (eviter / dans Windows)
        safe = ticker.replace("/", "_")
        out = LOGOS_DIR / f"{safe}.png"
        if out.exists() and not force:
            n_skipped += 1
            print(f"[{i:3}/{n_total}] {ticker:14} : cached")
            continue
        # 1. Try Google
        data = fetch_google(domain)
        src = "google"
        if not data:
            # 2. Fallback DDG
            data = fetch_ddg(domain)
            src = "ddg"
        if data:
            out.write_bytes(data)
            n_saved += 1
            print(f"[{i:3}/{n_total}] {ticker:14} ({domain[:30]:30}) -> {src} {len(data):>5}b")
        else:
            n_failed += 1
            print(f"[{i:3}/{n_total}] {ticker:14} ({domain[:30]:30}) -> FAILED")
    print(f"\nSummary : {n_saved} saved / {n_skipped} cached / {n_failed} failed / {n_total} total")
    print(f"Output : {LOGOS_DIR}")


if __name__ == "__main__":
    force = "--force" in sys.argv
    main(force=force)
