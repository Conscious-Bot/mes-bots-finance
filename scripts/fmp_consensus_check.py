"""Test FMP consensus targets vs targets DB Olivier.

Usage : `python3 scripts/fmp_consensus_check.py`

Prerequisite : FMP_API_KEY dans .env (get free key sur
https://site.financialmodelingprep.com/developer/docs).

Compare pour chaque thèse active :
- target_full DB (Olivier) en native currency
- consensus FMP (mean/median/high/low + n_analystes)
- delta % (target Olivier vs consensus mean)

Use case : identifier les positions où Olivier est très éloigné du consensus
=> opportunité ou red flag. Ferme la dette F3 du scoring méthodologique
(asymétrie pas fiable car targets datent du 16/05).
"""
from __future__ import annotations

from shared import fmp, storage as s


def main():
    # Quota
    print(f"FMP quota: {fmp.quota_status()}")
    print()

    with s.db() as cx:
        rows = cx.execute(
            "SELECT t.id, t.ticker, t.conviction, t.target_full, t.target_full_currency, "
            "       t.direction, bl_lp.last_price_native, bl_lp.last_price_currency "
            "FROM theses t "
            "LEFT JOIN positions bl_lp ON bl_lp.ticker = t.ticker AND bl_lp.status='open' "
            "WHERE t.status='active' AND t.target_full IS NOT NULL "
            "ORDER BY t.conviction DESC, t.ticker"
        ).fetchall()

    print(f"{len(rows)} theses actives avec target_full defini")
    print()
    print(f"{'TK':>11} {'conv':>4} {'tgt_olv':>10} {'ccy':>4} | "
          f"{'consensus':>10} {'high':>10} {'low':>10} {'N':>3} | {'Δ%':>6}")
    print("-" * 110)

    n_checked = 0
    n_covered = 0
    deltas = []

    for r in rows:
        tid, tk, conv, tgt_olv, tgt_ccy, direction, cur_native, cur_ccy = r

        cons = fmp.get_price_target_consensus(tk)
        n_checked += 1
        if not cons or cons.target_mean is None:
            print(f"  {tk:>9} c{conv} {tgt_olv:>10.2f} {tgt_ccy or '?':>4} | "
                  f"{'?':>10} {'?':>10} {'?':>10} {'-':>3} | not covered")
            continue
        n_covered += 1

        # Delta % : (target_olivier / consensus_mean - 1) * 100
        # > 0 = Olivier plus optimiste, < 0 = Olivier plus prudent
        # Note : pas de conversion currency ici, on suppose même devise listing FMP
        delta_pct = (tgt_olv / cons.target_mean - 1) * 100
        deltas.append((tk, delta_pct, conv))

        flag = ""
        if abs(delta_pct) > 20:
            flag = " ⚠ écart >20%"
        elif abs(delta_pct) < 5:
            flag = " ✓ aligné"

        print(f"  {tk:>9} c{conv} {tgt_olv:>10.2f} {tgt_ccy or '?':>4} | "
              f"{cons.target_mean:>10.2f} {cons.target_high or 0:>10.2f} "
              f"{cons.target_low or 0:>10.2f} {cons.n_analysts or 0:>3} | "
              f"{delta_pct:>+5.1f}%{flag}")

    print()
    print(f"Covered : {n_covered}/{n_checked} ({n_covered/n_checked*100:.0f}%)")
    print()

    # Tri par |delta| descending = qui est le plus éloigné du consensus
    if deltas:
        print("=== TOP 10 ECARTS vs consensus (|Δ%| trié) ===")
        sorted_d = sorted(deltas, key=lambda x: -abs(x[1]))
        for tk, dpct, conv in sorted_d[:10]:
            sign = "BULL" if dpct > 0 else "BEAR"
            print(f"  {tk:>11} c{conv} : {dpct:>+6.1f}% ({sign} vs consensus)")

    print()
    print(f"FMP quota apres : {fmp.quota_status()}")


if __name__ == "__main__":
    main()
