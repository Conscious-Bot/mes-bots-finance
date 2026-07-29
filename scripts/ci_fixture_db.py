"""DB de SYNTHÈSE pour la CI — rend la classe live_data testable hors du Mac.

Chantier #11 (04/07/2026) : la classe live_data (~17 fichiers) ne tournait JAMAIS
en CI ("rouge depuis toujours" → skippée 06/06 au lieu d'être fixée). Ce script
bootstrappe le schéma réel (alembic head) + seed un golden book minimal
synthétique : les tests state-agnostiques tournent en CI contre cette fixture ;
ceux qui assertent le VRAI book restent marqués live_book (local-only).

Usage (CI et dry-run local) :
    export PRESAGE_DB_PATH=/tmp/presage_fixture/bot.db
    export PRESAGE_STATE_PATH=/tmp/presage_fixture/bot_state.json
    python scripts/ci_fixture_db.py
    pytest tests/ -m "live_data and not live_book and not slow"

Garde-fou : REFUSE de tourner si la cible existe déjà (jamais d'écrasement
silencieux — supprime-la d'abord) ou si PRESAGE_DB_PATH n'est pas set alors que
la DB prod par défaut existe (protège le Mac ; en CI data/bot.db n'existe pas).
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _iso(days_ago: int = 0) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()


def _day(days_ago: int = 0) -> str:
    return (datetime.now(UTC).date() - timedelta(days=days_ago)).isoformat()


def main() -> Path:
    target_env = os.environ.get("PRESAGE_DB_PATH")
    default_db = ROOT / "data" / "bot.db"
    if not target_env and default_db.exists():
        raise SystemExit(
            "REFUS : PRESAGE_DB_PATH non défini et data/bot.db EXISTE (machine de "
            "prod ?). La fixture ne s'écrit jamais par-dessus la vraie DB."
        )
    target = Path(target_env) if target_env else default_db
    if target.exists():
        raise SystemExit(
            f"REFUS : {target} existe déjà — pas d'écrasement silencieux. "
            "Supprime la cible puis relance."
        )
    target.parent.mkdir(parents=True, exist_ok=True)

    # Schéma réel : alembic upgrade head (même code que prod).
    from shared.storage import bootstrap_schema

    bootstrap_schema(db_path=str(target))

    # Seed — via la passerelle storage quand un helper existe (elle pointe sur la
    # fixture grâce à PRESAGE_DB_PATH), sinon INSERT direct schéma-conforme.
    assert os.environ.get("PRESAGE_DB_PATH") or not default_db.exists()
    from shared import storage

    assert str(storage.DB_PATH) == str(target), (
        f"storage.DB_PATH={storage.DB_PATH} ne pointe pas sur la fixture {target} — "
        "PRESAGE_DB_PATH doit être exporté AVANT l'import de shared.storage."
    )

    with storage.db() as cx:
        # Source
        cx.execute(
            "INSERT INTO sources(name, type, credibility, family) "
            "VALUES('ci_fixture', 'rss', 0.7, 'secondary_curated')"
        )
        # 2 thèses actives (natives USD, invariants 0016 : entry/stop/target + triggers)
        cx.execute(
            "INSERT INTO theses(ticker, opened_at, conviction, direction, horizon, "
            "key_drivers, invalidation_triggers, entry_price, target_price, stop_price, "
            "status, position_type, conviction_at_entry, target_partial, target_full) "
            "VALUES('TSM', ?, 5, 'long', '12m', 'monopole fonderie avancée', "
            "'perte du lead N2 OU capex hyperscaler -20% yoy', 180.0, 260.0, 150.0, "
            "'active', 'structural', 5, 230.0, 260.0)",
            (_iso(60),),
        )
        cx.execute(
            "INSERT INTO theses(ticker, opened_at, conviction, direction, horizon, "
            "key_drivers, invalidation_triggers, entry_price, target_price, stop_price, "
            "status, position_type, conviction_at_entry, target_partial, target_full) "
            "VALUES('CCJ', ?, 3, 'long', '18m', 'déficit structurel uranium', "
            "'prix spot < 60 USD 3 mois OU restarts Kazatomprom', 50.0, 75.0, 40.0, "
            "'active', 'priced', 3, 65.0, 75.0)",
            (_iso(45),),
        )
        # Ledger : positions est une VUE dérivée de positions_meta (spine) JOIN
        # transactions (qty) JOIN price/fx_history (mark) — migrations 0046/0048.
        for tk, qty, px, d in (("TSM", 10, 180.0, 60), ("CCJ", 20, 50.0, 45)):
            cx.execute(
                "INSERT INTO positions_meta(ticker, status, account, wrapper) "
                "VALUES(?, 'open', 'ci', 'CTO')",
                (tk,),
            )
            cx.execute(
                "INSERT INTO transactions(ticker, side, qty, price_native, fees_native, "
                "currency, fx_at_trade, fx_is_derived, trade_date, source, is_anchor) "
                "VALUES(?, 'BUY', ?, ?, 1.0, 'USD', 0.92, 0, ?, 'ci_fixture', 1)",
                (tk, qty, px, _day(d)),
            )
        # Historique prix + FX (fraîcheur relative, jamais hardcodée)
        for d in range(5):
            for tk, px in (("TSM", 185.0 + d), ("CCJ", 52.0 + d * 0.2)):
                cx.execute(
                    "INSERT INTO price_history(ticker, price_native, currency, asof, source) "
                    "VALUES(?, ?, 'USD', ?, 'ci_fixture')",
                    (tk, px, _iso(d)),
                )
            cx.execute(
                "INSERT INTO fx_history(base, quote, rate, asof, source) "
                "VALUES('USD', 'EUR', 0.92, ?, 'ci_fixture')",
                (_iso(d),),
            )
        # Prédictions : 3 résolues (Brier) + 2 ouvertes
        for i, (brier, outcome) in enumerate([(0.04, "correct"), (0.36, "incorrect"), (0.09, "correct")]):
            cx.execute(
                "INSERT INTO predictions(ticker, direction, horizon_days, baseline_price, "
                "baseline_date, target_date, resolved_at, final_price, outcome, "
                "probability_at_creation, brier_score, methodology_version, claim_type, origin, return_pct) "
                "VALUES('TSM', 'up', 30, 180.0, ?, ?, ?, 190.0, ?, 0.8, ?, 'v2', "
                "'price', 'manual', 0.0556)",
                (_day(60 + i), _day(30 + i), _iso(30 + i), outcome, brier),
            )
        for i in range(2):
            cx.execute(
                "INSERT INTO predictions(ticker, direction, horizon_days, baseline_price, "
                "baseline_date, target_date, probability_at_creation, methodology_version, "
                "claim_type, origin) "
                "VALUES('CCJ', 'up', 60, 50.0, ?, ?, 0.7, 'v2', 'price', "
                "'manual')",
                (_day(10 + i), _day(-50 + i)),
            )
        # Grappe kill_switch : 3 snapshots complets
        for d in range(3):
            cx.execute(
                "INSERT INTO cluster_value_snapshots(snapshot_date, value_eur) VALUES(?, ?)",
                (_day(d), 1656.0 - d * 10),
            )
        cx.commit()

    # portfolio_snapshots via la passerelle (crée la table + respecte le format)
    for d in (2, 1, 0):
        storage.upsert_portfolio_snapshot(
            {
                "snapshot_date": _day(d),
                "captured_at": _iso(d),
                "total_value_eur": 2600.0 - d * 20,
                "total_cost_eur": 2576.0,
                "pnl_eur": 24.0 - d * 20,
                "pnl_pct": round((24.0 - d * 20) / 2576.0 * 100, 2),
                "n_positions": 2,
                "n_priced": 2,
                "hwm_value_eur": 2600.0,
                "drawdown_pct": round((2600.0 - d * 20) / 2600.0 * 100 - 100, 2),
                "detail_json": {},
            }
        )

    # Tables lazily-créées hors migrations : les instancier VIDES pour que les
    # tests à skip-si-vide skippent proprement au lieu de crasher sur table absente.
    from intelligence import debt_monitor

    debt_monitor._ensure_tables()

    # bot_state minimal (PRESAGE_STATE_PATH conseillé en CI)
    storage.save_state({"bootstrapped": _iso(0), "llm_status": "healthy"})

    # Diagnostic schéma (29/07/2026) : CI rouge / local vert sur les MÊMES
    # migrations 0040→0065 — ce dump imprime la vérité terrain du runner
    # (version sqlite + colonnes réelles) pour diff avec le Mac.
    import sqlite3 as _sq
    _dcx = _sq.connect(target)
    print(f"DIAG sqlite_version={_sq.sqlite_version} module={_sq.version if hasattr(_sq, 'version') else '?'}")
    _head = _dcx.execute("SELECT version_num FROM alembic_version").fetchone()
    print(f"DIAG alembic_head={_head[0] if _head else '?'}")
    for _t in ("predictions", "theses", "positions"):
        try:
            _cols = [c[1] for c in _dcx.execute(f"PRAGMA table_info({_t})").fetchall()]
            print(f"DIAG {_t} ({len(_cols)} cols): {','.join(_cols)}")
        except Exception as _e:
            print(f"DIAG {_t}: ERROR {_e}")
    _n_tables = _dcx.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    _tn = _dcx.execute("SELECT name FROM sqlite_master WHERE name='ticker_names'").fetchone()
    print(f"DIAG tables={_n_tables} ticker_names={'present' if _tn else 'ABSENT'}")
    _dcx.close()

    print(f"fixture OK -> {target}")
    return target


if __name__ == "__main__":
    main()
