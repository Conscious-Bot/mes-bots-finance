"""Aggregate bias ledger : etat actuel de TOUS les biais documentes.

Question repondue : tes biais comportementaux te coutent-ils ? Lesquels ?
Pipeline :
  1. Pour chaque biais dans _BIAS_PREDICATES (vend_winners_trop_tot,
     pas_vendre_crypto_top, etc.), run measure_bias() qui retourne
     N decisions / N resolved / verdict distribution / EUR cumulatif
  2. Forward visibility : combien d'ancres pending vont mature aux horizons
     30/60/90 j ? Quand exactement ?
  3. Top harmful cases (filtres TEST_*) pour qualitative review
  4. Verdict honnete : significance wide / tentative / robust

Cf doctrine projet : la mesure boucle-de-soi V0 = mecanisation du biais #1
(lock_in / vend_winners_trop_tot). Calendrier TODO : 29/06 D+30 doit
produire les premiers chiffres signes.

Cohort actuelle (05/06) : ledger pollue par 200+ ancres TEST_*. Le filter
ticker NOT LIKE 'TEST_%' a ete ajoute source-direct dans
intelligence/self_loop.measure_bias (commit meme jour).

Usage :
  python -m scripts.bias_ledger
  python -m scripts.bias_ledger --horizon 60   # mature window
  python -m scripts.bias_ledger --bias vend_winners_trop_tot
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from intelligence import self_loop
from shared import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("bias_ledger")


def fetch_pending_visibility(conn: sqlite3.Connection, horizon_days: int) -> dict:
    """Pour le horizon donne : combien d'ancres reelles (filtre TEST) sont
    en attente de resolution ? Quand vont-elles mature ?
    """
    # Ancres reelles non encore resolues a cet horizon
    rows = conn.execute(
        """
        SELECT dcf.id, dcf.ticker, dcf.decision_type, dcf.decided_at,
               julianday(date(dcf.decided_at, ?)) - julianday('now') AS days_until
        FROM decision_counterfactual dcf
        LEFT JOIN decisions d ON d.id = dcf.decision_id
        WHERE dcf.ticker NOT LIKE 'TEST_%'
          AND dcf.ticker NOT LIKE 'test%'
          AND (d.reasoning IS NULL OR d.reasoning NOT LIKE '[VOIDED %')
          AND NOT EXISTS (
            SELECT 1 FROM counterfactual_resolution cfr
            WHERE cfr.decision_counterfactual_id = dcf.id
              AND cfr.horizon_days = ?
          )
        ORDER BY days_until
        """,
        (f"+{horizon_days} days", horizon_days),
    ).fetchall()
    return {
        "n_total": len(rows),
        "next_to_mature": rows[:5],  # 5 plus proches
        "already_mature": [r for r in rows if r[4] is not None and r[4] <= 0],
    }


def fetch_top_harmful(conn: sqlite3.Connection, horizon_days: int, limit: int = 5) -> list:
    """Top N harmful cases reels (filtre TEST + VOIDED)."""
    rows = conn.execute(
        """
        SELECT dcf.ticker, dcf.decision_type, dcf.decided_at,
               ROUND(cfr.delta_eur, 2) AS delta_eur,
               ROUND(cfr.delta_pct, 1) AS delta_pct,
               COALESCE(dcf.bias_hypothesis_json, '[]') AS biases
        FROM counterfactual_resolution cfr
        JOIN decision_counterfactual dcf ON dcf.id = cfr.decision_counterfactual_id
        LEFT JOIN decisions d ON d.id = dcf.decision_id
        WHERE cfr.horizon_days = ?
          AND dcf.ticker NOT LIKE 'TEST_%'
          AND dcf.ticker NOT LIKE 'test%'
          AND (d.reasoning IS NULL OR d.reasoning NOT LIKE '[VOIDED %')
        ORDER BY cfr.delta_eur ASC
        LIMIT ?
        """,
        (horizon_days, limit),
    ).fetchall()
    return rows


def print_bias_summary(m: dict) -> None:
    """Pretty-print une mesure de biais."""
    bias = m.get("bias_name", "?")
    print(f"━━ {bias} ━━")
    print(f"  Description : {m.get('description', '')}")
    print(f"  Decisions correspondant au predicat : {m.get('n_decisions', 0)}")
    n_res = m.get("n_with_resolution", 0)
    print(f"  Resolved a J+{m.get('horizon_days', '?')} : {n_res}")

    if n_res == 0:
        print("  Verdict : pas encore mesurable (0 resolved)")
        return

    avg = m.get("avg_delta_pct")
    med = m.get("median_delta_pct")
    cumul = m.get("cumulative_delta_eur", 0.0)
    sig = m.get("statistical_significance", "wide")
    vd = m.get("verdict_distribution", {})

    print(f"  Verdict distribution : harmful={vd.get('harmful', 0)} "
          f"neutral={vd.get('neutral', 0)} beneficial={vd.get('beneficial', 0)}")
    print(f"  Delta avg : {avg:+.2f}% (median {med:+.2f}%)")
    cumul_sign = "-" if cumul < 0 else "+"
    print(f"  Cumulative delta : {cumul_sign}{abs(cumul):.2f} EUR "
          f"({'opportunite ratee' if cumul < 0 else 'sauve par la decision'})")
    print(f"  Significance : {sig} (n={n_res})")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--horizon", type=int, default=30, choices=[30, 60, 90],
                        help="Horizon resolution (default 30).")
    parser.add_argument("--bias", type=str, default=None,
                        help="Restrict to one bias (default: tous).")
    args = parser.parse_args()

    biases_to_check = (
        [args.bias] if args.bias
        else list(self_loop._BIAS_PREDICATES.keys())
    )

    print("\n" + "=" * 80)
    print("BIAS LEDGER — etat actuel de la boucle-de-soi V0")
    print("=" * 80)
    print(f"Horizon : J+{args.horizon}")
    print("Note : ancres TEST_* exclues (data poisoning fix source-direct 05/06).")
    print()

    for bias_name in biases_to_check:
        if bias_name not in self_loop._BIAS_PREDICATES:
            print(f"!! Biais inconnu : {bias_name}\n")
            continue
        m = self_loop.measure_bias(bias_name, horizon_days=args.horizon)
        if "error" in m:
            print(f"!! Erreur {bias_name} : {m['error']}\n")
            continue
        print_bias_summary(m)

    # Forward visibility
    conn = sqlite3.connect(storage.DB_PATH)
    try:
        pending = fetch_pending_visibility(conn, args.horizon)
        print("=" * 80)
        print(f"PENDING ANCRES (vraies, hors TEST) -- mature horizon J+{args.horizon}")
        print(f"  Total : {pending['n_total']}")
        print(f"  Deja mature (jours_until <= 0) : {len(pending['already_mature'])}")
        if pending["next_to_mature"]:
            print("  5 prochaines a mature :")
            for r in pending["next_to_mature"]:
                days = r[4] or 0
                if days < 0:
                    when = f"MATURE (deja {-int(days)}j passes)"
                else:
                    when = f"+{int(days)}j"
                print(f"    {r[1]:<10} {r[2]:<12} decided {r[3][:10]} -> {when}")
        print()

        # Top harmful (real, filtered)
        top_harm = fetch_top_harmful(conn, args.horizon)
        if top_harm:
            print("=" * 80)
            print(f"TOP 5 HARMFUL CASES REELS a J+{args.horizon} :")
            for r in top_harm:
                ticker, dtype, decided, delta_eur, delta_pct, biases = r
                print(f"  {ticker:<10} {dtype:<12} {decided[:10]} "
                      f"delta={delta_eur:+.2f}EUR ({delta_pct:+.1f}%)  biases={biases}")
            print()
    finally:
        conn.close()

    print("=" * 80)
    print("Lecture :")
    print("- Significance 'wide' = N<10, ne conclus rien")
    print("- Significance 'tentative' = N=10-30, observation directionnelle")
    print("- Significance 'robust' = N>30, conclusion ferme defendable")
    print("- Cumulative delta negatif = biais te coute (oppportunite ratee si tu")
    print("  avais hold). Positif = ta decision a battu le contrefactuel.")
    print("=" * 80)


if __name__ == "__main__":
    main()
