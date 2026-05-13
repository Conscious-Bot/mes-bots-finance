"""Phase C9 — 8-K filings categorization + severity classification.

Auto-classify SEC 8-K items by severity (catastrophic/high/medium/low) and persist
to filings_8k_log. Push immediate alerts for high+catastrophic.

Item severity taxonomy aligned with SEC 8-K General Instructions + market signal value.
"""

import logging

log = logging.getLogger(__name__)


ITEM_SEVERITY = {
    # CATASTROPHIC — restatement / material misstatement
    "4.02": ("catastrophic", "Non-reliance on previously issued financial statements"),
    # HIGH — red flag, often precedes material price move
    "4.01": ("high", "Auditor change/dismissal"),
    "5.02": ("high", "Officer/director departure or change"),
    "5.04": ("high", "Temporary suspension of trading under retirement plans"),
    "3.01": ("high", "Delisting notice / failure to satisfy listing"),
    # MEDIUM — material events worth attention
    "1.01": ("medium", "Entry into material agreement"),
    "1.02": ("medium", "Termination of material agreement"),
    "1.03": ("medium", "Bankruptcy or receivership"),
    "2.01": ("medium", "Completion of acquisition/disposition"),
    "2.02": ("medium", "Results of operations / financial condition (earnings)"),
    "2.03": ("medium", "Material direct financial obligation"),
    "2.04": ("medium", "Triggering event accelerating obligation"),
    "2.05": ("medium", "Costs associated with exit/disposal"),
    "2.06": ("medium", "Material impairments"),
    "3.02": ("medium", "Unregistered equity sales"),
    "3.03": ("medium", "Material modification to rights of holders"),
    "5.01": ("medium", "Changes in control of registrant"),
    "5.03": ("medium", "Amendments to articles/bylaws"),
    "5.07": ("medium", "Submission of matters to vote of holders"),
    "5.08": ("medium", "Shareholder director nominations"),
    "8.01": ("medium", "Other events (material)"),
    # LOW — administrative / routine
    "6.01": ("low", "ABS informational and computational material"),
    "6.02": ("low", "Change of servicer or trustee"),
    "6.03": ("low", "Change in credit enhancement"),
    "6.04": ("low", "Failure to make required distribution"),
    "6.05": ("low", "Securities Act updating disclosure"),
    "7.01": ("low", "Regulation FD disclosure (default low)"),
    "9.01": ("low", "Financial statements and exhibits"),
}

SEVERITY_ORDER = {"catastrophic": 4, "high": 3, "medium": 2, "low": 1, "unknown": 0}


def classify_severity(item_codes):
    """Given list of item codes, return (severity, reason) by max severity."""
    if not item_codes:
        return ("unknown", "No items reported")
    best_sev = "low"
    best_reason = ""
    best_code = ""
    for code in item_codes:
        if code in ITEM_SEVERITY:
            sev, reason = ITEM_SEVERITY[code]
            if SEVERITY_ORDER[sev] > SEVERITY_ORDER[best_sev]:
                best_sev = sev
                best_reason = reason
                best_code = code
    if not best_reason:
        return ("unknown", f"Unrecognized items: {','.join(item_codes)}")
    return (best_sev, f"Item {best_code}: {best_reason}")


def scan_and_log_8k_filings(tickers, days=7):
    """Scan list of tickers for new 8-K filings, persist, return newly-logged rows."""
    from shared import edgar, storage

    new_logged = []
    for tk in tickers:
        try:
            filings = edgar.get_recent_8k_filings(tk, days=days)
            for f in filings:
                if storage.get_8k_filing_by_accession(f["accession"]):
                    continue
                severity, reason = classify_severity(f["item_codes"])
                row_id = storage.log_8k_filing(
                    ticker=tk,
                    cik=f["cik"],
                    accession=f["accession"],
                    filed_at=f["filed_at"],
                    items_raw=f["items_raw"],
                    item_codes=f["item_codes"],
                    severity=severity,
                    severity_reason=reason,
                    filing_url=f["url"],
                )
                if row_id:
                    log.info(f"8-K logged: {tk} {f['filed_at']} {f['items_raw']} [{severity}] id={row_id}")
                    new_logged.append(
                        {"id": row_id, "ticker": tk, **f, "severity": severity, "severity_reason": reason}
                    )
        except Exception as e:
            log.warning(f"scan_and_log_8k {tk} failed: {e}")
    return new_logged


def format_8k_alert(row):
    """Single 8-K alert for push notification."""
    icon = {"catastrophic": "CATASTROPHIC", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}.get(row["severity"], "?")
    lines = [f"8-K [{icon}] {row['ticker']} ({row['filed_at'][:10]})"]
    lines.append(f"Items: {row.get('items_raw') or '?'}")
    if row.get("severity_reason"):
        lines.append(row["severity_reason"])
    if row.get("url") or row.get("filing_url"):
        lines.append(row.get("url") or row["filing_url"])
    return "\n".join(lines)


def format_8k_list(rows):
    """List view for /recent_8k handler."""
    if not rows:
        return "No 8-K filings matching filters."
    lines = [f"8-K FILINGS ({len(rows)} rows)"]
    for r in rows:
        icon = {"catastrophic": "!!!", "high": "!!", "medium": "!", "low": "-"}.get(r["severity"], "?")
        items = r.get("items_raw") or "?"
        lines.append(f"\n{icon} {r['ticker']:6s} {r['filed_at'][:10]} | {r['severity']:13s} | {items}")
        if r.get("severity_reason"):
            lines.append(f"   {r['severity_reason'][:120]}")
    return "\n".join(lines)
