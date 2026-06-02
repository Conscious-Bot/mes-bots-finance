"""Tests unit pour intelligence/v2_vigilance.py (couverture regression).

Les 3 vigilances V2 (watch_rate, directional_spread, insider_clusters_alive)
sont des fitness functions automatiques sur les patterns du decision log #01.
Ces tests verifient le routing OK/WARN/ALERT/INFO/INSUFFICIENT_DATA selon
la composition des datasets en DB.

Approche : DB SQLite temporaire (monkeypatch storage.DB_PATH grace a la
consolidation iter 9), seed datasets minimaux par scenario, assert sur status.
"""

import sqlite3

import pytest


def _setup_db(tmp_path, monkeypatch):
    """DB temporaire avec schema minimal : sources, signals, predictions,
    insider_buy_clusters_log, insider_snapshots."""
    db_path = tmp_path / "vigilance.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
    CREATE TABLE sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        type TEXT NOT NULL,
        credibility REAL,
        n_signals INTEGER DEFAULT 0
    );
    CREATE TABLE signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER,
        gmail_id TEXT UNIQUE,
        timestamp TEXT NOT NULL,
        title TEXT, content TEXT, summary TEXT,
        score INTEGER, sentiment TEXT, entities TEXT,
        signal_type TEXT, impact_magnitude REAL
    );
    CREATE TABLE predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        signal_id INTEGER,
        ticker TEXT, direction TEXT, horizon_days INTEGER,
        baseline_price REAL, baseline_date TEXT, target_date TEXT,
        probability_at_creation REAL,
        created_at TEXT, methodology_version TEXT
    );
    CREATE TABLE insider_buy_clusters_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT, detected_at TEXT, window_days INTEGER,
        distinct_buyers INTEGER, total_buy_m REAL, cluster_strength TEXT
    );
    CREATE TABLE insider_snapshots (
        ticker TEXT, snapshot_date TEXT,
        net_m REAL, n_buys INTEGER, n_sells INTEGER,
        total_buys_m REAL, total_sells_m REAL
    );
    CREATE TABLE theses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT, conviction INTEGER, direction TEXT,
        status TEXT DEFAULT 'active', opened_at TEXT
    );
    """)
    # Source dédiée V2 (utilisée par les 3 vigilances pour identifier les signals V2)
    conn.execute(
        "INSERT INTO sources (name, type, credibility) VALUES (?, ?, ?)",
        ("SEC EDGAR 8-K", "sec_filing", 0.85),
    )
    conn.execute(
        "INSERT INTO sources (name, type, credibility) VALUES (?, ?, ?)",
        ("SEC EDGAR Insider Cluster", "sec_filing", 0.85),
    )
    conn.commit()
    conn.close()

    from shared import storage
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    return db_path


def _seed_v2_signal_with_pred(cx, source_name="SEC EDGAR 8-K", days_ago=5,
                              direction="bullish", prob=0.72, gmail_id="test1"):
    """Helper : insere 1 signal V2 + 1 prediction associee."""
    src = cx.execute("SELECT id FROM sources WHERE name=?", (source_name,)).fetchone()
    cur = cx.execute(
        "INSERT INTO signals (source_id, gmail_id, timestamp, title) VALUES (?, ?, datetime('now', ?), ?)",
        (src["id"], gmail_id, f"-{days_ago} days", "test signal"),
    )
    sig_id = cur.lastrowid
    cx.execute(
        "INSERT INTO predictions (signal_id, ticker, direction, probability_at_creation, target_date) "
        "VALUES (?, ?, ?, ?, date('now', '+30 days'))",
        (sig_id, "TEST", direction, prob),
    )
    return sig_id


def _seed_v2_signal_watch_only(cx, source_name="SEC EDGAR 8-K", days_ago=5, gmail_id="watch1"):
    """Helper : insere 1 signal V2 SANS prediction (= V2 a dit watch)."""
    src = cx.execute("SELECT id FROM sources WHERE name=?", (source_name,)).fetchone()
    cur = cx.execute(
        "INSERT INTO signals (source_id, gmail_id, timestamp, title) VALUES (?, ?, datetime('now', ?), ?)",
        (src["id"], gmail_id, f"-{days_ago} days", "test signal watch"),
    )
    return cur.lastrowid


# ─────────────────────── watch_rate vigilance ──────────────────────────────

def test_watch_rate_insufficient_data(tmp_path, monkeypatch):
    """0 signal -> INSUFFICIENT_DATA."""
    _setup_db(tmp_path, monkeypatch)
    from intelligence import v2_vigilance
    from shared import storage

    with storage.db() as cx:
        r = v2_vigilance.check_watch_rate(cx, days=28)
    assert r["status"] == "INSUFFICIENT_DATA"
    assert r["n_total"] == 0


def test_watch_rate_ok_balanced(tmp_path, monkeypatch):
    """5 directional + 5 watch = 50% rate -> OK."""
    _setup_db(tmp_path, monkeypatch)
    from intelligence import v2_vigilance
    from shared import storage

    with storage.db() as cx:
        for i in range(5):
            _seed_v2_signal_with_pred(cx, gmail_id=f"d{i}")
        for i in range(5):
            _seed_v2_signal_watch_only(cx, gmail_id=f"w{i}")
        cx.commit()
        r = v2_vigilance.check_watch_rate(cx, days=28)
    assert r["status"] == "OK"
    assert r["n_total"] == 10
    assert r["watch_rate"] == 0.5


def test_watch_rate_alert_too_high(tmp_path, monkeypatch):
    """9 watch + 1 directional = 90% > 85% threshold -> ALERT (over-refusal)."""
    _setup_db(tmp_path, monkeypatch)
    from intelligence import v2_vigilance
    from shared import storage

    with storage.db() as cx:
        _seed_v2_signal_with_pred(cx, gmail_id="d0")
        for i in range(9):
            _seed_v2_signal_watch_only(cx, gmail_id=f"w{i}")
        cx.commit()
        r = v2_vigilance.check_watch_rate(cx, days=28)
    assert r["status"] == "ALERT"
    assert r["watch_rate"] == 0.9
    assert "ancrage" in r["message"]


def test_watch_rate_alert_too_low(tmp_path, monkeypatch):
    """9 directional + 1 watch = 10% < 20% threshold -> ALERT (over-commit)."""
    _setup_db(tmp_path, monkeypatch)
    from intelligence import v2_vigilance
    from shared import storage

    with storage.db() as cx:
        for i in range(9):
            _seed_v2_signal_with_pred(cx, gmail_id=f"d{i}")
        _seed_v2_signal_watch_only(cx, gmail_id="w0")
        cx.commit()
        r = v2_vigilance.check_watch_rate(cx, days=28)
    assert r["status"] == "ALERT"
    assert r["watch_rate"] == 0.1
    assert "sur-commitment" in r["message"]


# ─────────────────────── directional_spread vigilance ───────────────────────

def test_directional_spread_insufficient(tmp_path, monkeypatch):
    """<5 directional -> INSUFFICIENT_DATA."""
    _setup_db(tmp_path, monkeypatch)
    from intelligence import v2_vigilance
    from shared import storage

    with storage.db() as cx:
        for i in range(3):
            _seed_v2_signal_with_pred(cx, gmail_id=f"d{i}")
        cx.commit()
        r = v2_vigilance.check_directional_spread(cx, days=120)
    assert r["status"] == "INSUFFICIENT_DATA"
    assert r["n_directional"] == 3


def test_directional_spread_alert_mono_bucket(tmp_path, monkeypatch):
    """8 directional tous a 0.62 (1 bucket) -> ALERT mono-bucket demenage."""
    _setup_db(tmp_path, monkeypatch)
    from intelligence import v2_vigilance
    from shared import storage

    with storage.db() as cx:
        for i in range(8):
            _seed_v2_signal_with_pred(cx, gmail_id=f"d{i}", prob=0.62)
        cx.commit()
        r = v2_vigilance.check_directional_spread(cx, days=120)
    assert r["status"] == "ALERT"
    assert r["unique_buckets"] == 1
    assert "Mono-bucket" in r["message"]


def test_directional_spread_ok_diverse(tmp_path, monkeypatch):
    """8 directional spread sur 4+ buckets avec std > 0.05 -> OK."""
    _setup_db(tmp_path, monkeypatch)
    from intelligence import v2_vigilance
    from shared import storage

    probs = [0.58, 0.62, 0.68, 0.72, 0.78, 0.55, 0.65, 0.75]
    with storage.db() as cx:
        for i, p in enumerate(probs):
            _seed_v2_signal_with_pred(cx, gmail_id=f"d{i}", prob=p)
        cx.commit()
        r = v2_vigilance.check_directional_spread(cx, days=120)
    assert r["status"] == "OK"
    assert r["unique_buckets"] >= 3
    assert r["std"] >= 0.05


# ─────────────────────── insider_clusters_alive vigilance ───────────────────

def test_insider_clusters_alive_alert_no_data(tmp_path, monkeypatch):
    """0 cluster + 0 snapshot avec buys -> ALERT (job casse vraiment)."""
    _setup_db(tmp_path, monkeypatch)
    from intelligence import v2_vigilance
    from shared import storage

    with storage.db() as cx:
        r = v2_vigilance.check_insider_clusters_alive(cx, days=30)
    assert r["status"] == "ALERT"
    assert r["n"] == 0
    assert r["any_individual_buys"] == 0
    assert "0 cluster + 0 trade" in r["message"]


def test_insider_clusters_alive_info_dry_universe(tmp_path, monkeypatch):
    """0 cluster MAIS snapshots avec buys individuels -> INFO (univers sans clusters, pas bug)."""
    _setup_db(tmp_path, monkeypatch)
    from intelligence import v2_vigilance
    from shared import storage

    with storage.db() as cx:
        # Snapshots avec buys mais aucun cluster atteint
        for i in range(5):
            cx.execute(
                "INSERT INTO insider_snapshots (ticker, snapshot_date, n_buys, n_sells) "
                "VALUES (?, date('now', ?), ?, ?)",
                (f"T{i}", f"-{i} days", 1, 0),
            )
        cx.commit()
        r = v2_vigilance.check_insider_clusters_alive(cx, days=30)
    assert r["status"] == "INFO"
    assert r["n"] == 0
    assert r["any_individual_buys"] == 5
    assert "Normal for large-cap" in r["message"]


def test_insider_clusters_alive_ok_with_clusters(tmp_path, monkeypatch):
    """>= 1 cluster -> OK."""
    _setup_db(tmp_path, monkeypatch)
    from intelligence import v2_vigilance
    from shared import storage

    with storage.db() as cx:
        cx.execute(
            "INSERT INTO insider_buy_clusters_log (ticker, detected_at, distinct_buyers, total_buy_m, cluster_strength) "
            "VALUES (?, datetime('now', '-3 days'), ?, ?, ?)",
            ("ACME", 4, 8.5, "strong"),
        )
        cx.commit()
        r = v2_vigilance.check_insider_clusters_alive(cx, days=30)
    assert r["status"] == "OK"
    assert r["n"] == 1


# ─────────────────────── format_vigilance_report ────────────────────────────

def test_format_skips_ok_and_info(tmp_path, monkeypatch):
    """format_vigilance_report ne push QUE ALERT/WARN."""
    from intelligence import v2_vigilance

    results = [
        {"name": "watch_rate", "status": "OK", "message": "sain"},
        {"name": "directional_spread", "status": "INFO", "message": "normal"},
        {"name": "insider_clusters_alive", "status": "INSUFFICIENT_DATA", "message": "n/a"},
    ]
    assert v2_vigilance.format_vigilance_report(results) == ""


def test_format_includes_alert_and_warn(tmp_path, monkeypatch):
    """ALERT (🚨) et WARN (⚡) inclus, OK skip."""
    from intelligence import v2_vigilance

    results = [
        {"name": "watch_rate", "status": "ALERT", "message": "ancrage refus"},
        {"name": "directional_spread", "status": "WARN", "message": "spread faible"},
        {"name": "insider_clusters_alive", "status": "OK", "message": "sain"},
    ]
    msg = v2_vigilance.format_vigilance_report(results)
    assert "🚨" in msg
    assert "⚡" in msg
    assert "ancrage refus" in msg
    assert "spread faible" in msg
    assert "sain" not in msg  # OK skip


def test_run_all_vigilances_returns_3(tmp_path, monkeypatch):
    """run_all_vigilances retourne 6 dicts (smoke integration W13).
    Test renomme conserve par git tracking, count update 3 -> 6 apres
    extension scaffold sante distribution data (horizon, conviction, fx)."""
    _setup_db(tmp_path, monkeypatch)
    from intelligence import v2_vigilance

    results = v2_vigilance.run_all_vigilances()
    assert len(results) == 6
    names = {r["name"] for r in results}
    expected = {
        "watch_rate", "directional_spread", "insider_clusters_alive",
        "horizon_diversification", "conviction_distribution", "fx_freshness",
    }
    assert names == expected
