"""Drift report: target vs actual per account.

Output: Markdown to stdout.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import storage


def main():
    report = storage.compute_drift_report()

    lines = []
    lines.append("# Portfolio Drift Report — 2026-05-15")
    lines.append("")

    for account in ("PEA", "TR"):
        if account not in report:
            continue
        block = report[account]
        locked_note = " (LOCKED)" if account == "PEA" else ""
        lines.append(f"## {account}{locked_note}")
        lines.append("")
        lines.append("| Ticker | Target | Actual | Drift | Status | W | Bucket |")
        lines.append("|---|---:|---:|---:|---|---:|---|")

        for row in sorted(block["rows"], key=lambda r: -abs(r["drift_eur"])):
            t = row["ticker"]
            tgt = row["target_eur"]
            act = row["actual_eur"]
            drift = row["drift_eur"]
            status = row["status"]
            week = row.get("phase_week") or ""
            bucket = row.get("bucket") or ""
            drift_str = f"+€{drift:,.0f}" if drift > 0 else f"€{drift:,.0f}"
            lines.append(f"| {t} | €{tgt:,.0f} | €{act:,.0f} | {drift_str} | {status} | {week} | {bucket} |")

        lines.append("")
        lines.append(f"**Total {account}**: target €{block['total_target']:,.0f}, actual €{block['total_actual']:,.0f}, drift €{block['total_drift']:+,.0f}")
        lines.append("")

    s = report["summary"]
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Capital deployed: €{s['capital_deployed_eur']:,.0f}")
    lines.append(f"- Capital pending: €{s['capital_pending_eur']:,.0f}")
    lines.append(f"- Capital target: €{s['capital_target_eur']:,.0f}")
    lines.append(f"- % deployed: {s['pct_deployed']:.1f}%")
    lines.append("")

    # Top W1 priorities
    lines.append("## Priority Buys — Week 1")
    lines.append("")
    w1 = []
    for account, block in report.items():
        if account == "summary":
            continue
        for row in block.get("rows", []):
            if row.get("phase_week") == 1 and row["status"] == "planned":
                w1.append(row)
    for row in sorted(w1, key=lambda r: -r["target_eur"]):
        lines.append(f"- **{row['ticker']}** €{row['target_eur']:,.0f}  ({row['narrative']})")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
