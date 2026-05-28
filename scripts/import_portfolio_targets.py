"""Import portfolio targets from allocation document 2026-05-15.

Idempotent: deletes existing targets where source_doc matches, then re-inserts.
"""

# Find DB path via storage module
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared import storage

SOURCE_DOC = "allocation_2026-05-15"

# Format: (ticker, account, bucket, target_eur, target_weight_pct, narrative, priority, status, phase_week)
TARGETS = [
    # PEA LOCKED — 6 positions, €11,384
    ("ASML.AS", "PEA", "core_ai", 3930, 6.1, "EUV monopole + PEA-elig", "tier_s", "locked", None),
    ("STMPA.PA", "PEA", "semis", 2205, 3.4, "STM Paris listing (STM classic)", "tier_a", "locked", None),
    ("SU.PA", "PEA", "power", 1581, 2.5, "Schneider Electric grid", "tier_a", "locked", None),
    ("BESI.AS", "PEA", "semis_supporting", 1567, 2.4, "Hybrid bonding equip", "tier_a", "locked", None),
    ("HO.PA", "PEA", "defense", 1554, 2.4, "Thales defense electronics", "tier_a", "locked", None),
    ("SAF.PA", "PEA", "aerospace", 547, 0.8, "Safran engines", "tier_b", "locked", None),
    # TR Déjà exécuté — 15 positions, €32,000
    ("4063.T", "TR", "core_ai", 4500, 7.0, "Shin-Etsu wafer #1 + HPQ vertical", "tier_s", "executed", None),
    ("TSM", "TR", "core_ai", 4000, 6.2, "TSMC fab unique tous chips avances", "tier_s", "executed", None),
    ("SNPS", "TR", "core_ai", 3000, 4.7, "EDA toll road + Ansys robotics", "tier_s", "executed", None),
    (
        "7011.T",
        "TR",
        "power",
        3500,
        5.4,
        "MHI turbines + nuclear + defense (incl topup planned W1)",
        "tier_s",
        "executed",
        1,
    ),
    ("000660.KS", "TR", "core_ai", 2000, 3.1, "SK Hynix HBM monopole ~50% PDM", "tier_s", "executed", None),
    ("KLAC", "TR", "core_ai", 2000, 3.1, "Process control quasi-monopole", "tier_s", "executed", None),
    ("6920.T", "TR", "core_ai", 2000, 3.1, "Lasertec EUV mask inspection", "tier_s", "executed", None),
    ("MRVL", "TR", "core_ai", 2000, 3.1, "AWS Trainium design partner", "tier_s", "executed", None),
    ("AVGO", "TR", "core_ai", 1500, 2.3, "Custom silicon Google/Meta", "tier_a", "executed", None),
    ("TER", "TR", "semis", 1500, 2.3, "Teradyne semi test", "tier_a", "executed", None),
    ("ALAB", "TR", "moonshots", 1500, 2.3, "PCIe retimers AI connectivity", "tier_b", "executed", None),
    ("COHR", "TR", "chokepoints", 1500, 2.3, "Photonics + co-packaged optics", "tier_a", "executed", None),
    ("AMD", "TR", "semis", 1500, 2.3, "AMD legacy hold", "tier_b", "executed", None),
    ("GOOGL", "TR", "tech_mega", 1500, 2.3, "Alphabet AI infra", "tier_a", "executed", None),
    ("TSLA", "TR", "moonshots", 1000, 1.6, "Tesla legacy hold", "tier_b", "executed", None),
    # TR Planifié — 11 positions, €19,000 (no double-count of 7011.T topup which is rolled into executed row)
    ("AMZN", "TR", "tech_mega", 3000, 4.7, "Amazon DCA 3x1000", "tier_s", "planned", 2),
    ("0388.HK", "TR", "asia", 2500, 3.9, "HKEX pure-play exchange", "tier_s", "planned", 1),
    ("HDB", "TR", "asia", 2000, 3.1, "HDFC Bank India quality compounder", "tier_a", "planned", 1),
    ("6890.T", "TR", "chokepoints", 2000, 3.1, "Ferrotec semi consumables", "tier_a", "planned", 1),
    ("GEV", "TR", "power", 2000, 3.1, "GE Vernova power gen US DCA 2x1000", "tier_s", "planned", 3),
    ("0700.HK", "TR", "asia", 1500, 2.3, "Tencent Wechat moat + buyback", "tier_a", "planned", 1),
    ("ACMR", "TR", "semis_supporting", 1500, 2.3, "ACM Research SAPS cleaning", "tier_a", "planned", 2),
    ("BWXT", "TR", "power", 1500, 2.3, "BWXT naval + TRISO fuel", "tier_a", "planned", 2),
    ("CEG", "TR", "power", 1500, 2.3, "Constellation nuclear PPA DCA 2x750", "tier_s", "planned", 4),
    ("6324.T", "TR", "moonshots", 1500, 2.3, "Harmonic Drive robotics", "tier_a", "planned", 3),
    ("1347.HK", "TR", "chokepoints", 1000, 1.6, "Hua Hong Semi mature node foundry", "tier_b", "planned", 2),
    # Watchlist conditional — 3 positions
    (
        "6273.T",
        "TR",
        "moonshots",
        1750,
        2.7,
        "SMC robotics actuators (range 1500-2000)",
        "watchlist_conditional",
        "watchlist_conditional",
        None,
    ),
    (
        "8035.T",
        "TR",
        "core_ai",
        1750,
        2.7,
        "Tokyo Electron WFE chokepoint (range 1500-2000)",
        "watchlist_conditional",
        "watchlist_conditional",
        None,
    ),
    (
        "ASM.AS",
        "PEA",
        "core_ai",
        1250,
        1.9,
        "ASM Intl complete Dutch trio (range 1000-1500)",
        "watchlist_conditional",
        "watchlist_conditional",
        None,
    ),
    # Dropped
    ("INFY", "TR", None, 0, 0.0, "Dropped: sell €500 legacy holding", None, "dropped", None),
]


def main():
    with storage.db() as cx:
        # Idempotent: clear prior import
        cx.execute("DELETE FROM portfolio_targets WHERE source_doc=?", (SOURCE_DOC,))

        # Try to link thesis_id where ticker matches an active thesis
        thesis_map = {}
        for r in cx.execute("SELECT id, ticker FROM theses WHERE status='active'"):
            thesis_map[r["ticker"]] = r["id"]

        inserted = 0
        for ticker, account, bucket, target_eur, weight_pct, narrative, priority, status, phase_week in TARGETS:
            tid = thesis_map.get(ticker)
            cx.execute(
                """INSERT INTO portfolio_targets
                   (ticker, account, bucket, target_eur, target_weight_pct, narrative,
                    priority, status, phase_week, source_doc, thesis_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticker,
                    account,
                    bucket,
                    target_eur,
                    weight_pct,
                    narrative,
                    priority,
                    status,
                    phase_week,
                    SOURCE_DOC,
                    tid,
                ),
            )
            inserted += 1

        print(f"Inserted {inserted} portfolio_targets rows from source_doc={SOURCE_DOC}")

        # Summary
        print()
        print("Per account:")
        for r in cx.execute(
            """SELECT account, status, COUNT(*) AS n, SUM(target_eur) AS eur
               FROM portfolio_targets WHERE source_doc=?
               GROUP BY account, status ORDER BY account, status""",
            (SOURCE_DOC,),
        ):
            print(f"  {r['account']:6s} {r['status']:25s} n={r['n']:2d}  eur=€{r['eur']:>7.0f}")

        # Theses linked
        linked = cx.execute(
            "SELECT COUNT(*) AS n FROM portfolio_targets WHERE source_doc=? AND thesis_id IS NOT NULL",
            (SOURCE_DOC,),
        ).fetchone()["n"]
        print(f"\nLinked to existing theses: {linked} targets")


if __name__ == "__main__":
    main()
