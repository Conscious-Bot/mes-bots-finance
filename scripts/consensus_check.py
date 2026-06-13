"""Consensus targets check : compare target_full DB vs consensus yfinance live.

Wire 12/06/2026 (post FMP free tier audit : 19% couverture book → switch
vers yfinance .info qui couvre 100% + gratuit + déjà wired).

Use case PRESAGE :
- #135 refonte niveaux : consensus externe live pour ancrer chaque thèse
- Ferme la dette F3 du scoring méthodologique (asymétrie pas fiable car
  targets datent du 16/05)
- Identifier où Olivier est variant assumé vs out-of-consensus sans le savoir

Output :
- Tableau ticker × (target_olv / consensus_mean / high / low / N / Δ%)
- Top 10 écarts |Δ%| pour prioriser les revues
- Flag :
  * "BULL +X%" : Olivier plus optimiste que la rue (variant assumé ou risk)
  * "BEAR -X%" : Olivier plus prudent que la rue (fade-consensus ou caution)
  * Aligné si |Δ| < 5%, écart si > 20%
"""
from __future__ import annotations

from shared import prices, storage as s


def main():
    with s.db() as cx:
        rows = cx.execute(
            "SELECT t.id, t.ticker, t.conviction, t.direction, "
            "       t.target_full, t.target_full_currency "
            "FROM theses t "
            "WHERE t.status='active' AND t.target_full IS NOT NULL "
            "ORDER BY t.conviction DESC, t.ticker"
        ).fetchall()

    print(f"{len(rows)} theses actives avec target_full")
    print()
    print(f"{'TICKER':>11} {'conv':>4} {'dir':>4} {'tgt_olv':>10} | "
          f"{'consensus':>10} {'high':>10} {'low':>10} {'N':>3} {'ccy':>4} | "
          f"{'Δ%':>7} {'flag':>20}")
    print("-" * 115)

    n_checked = 0
    n_covered = 0
    deltas: list[tuple[str, float, int, str]] = []

    for r in rows:
        _tid, tk, conv, direction, tgt_olv, _tgt_ccy = r
        cons = prices.get_analyst_consensus(tk)
        n_checked += 1
        if not cons:
            print(f"  {tk:>9} c{conv} {direction or '?':>4} {tgt_olv:>10.2f} | "
                  f"{'?':>10} {'?':>10} {'?':>10} {'-':>3} {'?':>4} | {'-':>7} not_covered")
            continue
        n_covered += 1

        # Delta : (target_olv / consensus_mean - 1) * 100
        # Assume same currency (yfinance returns native du listing,
        # target_full Olivier en native aussi cf currency_native_invariant)
        delta_pct = (tgt_olv / cons["target_mean"] - 1) * 100

        flag = ""
        if abs(delta_pct) < 5:
            flag = "✓ aligné"
        elif delta_pct > 20:
            flag = "⚠ BULL >20%"
        elif delta_pct < -20:
            flag = "⚠ BEAR <-20%"
        elif delta_pct > 0:
            flag = "+bull"
        else:
            flag = "-bear"

        deltas.append((tk, delta_pct, conv, direction or "?"))

        print(f"  {tk:>9} c{conv} {direction or '?':>4} {tgt_olv:>10.2f} | "
              f"{cons['target_mean']:>10.2f} {cons['target_high'] or 0:>10.2f} "
              f"{cons['target_low'] or 0:>10.2f} {cons['n_analysts']:>3} "
              f"{cons['currency']:>4} | {delta_pct:>+6.1f}% {flag:>20}")

    print()
    print(f"Coverage : {n_covered}/{n_checked} ({n_covered/n_checked*100:.0f}%)")

    if not deltas:
        return

    print()
    print("=== TOP 10 ÉCARTS |Δ%| trié descending (priorité revue #135) ===")
    sorted_d = sorted(deltas, key=lambda x: -abs(x[1]))
    for tk, dpct, conv, dir_ in sorted_d[:10]:
        sign = "BULL" if dpct > 0 else "BEAR"
        comment = ""
        if dpct > 50:
            comment = "  -> variant explicite OU target stale"
        elif dpct > 20:
            comment = "  -> à justifier ou re-poser"
        elif dpct < -20:
            comment = "  -> tu es plus prudent que la rue"
        print(f"  {tk:>11} c{conv} {dir_:>4} : {dpct:>+6.1f}% ({sign}){comment}")


if __name__ == "__main__":
    main()
