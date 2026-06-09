"""Gate byte-identité VIEW positions (dérivée de transactions) vs table positions actuelle.

Cf SPEC_LEDGER.md §4 (Cure #4 — gate byte-identité avant swap) + §5 (étape GATE
juste avant 0048).

**PHILOSOPHIE** : ce script est un **garde-régression au moment du swap 0048**,
PAS une preuve de propreté supplémentaire. La propreté des 21 propres est
portée par la partition à 3 signaux indépendants (cf scripts/anchor_clean_positions.py
header). Le gate est tautologique sur les 21 (l'anchor reproduit la table par
construction).

**Vrai test du gate** : c'est au moment du swap, quand les 5 seront back-fillées
avec relevés TR autoritatifs (#121). Le gate confirmera alors :
  (a) les 21 propres n'ont PAS dérivé entre-temps (qty/PRU calc-from-transactions
      reste byte-identique à positions.qty/avg_cost_eur)
  (b) les 5 stale montrent des valeurs réconciliées SAINES (différentes de
      positions.* qui est le snapshot stale, mais cohérentes avec relevés TR
      hand-checkable)

Règles d'exit :
  0 = GATE GREEN : 21 propres matchent + 5 stale diffèrent (back-fill effectué) → swap autorisé
  1 = ABORT : 1+ des 21 propres dérive (corruption inattendue)
  2 = ABORT : 5 stale matchent encore (= #121 pas fait, swap perdrait les 5 réconciliations)
  3 = ABORT : transactions vides ou état impossible

État actuel (09/06 matin, avant relevés TR) : exit 2 attendu — les 5 sont sans
trade, donc leurs valeurs VUE seraient NULL/0 = différentes mais pas "réconciliées",
juste "vides". Le script le voit et bloque correctement.

Usage : python3 scripts/check_ledger_view_equivalence.py
"""
from __future__ import annotations

import sys

from shared import storage

STALE_TICKERS = {"000660.KS", "ALAB", "MU", "CCJ", "6920.T"}

# Tolérances (cf SPEC_LEDGER §4)
TOL_QTY = 1e-6           # arrondi flottant
TOL_PRU_REL = 1e-6       # PRU pondéré, normalement exact via astuce fx (~1e-16)
TOL_RPNL_EUR = 0.01      # realized_pnl en EUR


def compute_view_values(cx) -> dict[str, dict]:
    """Calcule la VUE positions équivalente depuis transactions (SPEC §2.2)."""
    rows = cx.execute("""
        SELECT b.ticker,
               b.sum_qty_buy,
               b.pru_native,
               b.pru_eur,
               COALESCE(b.sum_qty_buy, 0) - COALESCE(s.sum_qty_sell, 0) AS qty,
               COALESCE(s.realized_pnl_eur, 0) AS realized_pnl
        FROM (
            SELECT ticker,
                   SUM(qty) AS sum_qty_buy,
                   SUM(qty * price_native + fees_native) / SUM(qty) AS pru_native,
                   SUM(qty * price_native * fx_at_trade + fees_native * fx_at_trade) / SUM(qty) AS pru_eur
            FROM transactions WHERE side='BUY' GROUP BY ticker
        ) b
        LEFT JOIN (
            SELECT s.ticker,
                   SUM(s.qty) AS sum_qty_sell,
                   SUM(
                     s.qty * s.price_native * s.fx_at_trade
                   - s.fees_native * s.fx_at_trade
                   - s.qty * (
                       SELECT SUM(b.qty * b.price_native * b.fx_at_trade + b.fees_native * b.fx_at_trade)
                            / SUM(b.qty)
                       FROM transactions b
                       WHERE b.ticker = s.ticker AND b.side = 'BUY' AND b.trade_date < s.trade_date
                     )
                   ) AS realized_pnl_eur
            FROM transactions s WHERE s.side='SELL' GROUP BY s.ticker
        ) s ON s.ticker = b.ticker
    """).fetchall()
    return {r[0]: {"qty": r[4], "pru_native": r[2], "pru_eur": r[3], "realized_pnl": r[5]} for r in rows}


def compute_table_values(cx) -> dict[str, dict]:
    """Lit positions actuelle (snapshot, à comparer à la VUE)."""
    rows = cx.execute("""
        SELECT ticker, qty, avg_cost_native, avg_cost_eur, realized_pnl
        FROM positions WHERE status='open' AND qty > 0
    """).fetchall()
    return {r[0]: {"qty": r[1], "pru_native": r[2], "pru_eur": r[3], "realized_pnl": r[4] or 0} for r in rows}


def diff_position(view: dict, table: dict) -> dict:
    """Δ par champ. None si une des deux côtés manque."""
    d = {}
    for field in ("qty", "pru_native", "pru_eur", "realized_pnl"):
        v = view.get(field) if view else None
        t = table.get(field) if table else None
        if v is None or t is None:
            d[field] = None
            continue
        # Δ absolu pour qty et rPnL ; Δ relatif pour PRU
        if field in ("qty", "realized_pnl"):
            d[field] = v - t
        else:
            d[field] = abs(v - t) / t if t else abs(v - t)
    return d


def is_match(d: dict) -> bool:
    """Match si Δ < tolérance sur chaque champ non-None."""
    if d["qty"] is None or d["pru_native"] is None:
        return False
    return (
        abs(d["qty"]) < TOL_QTY
        and d["pru_native"] < TOL_PRU_REL
        and d["pru_eur"] < TOL_PRU_REL
        and abs(d["realized_pnl"]) < TOL_RPNL_EUR
    )


def main() -> int:
    with storage.db() as cx:
        cx.row_factory = None

        # Pré-flight : transactions doit avoir des rows
        n_trades = cx.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        if n_trades == 0:
            print("ABORT : transactions vide — run scripts/anchor_clean_positions.py d'abord.")
            return 3

        view_values = compute_view_values(cx)
        table_values = compute_table_values(cx)
        all_tickers = sorted(set(view_values) | set(table_values))

        # Verdict par ticker
        verdicts = {"propre_match": [], "propre_drift": [], "stale_reconciled": [],
                    "stale_still_missing": [], "stale_unexpected_match": []}
        details = []

        print(f"{'TICKER':12s} {'class':>8s} {'Δqty':>10s} {'Δpru_n%':>10s} {'Δpru_e%':>10s} {'ΔrPnL_eur':>11s}  verdict")
        print("-" * 100)
        for tk in all_tickers:
            v = view_values.get(tk)
            t = table_values.get(tk)
            is_stale = tk in STALE_TICKERS
            d = diff_position(v, t)
            details.append((tk, v, t, d))

            if is_stale:
                if v is None:
                    verdicts["stale_still_missing"].append(tk)
                    verdict = "STALE_NO_BACKFILL"
                elif is_match(d):
                    verdicts["stale_unexpected_match"].append(tk)
                    verdict = "STALE_UNEXPECTED_MATCH"
                else:
                    verdicts["stale_reconciled"].append(tk)
                    verdict = "STALE_RECONCILED"
            else:
                if v is None:
                    verdicts["propre_drift"].append(tk)
                    verdict = "PROPRE_NO_TRADE"
                elif is_match(d):
                    verdicts["propre_match"].append(tk)
                    verdict = "PROPRE_MATCH"
                else:
                    verdicts["propre_drift"].append(tk)
                    verdict = "PROPRE_DRIFT"

            def _f(x, fmt):
                return fmt.format(x) if x is not None else "n/a"
            klass = "stale" if is_stale else "propre"
            print(f"{tk:12s} {klass:>8s} "
                  f"{_f(d['qty'], '{:+10.6f}'):>10s} "
                  f"{_f(d['pru_native'], '{:9.1e}'):>10s} "
                  f"{_f(d['pru_eur'], '{:9.1e}'):>10s} "
                  f"{_f(d['realized_pnl'], '{:+11.2f}'):>11s}  {verdict}")

        # Résumé
        print()
        print("=== Résumé ===")
        print(f"  PROPRES (21 attendu)         : match={len(verdicts['propre_match'])}, drift={len(verdicts['propre_drift'])}")
        print(f"  STALE   (5 attendu)          : reconciled={len(verdicts['stale_reconciled'])}, "
              f"still_missing={len(verdicts['stale_still_missing'])}, "
              f"unexpected_match={len(verdicts['stale_unexpected_match'])}")
        print()

        # Décision finale
        if verdicts["propre_drift"]:
            print(f"ABORT (exit 1) : {len(verdicts['propre_drift'])} propre(s) en drift — "
                  f"corruption inattendue : {verdicts['propre_drift']}")
            print("  Investigation : (a) anchor manquant ? (b) trade postérieur cassant la VUE ? "
                  "(c) table positions modifiée hors ledger ?")
            return 1

        if verdicts["stale_still_missing"]:
            print(f"ABORT (exit 2) : {len(verdicts['stale_still_missing'])} stale sans back-fill — "
                  f"swap perdrait ces réconciliations : {verdicts['stale_still_missing']}")
            print("  Action : back-fill #121 avec relevés TR autoritatifs avant de relancer le gate.")
            return 2

        if verdicts["stale_unexpected_match"]:
            print(f"ABORT (exit 1) : {len(verdicts['stale_unexpected_match'])} stale matche pourtant la table "
                  f"snapshot stale — back-fill probablement faux : {verdicts['stale_unexpected_match']}")
            print("  Investigation : les valeurs réconciliées coïncident-elles avec les valeurs stale "
                  "par hasard ? Ou le back-fill a-t-il reproduit le stale au lieu de le corriger ?")
            return 1

        # Tout vert
        if len(verdicts["propre_match"]) == 21 and len(verdicts["stale_reconciled"]) == 5:
            print("GATE GREEN ✓ — 21 propres byte-identique, 5 stale réconciliées avec Δ visible.")
            print()
            print("Hand-check requis avant 0048 : pour chaque stale ci-dessus, vérifier que les Δ"
                  " correspondent aux relevés TR (qty broker, avg_cost broker, realized_pnl broker).")
            print()
            print("Δ stale détails (pour hand-check) :")
            for tk, v, t, d in details:
                if tk in verdicts["stale_reconciled"]:
                    print(f"  {tk}:")
                    print(f"    qty            : VUE={v['qty']:.6f}    TBL={t['qty']:.6f}    Δ={d['qty']:+.6f}")
                    print(f"    pru_native     : VUE={v['pru_native']:.4f}    TBL={t['pru_native']:.4f}")
                    print(f"    pru_eur        : VUE={v['pru_eur']:.4f}    TBL={t['pru_eur']:.4f}")
                    print(f"    realized_pnl   : VUE={v['realized_pnl']:+.2f}  TBL={t['realized_pnl']:+.2f}  Δ={d['realized_pnl']:+.2f}")
            return 0

        # Edge case : compteurs ne matchent pas l'attendu sans drift explicite
        print(f"ABORT (exit 1) : compteurs inattendus : "
              f"propre_match={len(verdicts['propre_match'])} (attendu 21), "
              f"stale_reconciled={len(verdicts['stale_reconciled'])} (attendu 5).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
