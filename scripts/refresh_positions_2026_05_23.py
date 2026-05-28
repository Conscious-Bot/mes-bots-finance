#!/usr/bin/env python3
"""Reset positions au cout-de-revient EXACT broker-source, 2026-05-23. account TR/PEA.

PEA (Boursorama): qty + PRU exacts -> set_position direct.
TR (Trade Republic): valeur + P&L absolu "depuis l'achat" -> cost = valeur - pnl,
  qty = valeur/prix_live, avg_cost = cost/qty. Cout exact, qty derive du prix live.
Backup-first (cote caller). Re-runnable: set_position UPSERT idempotent.
"""

import sqlite3
import sys

from shared import positions as positions_mod, prices

# PEA (Boursorama): (ticker, qty_exact, pru_exact_eur)
PEA = [
    ("ASML.AS", 3, 820.95),
    ("BESI.AS", 6, 262.71),
    ("SAF.PA", 2, 213.75),  # Safran
    ("SU.PA", 6, 219.49),  # Schneider
    ("STMPA.PA", 42, 22.84),  # STMicro
    ("HO.PA", 7, 81.59),  # Thales
]

# TR (Trade Republic): (ticker, valeur_marche_eur, pnl_absolu_eur)
TR = [
    ("4063.T", 4336.32, -163.68),  # Shin-Etsu
    ("TSM", 3983.27, 1383.93),
    ("SNPS", 3620.27, 131.27),  # Synopsys
    ("7011.T", 2386.13, -113.87),  # Mitsubishi Heavy
    ("KLAC", 2041.56, 41.56),  # KLA
    ("000660.KS", 1971.70, -28.30),  # SK Hynix
    ("6920.T", 1906.54, -93.46),  # Lasertec
    ("ALAB", 1855.35, 527.35),  # Astera Labs
    ("TSLA", 1767.83, 35.59),
    ("AMD", 1657.63, 1053.07),
    ("MU", 1528.70, 465.14),  # Micron
    ("AMZN", 1527.22, 27.22),  # Amazon
    ("ENTG", 1404.10, 12.10),  # Entegris
    ("MP", 1326.13, 76.14),  # MP Materials
    ("AVGO", 1306.76, -51.24),  # Broadcom
    ("COHR", 1113.03, -34.97),  # Coherent
    ("6857.T", 1064.01, 30.00),  # Advantest
    ("TER", 1049.05, 517.74),  # Teradyne
    ("GOOGL", 985.20, 421.97),  # Alphabet
    ("VRT", 866.54, -112.47),  # Vertiv
    ("LNG", 729.83, 4.52),  # Cheniere
    ("CCJ", 722.03, -25.97),  # Cameco
]
CLOSE = ["MRVL"]
DB = "data/bot.db"


def main():
    done = []
    failed = []

    # PEA: qty + PRU exacts (pas besoin de prix live)
    for ticker, qty, pru in PEA:
        note = "refresh_2026_05_23 | account=PEA | pru=" + str(pru) + " | qty=" + str(qty)
        positions_mod.set_position(ticker, float(qty), float(pru), note)
        done.append(("PEA", ticker, round(qty * pru, 2), float(pru), float(qty)))

    # TR: cost = valeur - pnl (exact), qty = valeur/prix_live, avg_cost = cost/qty
    for ticker, value, pnl in TR:
        try:
            price = prices.get_current_price_in_eur(ticker)
        except Exception as exc:
            failed.append((ticker, "price_error: " + str(exc)[:70]))
            continue
        if not price or price <= 0:
            failed.append((ticker, "pas de prix"))
            continue
        cost = value - pnl
        qty = value / price
        avg_cost = cost / qty
        note = "refresh_2026_05_23 | account=TR | eur_value=" + str(value) + " | pnl=" + str(pnl)
        positions_mod.set_position(ticker, qty, avg_cost, note)
        done.append(("TR", ticker, round(cost, 2), round(avg_cost, 4), round(qty, 4)))

    con = sqlite3.connect(DB, timeout=10)
    try:
        pea_tk = [t for t, _, _ in PEA]
        qmarks = ",".join("?" for _ in pea_tk)
        con.execute("UPDATE positions SET account='PEA' WHERE status='open' AND ticker IN (" + qmarks + ")", pea_tk)
        con.execute("UPDATE positions SET account='TR' WHERE status='open' AND ticker NOT IN (" + qmarks + ")", pea_tk)
        for t in CLOSE:
            con.execute(
                "UPDATE positions SET status='closed', "
                "notes=COALESCE(notes,'')||' | closed_refresh_2026_05_23' "
                "WHERE ticker=? AND status='open'",
                (t,),
            )
        con.commit()
    finally:
        con.close()

    cost_total = sum(c for _, _, c, _, _ in done)
    print("[OK] refreshed:", len(done), "| failed:", len(failed), "| closed:", len(CLOSE))
    print("   cout de revient charge =", round(cost_total, 2), "eur (attendu ~42360)")
    for acct, t, c, p, q in done:
        print("   ", acct, t.ljust(10), "cout=" + str(c).rjust(9), "avg_cost=" + str(p).rjust(10), "qty=" + str(q))
    if failed:
        print("[WARN] echecs (re-run safe):")
        for t, r in failed:
            print("   ", t, r)
        sys.exit(0)


if __name__ == "__main__":
    main()
