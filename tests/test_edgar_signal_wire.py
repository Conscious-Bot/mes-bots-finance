"""Wire SEC 8-K -> signals -> V2 -> predictions : tests unit + e2e.

L'arc (decision log #01 iter 6+) : edgar_exhibits.extract_filing_content() resout
le contenu material des 8-K. edgar_signal_wire.wire_8k_to_signal() insere le
signal dans la pipeline. EightKSource.persist() appelle le wire sync.

Tests :
1. unit : wire avec mock extract -> verifie signal cree avec bon source_id,
   signal_type, gmail_id dedup. Sans network ni LLM.
2. unit dedup : 2 appels meme accession -> 1 signal en DB.
3. unit skip : extract retourne contenu trop court -> pas de signal.
4. e2e (slow) : vraie NVDA 8-K -> wire -> verifie prediction registree par V2.
"""

import json
import sqlite3

import pytest


def _setup_isolated_db(tmp_path, monkeypatch):
    """Cree une DB SQLite isolee + monkeypatch storage.DB_PATH.

    Apres consolidation 30/05 (commit X) : storage._DB_PATH est resolu
    dynamiquement via __getattr__ -> retourne DB_PATH courant. Donc UN seul
    monkeypatch sur DB_PATH suffit, _DB_PATH suit automatiquement.

    Schema minimal : sources, signals, predictions (le module wire n'utilise pas
    les autres tables).
    """
    db_path = tmp_path / "test_wire.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
    CREATE TABLE sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        type TEXT NOT NULL,
        credibility REAL,
        n_signals INTEGER DEFAULT 0,
        family TEXT NOT NULL DEFAULT 'narrative_newsletter'
    );
    CREATE TABLE signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER,
        gmail_id TEXT UNIQUE,
        timestamp TEXT NOT NULL,
        title TEXT,
        content TEXT,
        summary TEXT,
        score INTEGER,
        sentiment TEXT,
        entities TEXT,
        signal_type TEXT,
        impact_magnitude REAL
    );
    """)
    conn.commit()
    conn.close()

    from shared import storage
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    # _DB_PATH n'a plus besoin d'etre patch separement (cf storage.__getattr__).
    return db_path


def test_wire_8k_inserts_signal_with_correct_metadata(tmp_path, monkeypatch):
    """Unit : wire avec mock extract -> signal insere avec metadata canonique."""
    _setup_isolated_db(tmp_path, monkeypatch)

    # Mock extract_filing_content pour eviter network
    from shared import edgar_exhibits
    monkeypatch.setattr(
        edgar_exhibits, "extract_filing_content",
        lambda url: "Mock material content " * 100  # >500 chars
    )

    from intelligence import edgar_signal_wire
    from shared import storage

    filing = {
        "ticker": "NVDA",
        "accession": "0001045810-26-000051",
        "url": "https://www.sec.gov/example/nvda-20260520.htm",
        "filed_at": "2026-05-20",
        "items_raw": "2.02,9.01",
    }

    signal_id = edgar_signal_wire.wire_8k_to_signal(filing)
    assert signal_id is not None, "wire returned None on valid filing"

    with storage.db() as cx:
        row = cx.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
        assert row is not None
        d = dict(row)
        assert d["signal_type"] == "catalyst"
        assert d["score"] == 7
        assert d["sentiment"] == "bullish"  # placeholder, V2 recalcule
        assert d["gmail_id"] == "sec_8k:0001045810-26-000051"
        assert "NVDA" in d["title"]
        assert "2.02" in d["title"]
        assert json.loads(d["entities"]) == ["NVDA"]

        # Source dediee creee correctement
        src = cx.execute("SELECT * FROM sources WHERE id = ?", (d["source_id"],)).fetchone()
        assert dict(src)["name"] == "SEC EDGAR 8-K"
        assert dict(src)["type"] == "sec_filing"
        assert dict(src)["credibility"] == 0.85


def test_wire_8k_dedup_via_accession(tmp_path, monkeypatch):
    """2 appels meme accession -> 1 signal en DB (pas de doublon)."""
    _setup_isolated_db(tmp_path, monkeypatch)

    from shared import edgar_exhibits
    monkeypatch.setattr(
        edgar_exhibits, "extract_filing_content",
        lambda url: "Mock material content " * 100
    )

    from intelligence import edgar_signal_wire
    from shared import storage

    filing = {
        "ticker": "NVDA", "accession": "0001045810-26-000051",
        "url": "https://example.com/nvda.htm",
        "filed_at": "2026-05-20", "items_raw": "2.02,9.01",
    }

    id1 = edgar_signal_wire.wire_8k_to_signal(filing)
    id2 = edgar_signal_wire.wire_8k_to_signal(filing)  # 2eme appel

    assert id1 == id2, "dedup doit retourner le meme signal_id"
    with storage.db() as cx:
        n = cx.execute("SELECT COUNT(*) c FROM signals WHERE gmail_id = ?",
                       ("sec_8k:0001045810-26-000051",)).fetchone()["c"]
    assert n == 1, f"dedup viole : {n} signals en DB pour meme accession"


def test_wire_8k_skip_on_insufficient_content(tmp_path, monkeypatch):
    """Extract retourne contenu trop court -> wire skip (pas de signal cree)."""
    _setup_isolated_db(tmp_path, monkeypatch)

    from shared import edgar_exhibits
    monkeypatch.setattr(
        edgar_exhibits, "extract_filing_content",
        lambda url: "short"  # < 500 chars
    )

    from intelligence import edgar_signal_wire
    from shared import storage

    filing = {
        "ticker": "NVDA", "accession": "0001045810-26-000051",
        "url": "https://example.com/nvda.htm",
        "filed_at": "2026-05-20", "items_raw": "5.02",
    }

    signal_id = edgar_signal_wire.wire_8k_to_signal(filing)
    assert signal_id is None, "wire should skip on insufficient content"

    with storage.db() as cx:
        n = cx.execute("SELECT COUNT(*) c FROM signals").fetchone()["c"]
    assert n == 0


def test_wire_buy_cluster_inserts_signal_with_correct_metadata(tmp_path, monkeypatch):
    """Unit : wire insider cluster -> signal insere avec metadata canonique
    (source distincte du 8-K, dedup key insider_cluster:ticker:date)."""
    _setup_isolated_db(tmp_path, monkeypatch)

    from intelligence import edgar_signal_wire
    from shared import storage

    cluster = {
        "cluster_strength": "strong",
        "distinct_buyers": 4,
        "total_buy_m": 8.5,
        "_price_at_detection": 145.20,
        "window_days": 30,
        "top_buyers": [
            {"name": "John Smith", "role": "CEO", "amount": 3500000, "date": "2026-05-15"},
            {"name": "Jane Doe", "role": "CFO", "amount": 2200000, "date": "2026-05-18"},
            {"name": "Bob Lee", "role": "Director", "amount": 1800000, "date": "2026-05-20"},
            {"name": "Alice Wong", "role": "Director", "amount": 1000000, "date": "2026-05-22"},
        ],
    }

    signal_id = edgar_signal_wire.wire_buy_cluster_to_signal(
        cluster=cluster, ticker="ACME", detected_at="2026-05-30 10:00:00"
    )
    assert signal_id is not None

    with storage.db() as cx:
        row = cx.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
        d = dict(row)
        assert d["signal_type"] == "catalyst"
        assert d["score"] == 7
        assert d["gmail_id"] == "insider_cluster:ACME:2026-05-30"
        assert "ACME" in d["title"]
        assert "strong" in d["title"]
        # Content doit contenir les top buyers (V2 a besoin de cette specificite)
        assert "John Smith" in d["content"]
        assert "CEO" in d["content"]
        assert "$3,500,000" in d["content"]

        # Source distincte du 8-K
        src = cx.execute("SELECT * FROM sources WHERE id = ?", (d["source_id"],)).fetchone()
        assert dict(src)["name"] == "SEC EDGAR Insider Cluster"
        assert dict(src)["type"] == "sec_filing"


def test_wire_buy_cluster_dedup(tmp_path, monkeypatch):
    """2 detections meme (ticker, date) -> 1 signal en DB."""
    _setup_isolated_db(tmp_path, monkeypatch)

    from intelligence import edgar_signal_wire
    from shared import storage

    cluster = {
        "cluster_strength": "strong",
        "distinct_buyers": 4,
        "total_buy_m": 12.3,
        "_price_at_detection": 88.40,
        "window_days": 30,
        "top_buyers": [
            {"name": "Sarah Chen", "role": "CEO", "amount": 4_800_000, "date": "2026-05-12"},
            {"name": "Marcus Bell", "role": "CFO", "amount": 3_500_000, "date": "2026-05-14"},
            {"name": "Priya Singh", "role": "COO", "amount": 2_200_000, "date": "2026-05-19"},
            {"name": "Tom O'Brien", "role": "Director", "amount": 1_800_000, "date": "2026-05-22"},
        ],
    }
    id1 = edgar_signal_wire.wire_buy_cluster_to_signal(cluster, "ACME", "2026-05-30 10:00:00")
    id2 = edgar_signal_wire.wire_buy_cluster_to_signal(cluster, "ACME", "2026-05-30 18:00:00")  # meme jour
    assert id1 is not None, "wire pre-condition: insert OK"
    assert id1 == id2
    with storage.db() as cx:
        n = cx.execute("SELECT COUNT(*) c FROM signals WHERE gmail_id LIKE 'insider_cluster:ACME:%'").fetchone()["c"]
    assert n == 1


@pytest.mark.slow
def test_e2e_wire_real_nvda_8k_produces_strong_prediction(tmp_path, monkeypatch):
    """E2E : vraie NVDA Q1 FY27 8-K -> extract reel -> V2 reel -> signal +
    prediction registre. Confirme que la chaine complete fonctionne.

    Marker slow : depend du reseau SEC + 1 call Sonnet (~10s total).
    """
    _setup_isolated_db(tmp_path, monkeypatch)

    # Aussi besoin de predictions table pour register
    from shared import storage
    with storage.db() as cx:
        cx.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER,
            ticker TEXT,
            direction TEXT,
            horizon_days INTEGER,
            baseline_price REAL,
            baseline_date TEXT,
            target_date TEXT,
            probability_at_creation REAL,
            scoring_trace_json TEXT,
            source_metadata_json TEXT,
            methodology_version TEXT NOT NULL
        )""")
        cx.commit()

    from intelligence import edgar_signal_wire

    nvda_filing = {
        "ticker": "NVDA",
        "accession": "0001045810-26-000051",
        "url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000051/nvda-20260520.htm",
        "filed_at": "2026-05-20",
        "items_raw": "2.02,9.01",
    }

    result = edgar_signal_wire.wire_and_register_8k(nvda_filing)
    assert result["wired"] is True, f"wire failed: {result.get('reason_if_skipped')}"
    assert result["signal_id"] is not None

    # V2 doit avoir register au moins 1 prediction (NVDA earnings -> bullish strong)
    assert len(result["registered_predictions"]) >= 1, (
        "Aucune prediction enregistree -- V2 a peut-etre sorti watch, "
        "mais NVDA Q1 FY27 earnings doit produire bullish strong"
    )

    # Verifier la prediction stockee
    with storage.db() as cx:
        pred = cx.execute(
            "SELECT * FROM predictions WHERE signal_id = ?", (result["signal_id"],)
        ).fetchone()
        assert pred is not None
        d = dict(pred)
        assert d["ticker"] == "NVDA"
        assert d["direction"] == "bullish"
        assert d["probability_at_creation"] >= 0.65, (
            f"NVDA earnings doit produire prob >= 0.65 via wire e2e, got {d['probability_at_creation']}"
        )
