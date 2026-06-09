"""Anchor BUY synthétique pour les 21 positions propres (back-fill ledger).

Cf SPEC_LEDGER.md §3.1 (anchor astuce fx) + §5 étape 0047b.

Les 21 propres sont déterminées par signal indépendant strict (cf
verify-before-patch 09/06 matin) :
  - 6 PEA : qty Δ = 0 vs broker_positions.yaml (Boursorama screenshot, source externe)
  - 15 TR : 0 flag patch dans notes + 0 realized_pnl + 0 'qty_aligned' note

Les 5 stale (SK Hynix, ALAB, MU, CCJ, 6920.T) SONT EXCLUES par construction
(SPEC §3.2 : n'anchore JAMAIS un stale — coulerait valeur fausse dans
l'immuable irréversible). Elles attendent les relevés TR autoritatifs (#121).

Astuce fx (SPEC §3.1) : fx_at_trade = avg_cost_eur / avg_cost_native
reproduit price_native × fx_at_trade ≡ avg_cost_eur exactement. Garantit
que pru_native ET pru_eur calculés par la VUE matchent la table actuelle
à la tolérance (gate byte-identité §4).

Idempotent :
  - INSERT seulement si aucun trade existe pour ce ticker (donc anchor pas
    déjà posé). Détection : SELECT 1 FROM transactions WHERE ticker = ? LIMIT 1
  - Re-runnable sans risque de double-anchor.

Audit log :
  - source = 'migration_anchor_2026-06-09'
  - is_anchor = 1
  - notes = explicit explanation, traçable par grep
  - broker_trade_id = NULL (anchor synthétique, pas un trade broker réel)

Usage : python3 scripts/anchor_clean_positions.py
"""
from __future__ import annotations

import sys

from shared import storage

# Liste dure des 5 stale — EXCLUSION par construction (SPEC §3.2)
STALE_EXCLUDED = {"000660.KS", "ALAB", "MU", "CCJ", "6920.T"}

# Liste positive 21 propres — vérifiable par grep ; double-check vs DB query au runtime
CLEAN_EXPECTED = {
    # PEA (6) — qty Δ = 0 vs yaml
    "ASML.AS", "BESI.AS", "HO.PA", "SAF.PA", "STMPA.PA", "SU.PA",
    # TR (15) — 0 flag patch + 0 realized_pnl + 0 'qty_aligned' note
    "4063.T", "6857.T", "7011.T", "AMD", "AMZN", "AVGO", "COHR", "ENTG",
    "GOOGL", "KLAC", "LNG", "MP", "SNPS", "TSLA", "TSM",
}


def main() -> int:
    if len(CLEAN_EXPECTED) != 21:
        print(f"ERREUR liste CLEAN_EXPECTED : {len(CLEAN_EXPECTED)} ≠ 21 attendu")
        return 1

    with storage.db() as cx:
        cx.row_factory = None

        # Pré-flight 1 : table transactions existe
        r = cx.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='transactions'"
        ).fetchone()
        if not r:
            print("ERREUR : table transactions absente — appliquer migration 0046 d'abord.")
            return 1

        # Pré-flight 2 : verify que les 21 attendues sont bien dans positions open
        open_tickers = {
            r[0] for r in cx.execute("SELECT ticker FROM positions WHERE status='open' AND qty>0").fetchall()
        }
        missing = CLEAN_EXPECTED - open_tickers
        if missing:
            print(f"ERREUR : {len(missing)} clean attendues absentes de positions open : {missing}")
            return 1
        if STALE_EXCLUDED & CLEAN_EXPECTED:
            print(f"ERREUR : intersection stale/clean : {STALE_EXCLUDED & CLEAN_EXPECTED}")
            return 1

        # Pré-flight 3 : si déjà partiellement anchored, on continue (idempotent)
        already_anchored = {
            r[0] for r in cx.execute(
                "SELECT DISTINCT ticker FROM transactions WHERE source = 'migration_anchor_2026-06-09'"
            ).fetchall()
        }
        if already_anchored:
            print(f"INFO : {len(already_anchored)} ticker(s) déjà anchored : {sorted(already_anchored)}")

        anchored_now = 0
        skipped_existing = 0
        skipped_excluded = 0
        skipped_no_data = 0

        for ticker in sorted(CLEAN_EXPECTED):
            if ticker in STALE_EXCLUDED:
                # Defense in depth — devrait jamais arriver vu le pré-flight 2
                skipped_excluded += 1
                continue

            # Idempotence : si N'IMPORTE QUEL trade existe pour ce ticker, skip
            # (anchor déjà posé OU trade réel déjà ingéré)
            has_trade = cx.execute(
                "SELECT 1 FROM transactions WHERE ticker = ? LIMIT 1", (ticker,)
            ).fetchone()
            if has_trade:
                skipped_existing += 1
                continue

            # Pull les valeurs depuis positions table
            row = cx.execute("""
                SELECT qty, avg_cost_native, avg_cost_eur, avg_cost_currency, opened_at
                FROM positions WHERE ticker = ?
            """, (ticker,)).fetchone()
            if not row:
                skipped_no_data += 1
                print(f"  SKIP {ticker} : no data in positions")
                continue
            qty, avg_native, avg_eur, currency, opened_at = row
            if not (qty and avg_native and avg_eur and currency):
                skipped_no_data += 1
                print(f"  SKIP {ticker} : missing field (qty={qty}, avg_native={avg_native}, "
                      f"avg_eur={avg_eur}, currency={currency})")
                continue

            # Astuce fx (SPEC §3.1) : reproduit pru_native ET pru_eur exactement
            fx_anchor = avg_eur / avg_native

            cx.execute("""
                INSERT INTO transactions (
                    ticker, side, qty, price_native, fees_native,
                    currency, fx_at_trade, fx_is_derived,
                    trade_date, broker_trade_id, source, is_anchor, notes
                ) VALUES (
                    ?, 'BUY', ?, ?, 0,
                    ?, ?, 0,
                    ?, NULL, 'migration_anchor_2026-06-09', 1, ?
                )
            """, (
                ticker, qty, avg_native,
                currency, fx_anchor,
                opened_at or "2026-05-15",
                f"Anchor synthétique migration ledger v0 (SPEC_LEDGER §3.1). "
                f"Reproduit pru_native={avg_native:.6f} {currency} ET "
                f"pru_eur={avg_eur:.6f} EUR via astuce fx={fx_anchor:.10f}. "
                f"Position classée propre par signal indépendant strict "
                f"(qty Δ=0 vs broker.yaml PEA OR 0 flag patch + 0 realized_pnl TR)."
            ))
            anchored_now += 1

        cx.commit()

        # Verify
        total_anchors = cx.execute(
            "SELECT COUNT(*) FROM transactions WHERE is_anchor = 1"
        ).fetchone()[0]
        total_trades = cx.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        print()
        print("=== Résumé ===")
        print(f"  anchored maintenant       : {anchored_now}")
        print(f"  skipped (déjà anchored)   : {skipped_existing}")
        print(f"  skipped (exclus stale)    : {skipped_excluded}")
        print(f"  skipped (données manquantes) : {skipped_no_data}")
        print()
        print(f"  total anchors dans transactions : {total_anchors}")
        print(f"  total trades dans transactions  : {total_trades}")

        # 5 stale doivent rester sans trade pour le moment
        stale_with_trade = cx.execute("""
            SELECT ticker FROM transactions
            WHERE ticker IN (?, ?, ?, ?, ?)
        """, tuple(STALE_EXCLUDED)).fetchall()
        if stale_with_trade:
            print(f"  ⚠ stale avec trades déjà ingérés : {[r[0] for r in stale_with_trade]}")
        else:
            print("  ✓ 5 stale sans trade (KNOWN-GAP honnête en attente relevés TR)")

        # Final assertion : 21 propres + 0 stale = 21 tickers avec at least 1 trade
        unique_anchored = cx.execute(
            "SELECT COUNT(DISTINCT ticker) FROM transactions"
        ).fetchone()[0]
        if unique_anchored == 21:
            print("  ✓ 21/21 propres avec exactement 1 anchor — état attendu post-0047b")
            return 0
        else:
            print(f"  ⚠ {unique_anchored} tickers avec trades — attendu 21")
            return 2


if __name__ == "__main__":
    sys.exit(main())
