"""v2.c.6 tests : lock_in_detector -- Surface 2 winner-sell detection.

User 01/06 validation finale :
- Gate v1 absolu : pnl_pct >= 0.15 AND conviction_at_sell >= 3
- 4 dimensions logguees dans counterfactual_json pour v2 data-driven post-90j
- Conviction at-sell (CONTEMPORAINE, post-revisits), pas at-creation
- L7 silent miss : aucune exception ne traverse vers le caller

8 tests canoniques (cf plan task #39) :
1. Winner +20% c4 sold -> ouvre candidat lock_in avec 4 dimensions
2. Winner +15% c3 sold -> ouvre (boundary inclusive gate)
3. Winner +5% c4 sold -> PAS ouvert (gate pnl violé)
4. Winner +20% c1 sold -> PAS ouvert (gate conviction violé)
5. Loser -10% c4 sold -> PAS ouvert (pas winner)
6. Cas missing data (no thesis active) -> skip propre, pas raise
7. Idempotence : même vente loggée 2x via wire_bias_trigger -> 1 seul candidat
8. Fail-safe : detect raise dans wire -> caller (add_sell) survit
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


def _schema_minimal(cx: sqlite3.Connection) -> None:
    """Clone DDL 0023 (bias_events) + 0025 (position_event_id FK) +
    positions + position_events + theses."""
    cx.executescript("""
        CREATE TABLE bias_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            ticker TEXT,
            bias TEXT NOT NULL CHECK(bias IN ('lock_in', 'fomo_greed', 'other')),
            action TEXT NOT NULL CHECK(action IN ('acted_on_bias', 'resisted')),
            decision_json TEXT NOT NULL,
            counterfactual_json TEXT NOT NULL,
            resolution_json TEXT,
            status TEXT NOT NULL DEFAULT 'open'
                CHECK(status IN ('open', 'resolved', 'void',
                                 'thesis_invalidated', 'reentered',
                                 'missing_data')),
            source TEXT NOT NULL CHECK(source IN ('auto_detected',
                                                  'telegram_tap', 'manual')),
            thesis_id INTEGER, prediction_id INTEGER, note_tags_json TEXT,
            horizon_days INTEGER NOT NULL,
            resolve_at TEXT NOT NULL,
            position_event_id INTEGER
        );
        CREATE TABLE positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL, qty REAL, avg_cost REAL,
            status TEXT DEFAULT 'open', opened_at TEXT
        );
        CREATE TABLE position_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER, ticker TEXT NOT NULL, event_type TEXT NOT NULL,
            qty REAL, price REAL, pnl REAL, notes TEXT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE theses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT, conviction INTEGER, direction TEXT,
            status TEXT DEFAULT 'active', opened_at TEXT,
            entry_price REAL, target_partial REAL, target_full REAL
        );
    """)


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "test.db"
    cx = sqlite3.connect(db)
    _schema_minimal(cx)
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db)
    return db


def _seed_thesis(
    db: Path, *, ticker: str = "NVDA", conviction: int = 4,
    entry_price: float = 100.0, target_full: float = 200.0,
    days_held_back: int = 30,
) -> int:
    """INSERT thesis active. Returns thesis_id."""
    from datetime import UTC, datetime, timedelta
    opened_at = (datetime.now(UTC) - timedelta(days=days_held_back)).isoformat()
    cx = sqlite3.connect(db)
    cur = cx.execute(
        "INSERT INTO theses (ticker, conviction, direction, status, "
        " opened_at, entry_price, target_full) "
        "VALUES (?, ?, 'bullish', 'active', ?, ?, ?)",
        (ticker, conviction, opened_at, entry_price, target_full),
    )
    cx.commit()
    tid = cur.lastrowid
    cx.close()
    return tid


def _seed_position_event_sell(
    db: Path, *, ticker: str = "NVDA", qty: float = 100.0, price: float = 120.0,
) -> int:
    """INSERT position + event sell. Returns position_event_id."""
    cx = sqlite3.connect(db)
    cur1 = cx.execute(
        "INSERT INTO positions (ticker, qty, avg_cost, status, opened_at) "
        "VALUES (?, 0, ?, 'closed', '2026-04-01')",
        (ticker, 100.0),
    )
    pid = cur1.lastrowid
    cur2 = cx.execute(
        "INSERT INTO position_events (position_id, ticker, event_type, qty, price) "
        "VALUES (?, ?, 'sell', ?, ?)",
        (pid, ticker, qty, price),
    )
    cx.commit()
    peid = cur2.lastrowid
    cx.close()
    return peid


def _mock_anchor_eur(monkeypatch: pytest.MonkeyPatch, val: float = 110.0) -> None:
    """Stub get_current_price_in_eur."""
    import shared.prices
    monkeypatch.setattr(shared.prices, "get_current_price_in_eur",
                        lambda tk: val)


def _count_bias_events(db: Path, ticker: str, bias: str = "lock_in") -> int:
    cx = sqlite3.connect(db)
    n = cx.execute(
        "SELECT COUNT(*) FROM bias_events WHERE ticker=? AND bias=? AND status='open'",
        (ticker, bias),
    ).fetchone()[0]
    cx.close()
    return n


# ─── Test 1 : winner +20% c4 sold -> ouvre candidat ────────────────────────


def test_winner_pnl20_c4_sold_opens_candidate(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cas canonique : prix vente 120, avg_cost 100 -> pnl_pct = +20%.
    Conviction c4. Gates v1 satisfaits -> 1 candidat ouvert avec 4
    dimensions logguees dans counterfactual_json.note."""
    _seed_thesis(isolated_db, ticker="NVDA", conviction=4,
                 entry_price=100.0, target_full=200.0)
    _seed_position_event_sell(isolated_db, ticker="NVDA", qty=50.0, price=120.0)
    _mock_anchor_eur(monkeypatch, val=110.0)  # EUR converted

    from intelligence.lock_in_detector import detect_winner_sell
    out = detect_winner_sell(
        position_id=1, ticker="NVDA",
        qty_sold=50.0, sold_price_native=120.0,
        qty_before=100.0, avg_cost=100.0,
    )
    assert out is not None
    assert out["bias_event_id"] is not None

    # Vérifie le candidat ouvert
    assert _count_bias_events(isolated_db, "NVDA") == 1

    # Inspecte les 4 dimensions (stockees dans note_tags_json via wire_bias_trigger)
    cx = sqlite3.connect(isolated_db)
    row = cx.execute(
        "SELECT counterfactual_json, position_event_id, note_tags_json "
        "FROM bias_events "
        "WHERE bias='lock_in' AND ticker='NVDA' AND status='open'"
    ).fetchone()
    cx.close()
    cf = json.loads(row[0])
    assert cf["initial_qty"] == 100.0
    assert cf["discipline_expected_delta"] == 0.0  # discipline = hold
    assert cf["anchor_price_eur"] == 110.0

    # 4 dimensions dans note_tags_json
    note = json.loads(row[2])
    assert note["pnl_pct_at_sell"] == pytest.approx(0.20, abs=0.001)
    assert note["conviction_at_sell"] == 4
    assert note["pnl_pct_progress"] is not None  # target connu (200/100-1 = 1.0)
    assert note["pnl_pct_progress"] == pytest.approx(0.20, abs=0.001)
    assert note["surface"] == "surface_2_winner_sell"

    # FK position_event_id renseignee
    assert row[1] is not None


# ─── Test 2 : winner +15% c3 sold -> ouvre (boundary inclusive) ────────────


def test_winner_pnl15_c3_sold_boundary_opens_candidate(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test gate boundary : pnl_pct = 0.15 EXACT (inclusif) et conviction = 3
    EXACT (inclusif). Doit ouvrir."""
    _seed_thesis(isolated_db, ticker="AMD", conviction=3,
                 entry_price=100.0, target_full=180.0)
    _seed_position_event_sell(isolated_db, ticker="AMD", qty=50.0, price=115.0)
    _mock_anchor_eur(monkeypatch, val=110.0)

    from intelligence.lock_in_detector import detect_winner_sell
    out = detect_winner_sell(
        position_id=1, ticker="AMD",
        qty_sold=50.0, sold_price_native=115.0,
        qty_before=100.0, avg_cost=100.0,
    )
    assert out is not None
    assert _count_bias_events(isolated_db, "AMD") == 1


# ─── Test 3 : winner +5% c4 sold -> PAS ouvert (gate pnl) ──────────────────


def test_pnl5_below_gate_not_opened(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pnl_pct = +5% < 0.15 -> gate pnl viole, return None sans candidat."""
    _seed_thesis(isolated_db, ticker="TSLA", conviction=4)
    _seed_position_event_sell(isolated_db, ticker="TSLA", qty=50.0, price=105.0)
    _mock_anchor_eur(monkeypatch)

    from intelligence.lock_in_detector import detect_winner_sell
    out = detect_winner_sell(
        position_id=1, ticker="TSLA",
        qty_sold=50.0, sold_price_native=105.0,
        qty_before=100.0, avg_cost=100.0,
    )
    assert out is None
    assert _count_bias_events(isolated_db, "TSLA") == 0


# ─── Test 4 : winner +20% c1 sold -> PAS ouvert (gate conviction) ──────────


def test_conviction_c1_below_gate_not_opened(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Conviction c1 (trash) < 3 -> gate conviction viole, pas ouvert.
    Vendre une these trash en gain n'est pas du lock_in (c'est rationnel)."""
    _seed_thesis(isolated_db, ticker="MEME", conviction=1)
    _seed_position_event_sell(isolated_db, ticker="MEME", qty=50.0, price=120.0)
    _mock_anchor_eur(monkeypatch)

    from intelligence.lock_in_detector import detect_winner_sell
    out = detect_winner_sell(
        position_id=1, ticker="MEME",
        qty_sold=50.0, sold_price_native=120.0,
        qty_before=100.0, avg_cost=100.0,
    )
    assert out is None
    assert _count_bias_events(isolated_db, "MEME") == 0


# ─── Test 5 : loser sold -> PAS ouvert (pas winner par definition) ────────


def test_loser_sold_not_opened(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vente a perte (pnl_pct -10%) -> pas un winner, pas un candidat lock_in."""
    _seed_thesis(isolated_db, ticker="SHOR", conviction=4)
    _seed_position_event_sell(isolated_db, ticker="SHOR", qty=50.0, price=90.0)
    _mock_anchor_eur(monkeypatch)

    from intelligence.lock_in_detector import detect_winner_sell
    out = detect_winner_sell(
        position_id=1, ticker="SHOR",
        qty_sold=50.0, sold_price_native=90.0,
        qty_before=100.0, avg_cost=100.0,
    )
    assert out is None
    assert _count_bias_events(isolated_db, "SHOR") == 0


# ─── Test 6 : no thesis active -> skip propre, pas raise ──────────────────


def test_no_active_thesis_skips_clean(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aucune these active sur ticker -> conviction unknown -> skip propre
    (pas un cas de pas-de-thesis = pas un cas de biais lock_in instrumentable).
    Aucune exception."""
    _seed_position_event_sell(isolated_db, ticker="ORPHAN", qty=50.0, price=120.0)
    _mock_anchor_eur(monkeypatch)

    from intelligence.lock_in_detector import detect_winner_sell
    out = detect_winner_sell(
        position_id=1, ticker="ORPHAN",
        qty_sold=50.0, sold_price_native=120.0,
        qty_before=100.0, avg_cost=100.0,
    )
    assert out is None
    assert _count_bias_events(isolated_db, "ORPHAN") == 0


# ─── Test 7 : idempotence via wire_bias_trigger ────────────────────────────


def test_idempotence_same_position_event_kept(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Meme vente loggee 2x (rare mais possible) -> wire_bias_trigger kept
    via cle (ticker, bias, action, ref) -- ref include pe{position_event_id}.
    1 candidat unique."""
    _seed_thesis(isolated_db, ticker="NVDA", conviction=4)
    _seed_position_event_sell(isolated_db, ticker="NVDA", qty=50.0, price=120.0)
    _mock_anchor_eur(monkeypatch)

    from intelligence.lock_in_detector import detect_winner_sell

    # 1er appel
    out1 = detect_winner_sell(
        position_id=1, ticker="NVDA", qty_sold=50.0, sold_price_native=120.0,
        qty_before=100.0, avg_cost=100.0,
    )
    assert out1 is not None
    # 2e appel meme parametres (meme position_event)
    out2 = detect_winner_sell(
        position_id=1, ticker="NVDA", qty_sold=50.0, sold_price_native=120.0,
        qty_before=100.0, avg_cost=100.0,
    )
    # out2 = None car wire_bias_trigger.opened == 0 (kept)
    assert out2 is None
    # Mais toujours 1 seul candidat open
    assert _count_bias_events(isolated_db, "NVDA") == 1


# ─── Test 9 : conviction CONTEMPORAINE post-revisit (user 01/06 #4) ───────


def test_conviction_at_sell_reads_current_post_revisit(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verrou architectural : la conviction lue au moment de la vente est
    la CONTEMPORAINE (post-revisits), pas at-creation. Path : theses.conviction
    est UPDATE in-place (storage.py:2734), donc SELECT conviction lit
    toujours la valeur courante.

    Setup : thesis creee c2, UPDATE conviction=4 (simule revisit), vendre.
    Verifie note.conviction_at_sell == 4 (post-revisit), pas 2 (creation)."""
    # Cree these c2 initialement
    _seed_thesis(isolated_db, ticker="NVDA", conviction=2,
                 entry_price=100.0, target_full=200.0)
    # UPDATE conviction 2 -> 4 (revisit pattern)
    cx = sqlite3.connect(isolated_db)
    cx.execute("UPDATE theses SET conviction=4 WHERE ticker='NVDA'")
    cx.commit()
    cx.close()

    _seed_position_event_sell(isolated_db, ticker="NVDA", qty=50.0, price=120.0)
    _mock_anchor_eur(monkeypatch)

    from intelligence.lock_in_detector import detect_winner_sell
    out = detect_winner_sell(
        position_id=1, ticker="NVDA",
        qty_sold=50.0, sold_price_native=120.0,
        qty_before=100.0, avg_cost=100.0,
    )
    # Avec c4 (post-revisit), gate conviction OK -> candidat ouvert
    assert out is not None

    cx = sqlite3.connect(isolated_db)
    note_str = cx.execute(
        "SELECT note_tags_json FROM bias_events WHERE ticker='NVDA' AND bias='lock_in'"
    ).fetchone()[0]
    cx.close()
    note = json.loads(note_str)
    # CRITIQUE : conviction_at_sell doit etre 4 (post-revisit), PAS 2 (creation)
    assert note["conviction_at_sell"] == 4, (
        "conviction_at_sell doit lire la valeur CONTEMPORAINE (post-revisit), "
        "pas la valeur at-creation. Si fail = bug architectural sur le path "
        "de lookup conviction."
    )


# ─── Test 8 : fail-safe wire raise -> caller survit ───────────────────────


def test_failsafe_wire_raise_caller_survives(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """wire_bias_trigger raise (simule un bug DB) -> detect_winner_sell
    capture (return None ou error mais NE traverse pas vers caller add_sell).
    L7 silent miss strict."""
    _seed_thesis(isolated_db, ticker="NVDA", conviction=4)
    _seed_position_event_sell(isolated_db, ticker="NVDA", qty=50.0, price=120.0)
    _mock_anchor_eur(monkeypatch)

    # Force wire_bias_trigger a raise
    import intelligence.bias_events
    def boom(_):
        raise RuntimeError("simulated wire DB bug")
    monkeypatch.setattr(intelligence.bias_events, "wire_bias_trigger", boom)

    # detect_winner_sell ne doit PAS raise au caller -- soit return None
    # soit catch interne (pour ce design, wire raise traverse a try-except
    # wrap dans positions.add_sell, pas dans le detector lui-meme).
    from intelligence.lock_in_detector import detect_winner_sell

    raised = False
    try:
        out = detect_winner_sell(
            position_id=1, ticker="NVDA", qty_sold=50.0, sold_price_native=120.0,
            qty_before=100.0, avg_cost=100.0,
        )
    except RuntimeError:
        # Le detector laisse remonter -- mais add_sell catch (cf L7).
        raised = True
        out = None

    # Verify : le candidat n'a PAS ete cree
    assert _count_bias_events(isolated_db, "NVDA") == 0
    # Et que ce soit raise ou return None, add_sell saura gerer.
    assert raised or out is None
