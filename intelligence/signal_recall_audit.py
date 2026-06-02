"""#69 LOOP -- Audit recall signal coverage (mesurer ce qu'on rate).

Compare les 8-K filings reels sur sec.gov vs ce qu'on a en table signals.
Mesure le recall (% des filings externes captures par notre wire) par
ticker et globalement.

Pourquoi : sans recall, on ne sait pas si notre wire EDGAR rate des
filings (rate-limit, crash silencieux, dedup-key buggee). Le Brier
disaggregue (#72) calibre la precision des signaux qu'on a, mais ne
detecte pas ceux qu'on aurait du avoir.

Pattern :
- get_recent_8k_filings(ticker, days_back) -> verite externe SEC
- query signals WHERE gmail_id LIKE 'sec_8k:%' -> capture interne
- compare par accession_number normalise
- output : {n_external, n_captured, recall_pct, missing[], extra[]}

Le mock pattern est important : les tests stubent get_recent_8k_filings
pour ne pas hit sec.gov. En prod, on appelle le helper reel.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

log = logging.getLogger(__name__)


def _normalize_accession(acc: str | None) -> str:
    """Normalise un accession number (enleve tirets, lowercase)."""
    if not acc:
        return ""
    return str(acc).replace("-", "").strip().lower()


def audit_ticker_8k_recall(
    cx: sqlite3.Connection,
    ticker: str,
    days_back: int = 30,
    edgar_fetcher: Any = None,
) -> dict[str, Any]:
    """Audit recall 8-K pour un ticker.

    Args:
        cx: connexion sqlite3
        ticker: ticker UPPER-CASE
        days_back: fenetre temporelle (default 30j)
        edgar_fetcher: callable(ticker, days_back) -> list of {accession, ...}
            Default = shared.edgar.get_recent_8k_filings (prod)
            Override pour tests.

    Returns:
        dict avec :
            ticker, days_back
            n_external (filed sur sec.gov)
            n_captured (en signals)
            recall_pct (None si n_external=0)
            missing_accessions : ceux que SEC a mais on n'a pas
            extra_accessions : ceux qu'on a mais SEC ne montre pas
                               (peu probable, signe potentiel de dedup buggy
                                ou orphan rows)
            status : 'OK' / 'WARN' / 'ALERT' / 'INSUFFICIENT_DATA'
    """
    ticker = ticker.upper()
    if edgar_fetcher is None:
        from shared.edgar import get_recent_8k_filings
        edgar_fetcher = get_recent_8k_filings

    # External truth (SEC)
    try:
        external = edgar_fetcher(ticker, days_back) or []
    except Exception as e:
        log.warning(f"recall_audit {ticker}: fetcher failed: {e}")
        return {
            "ticker": ticker,
            "days_back": days_back,
            "error": f"fetcher: {type(e).__name__}",
            "status": "INSUFFICIENT_DATA",
        }
    external_accs = {_normalize_accession(f.get("accession")) for f in external}
    external_accs.discard("")

    # Internal capture
    cutoff_sql = f"-{days_back} days"
    rows = cx.execute(
        "SELECT gmail_id FROM signals "
        "WHERE gmail_id LIKE 'sec_8k:%' "
        "AND timestamp >= datetime('now', ?) "
        "AND entities LIKE ?",
        (cutoff_sql, f'%"{ticker}"%'),
    ).fetchall()
    internal_accs: set[str] = set()
    for r in rows:
        gid = r[0] if not isinstance(r, dict) else r.get("gmail_id")
        if gid and gid.startswith("sec_8k:"):
            internal_accs.add(_normalize_accession(gid.split(":", 1)[1]))

    missing = external_accs - internal_accs
    extra = internal_accs - external_accs
    n_external = len(external_accs)
    n_captured = len(external_accs & internal_accs)

    recall_pct = round(n_captured / n_external * 100, 1) if n_external > 0 else None

    if n_external == 0:
        status = "INSUFFICIENT_DATA"  # rien a auditer
    elif recall_pct is not None and recall_pct >= 90:
        status = "OK"
    elif recall_pct is not None and recall_pct >= 70:
        status = "WARN"
    else:
        status = "ALERT"

    return {
        "ticker": ticker,
        "days_back": days_back,
        "n_external": n_external,
        "n_captured": n_captured,
        "recall_pct": recall_pct,
        "missing_accessions": sorted(missing),
        "extra_accessions": sorted(extra),
        "status": status,
    }


def audit_all_8k_recall(
    cx: sqlite3.Connection,
    tickers: list[str],
    days_back: int = 30,
    edgar_fetcher: Any = None,
) -> dict[str, Any]:
    """Audit recall agrege sur N tickers.

    Returns:
        {
            days_back, n_tickers, n_with_external, n_audited,
            per_ticker : [audit dict per ticker],
            global_recall_pct : weighted by n_external,
            status : worst sub-status
        }
    """
    per_ticker = []
    total_external = 0
    total_captured = 0
    for tk in tickers:
        rec = audit_ticker_8k_recall(cx, tk, days_back=days_back, edgar_fetcher=edgar_fetcher)
        per_ticker.append(rec)
        if rec.get("n_external"):
            total_external += rec["n_external"]
            total_captured += rec["n_captured"]

    n_with_external = sum(1 for r in per_ticker if r.get("n_external"))
    global_recall = round(total_captured / total_external * 100, 1) if total_external > 0 else None

    # Global status agrege : pire que les sub-status
    statuses = [r.get("status", "INSUFFICIENT_DATA") for r in per_ticker]
    if "ALERT" in statuses:
        global_status = "ALERT"
    elif "WARN" in statuses:
        global_status = "WARN"
    elif "OK" in statuses:
        global_status = "OK"
    else:
        global_status = "INSUFFICIENT_DATA"

    return {
        "days_back": days_back,
        "n_tickers": len(tickers),
        "n_with_external": n_with_external,
        "n_audited": len(per_ticker),
        "per_ticker": per_ticker,
        "total_external": total_external,
        "total_captured": total_captured,
        "global_recall_pct": global_recall,
        "status": global_status,
    }
