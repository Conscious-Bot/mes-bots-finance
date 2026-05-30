"""Phase C9 — 8-K filings categorization + severity classification.

Auto-classify SEC 8-K items by severity (catastrophic/high/medium/low) and persist
to filings_8k_log. Push immediate alerts for high+catastrophic.

Item severity taxonomy aligned with SEC 8-K General Instructions + market signal value.
"""

import logging

from pydantic import BaseModel

from shared.data_source_base import BaseDataSource

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


class EightKFiling(BaseModel):
    """Pydantic schema for validated 8-K filing (Sprint 1.2 item 3c)."""

    ticker: str
    cik: str
    accession: str
    filed_at: str
    items_raw: str
    item_codes: list[str]
    url: str
    severity: str
    severity_reason: str


class EightKSource(BaseDataSource):
    """SEC 8-K filing ingestion across watchlist tickers (Sprint 1.2)."""

    source_name = "sec_8k"
    rate_limit_rpm = 300  # SEC EDGAR conservative (10 req/sec public limit)

    def __init__(self, tickers: list[str], days: int = 7) -> None:
        super().__init__()
        self.tickers = tickers
        self.days = days
        # Backward-compat: collect newly-logged rows for legacy return value
        self.new_logged: list[dict] = []

    def fetch(self, since=None):
        """Fetch 8-K filings across all watchlist tickers (flatten to per-filing list)."""
        from shared import edgar

        out = []
        for tk in self.tickers:
            try:
                filings = edgar.get_recent_8k_filings(tk, days=self.days)
                for f in filings:
                    out.append({"ticker": tk, **f})
            except Exception as e:
                log.warning(f"fetch 8-K for {tk} failed: {e}")
        return out

    def validate(self, raw):
        """Dedup + classify severity. Returns EightKFiling or None (skip)."""
        from shared import storage

        if storage.get_8k_filing_by_accession(raw["accession"]):
            return None  # silent dedup skip
        severity, reason = classify_severity(raw["item_codes"])
        return EightKFiling(
            ticker=raw["ticker"],
            cik=raw["cik"],
            accession=raw["accession"],
            filed_at=raw["filed_at"],
            items_raw=raw["items_raw"],
            item_codes=raw["item_codes"],
            url=raw["url"],
            severity=severity,
            severity_reason=reason,
        )

    def persist(self, validated: EightKFiling, provenance):
        """Insert into filings_8k_log table + accumulate for legacy return value."""
        from shared import storage

        row_id = storage.log_8k_filing(
            ticker=validated.ticker,
            cik=validated.cik,
            accession=validated.accession,
            filed_at=validated.filed_at,
            items_raw=validated.items_raw,
            item_codes=validated.item_codes,
            severity=validated.severity,
            severity_reason=validated.severity_reason,
            filing_url=validated.url,
        )
        if row_id:
            log.info(
                f"8-K logged: {validated.ticker} {validated.filed_at} "
                f"{validated.items_raw} [{validated.severity}] id={row_id}"
            )
            filing_dict = {
                "id": row_id,
                "ticker": validated.ticker,
                "cik": validated.cik,
                "accession": validated.accession,
                "filed_at": validated.filed_at,
                "items_raw": validated.items_raw,
                "item_codes": validated.item_codes,
                "url": validated.url,
                "severity": validated.severity,
                "severity_reason": validated.severity_reason,
            }
            self.new_logged.append(filing_dict)

            # Wire vers signals -> V2 -> predictions (audit 30/05 A3 iter 6+).
            # Sync : extract content + call V2 + insert signal + register prediction
            # ajoute ~5-10s par 8-K. Acceptable inline. Forward-only, dedupe via
            # gmail_id='sec_8k:{accession}'. Echec non-bloquant pour le log filing.
            try:
                from intelligence.edgar_signal_wire import wire_and_register_8k

                result = wire_and_register_8k(filing_dict)
                if result["wired"]:
                    log.info(
                        f"8-K wired: {validated.ticker} accession={validated.accession} -> "
                        f"signal_id={result['signal_id']}, preds={len(result['registered_predictions'])}"
                    )
                else:
                    log.info(
                        f"8-K skip wire: {validated.ticker} accession={validated.accession} "
                        f"({result.get('reason_if_skipped', 'unknown')})"
                    )
            except Exception as wire_err:
                log.warning(
                    f"8-K wire failed (non-blocking) for {validated.ticker} "
                    f"{validated.accession}: {type(wire_err).__name__}: {wire_err}"
                )
        return row_id


def scan_and_log_8k_filings(tickers, days=7):
    """Scan list of tickers for new 8-K filings, persist, return newly-logged rows.

    Sprint 1.2 item 3c: thin wrapper around EightKSource. Cron entry point
    (bot/main.scheduled_8k_scan_job) unchanged.
    """
    source = EightKSource(tickers=tickers, days=days)
    source.ingest()
    return source.new_logged


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
    """List view canonical (TG output spec 21/05/2026): grouped by severity with emoji."""
    import re as _re

    if not rows:
        return "🚨 8-K FILINGS — 0 rows\nNo 8-K filings matching filters."

    groups: dict[str, list] = {"catastrophic": [], "high": [], "medium": [], "low": [], "unknown": []}
    for r in rows:
        sev = r.get("severity", "unknown") or "unknown"
        if sev not in groups:
            sev = "unknown"
        groups[sev].append(r)

    lines = [f"🚨 8-K FILINGS — {len(rows)} rows (60d window)"]
    summary_parts = []
    for sev_name, label in [
        ("catastrophic", "CATASTROPHIC"),
        ("high", "HIGH"),
        ("medium", "MEDIUM"),
        ("low", "LOW"),
        ("unknown", "UNKNOWN"),
    ]:
        n = len(groups[sev_name])
        if n > 0:
            summary_parts.append(f"{n} {label}")
    if summary_parts:
        lines.append("Severity: " + " | ".join(summary_parts))
    lines.append("")

    sev_emoji = {
        "catastrophic": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢",
        "unknown": "⚪",
    }

    def _clean_desc(reason):
        if not reason:
            return ""
        return _re.sub(r"^Item \d+\.\d+:\s*", "", reason).strip()

    for sev in ["catastrophic", "high", "medium", "low", "unknown"]:
        items = groups[sev]
        if not items:
            continue
        emoji = sev_emoji.get(sev, "⚪")
        lines.append(f"━ {sev.upper()} ({len(items)}) ━")
        for r in items:
            items_raw = r.get("items_raw") or "?"
            ticker = r["ticker"]
            date = r["filed_at"][:10]
            desc = _clean_desc(r.get("severity_reason"))
            if desc and len(desc) > 60:
                desc = desc[:57] + "..."
            if desc:
                lines.append(f"{emoji} {ticker:8s} {date}  {desc}  ({items_raw})")
            else:
                lines.append(f"{emoji} {ticker:8s} {date}  ({items_raw})")
        lines.append("")

    return "\n".join(lines).rstrip()
