"""Tests digues de concentration ADR 015 (intelligence/digue_monitor.py).

Classifier pur = CI-safe (déterministe). Transitions journalisées = DB temp isolée.
"""

import sqlite3
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest

from intelligence import digue_monitor as dm

# ---------- classifier pur (source de vérité) ----------

@pytest.mark.parametrize(
    "dd,expected",
    [
        (0.0, "normal"),
        (-9.31, "normal"),
        (-14.99, "normal"),
        (-15.0, "gel_15"),
        (-24.99, "gel_15"),
        (-25.0, "gel_25"),
        (-34.99, "gel_25"),
        (-35.0, "prorata_35"),
        (-60.0, "prorata_35"),
    ],
)
def test_classify_digue_thresholds(dd, expected):
    assert dm.classify_digue(dd) == expected


def test_gel_states_all_freeze_prorata_only_at_35():
    """Un seul gel gradué : tout gel_* gèle ; prorata armé seulement à -35%."""
    assert dm.is_frozen("normal") is False
    assert dm.is_frozen("gel_15") is True
    assert dm.is_frozen("gel_25") is True
    assert dm.is_frozen("prorata_35") is True
    assert dm.is_prorata_armed("gel_15") is False
    assert dm.is_prorata_armed("gel_25") is False
    assert dm.is_prorata_armed("prorata_35") is True


def test_transition_direction():
    assert dm._transition("normal", "gel_15") == "escalation"
    assert dm._transition("gel_15", "prorata_35") == "escalation"
    assert dm._transition("prorata_35", "gel_15") == "recovery"
    assert dm._transition("gel_15", "normal") == "recovery"
    assert dm._transition("gel_25", "gel_25") == "no_change"


# ---------- state + transition avec DB temporaire isolée ----------

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """DB SQLite temp avec portfolio_snapshots + digue_alerts (schéma aligné prod :
    n_priced/n_positions requis par la garde « agrégat partiel ≠ total » 04/07)."""
    p = tmp_path / "t.db"
    c = sqlite3.connect(p)
    c.executescript(
        """
        CREATE TABLE portfolio_snapshots (
            snapshot_date TEXT, total_value_eur REAL, hwm_value_eur REAL,
            drawdown_pct REAL, n_priced INTEGER, n_positions INTEGER
        );
        CREATE TABLE digue_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            drawdown_pct REAL NOT NULL, hwm_value_eur REAL, current_value_eur REAL,
            snapshot_date TEXT,
            status TEXT NOT NULL CHECK(status IN ('normal','gel_15','gel_25','prorata_35')),
            notified INTEGER NOT NULL DEFAULT 0, transition TEXT
        );
        """
    )
    c.commit()
    c.close()
    from shared import storage

    monkeypatch.setattr(storage, "DB_PATH", str(p))
    # state store isolé (override + cooldown)
    sp = tmp_path / "state.json"
    sp.write_text("{}")
    monkeypatch.setattr(storage, "STATE_PATH", sp)
    return p


def _iso(days_ago: int = 0) -> str:
    """Dates RELATIVES (jamais hardcodées — leçon 15/06 : boundary temporel
    silencieux) ; la gate de staleness digue rendrait des dates figées fausses."""
    return (datetime.now(UTC).date() - timedelta(days=days_ago)).isoformat()


def _set_snapshot(db_path, date, value, hwm, dd, n_priced=26, n_positions=26):
    c = sqlite3.connect(db_path)
    c.execute(
        "INSERT INTO portfolio_snapshots VALUES (?,?,?,?,?,?)",
        (date, value, hwm, dd, n_priced, n_positions),
    )
    c.commit()
    c.close()


def test_current_state_normal_when_shallow(temp_db):
    _set_snapshot(temp_db, _iso(0), 54646, 60258, -9.31)
    st = dm.current_digue_state()
    assert st["available"] is True
    assert st["status"] == "normal"
    assert st["frozen"] is False


def test_current_state_frozen_at_minus_20(temp_db):
    _set_snapshot(temp_db, _iso(0), 48000, 60000, -20.0)
    st = dm.current_digue_state()
    assert st["status"] == "gel_15"
    assert st["frozen"] is True


def test_fail_open_when_no_snapshot(temp_db):
    """Aucun snapshot => available=False, frozen=False (ne fabrique PAS un gel)."""
    st = dm.current_digue_state()
    assert st["available"] is False
    assert st["frozen"] is False
    assert st["drawdown_pct"] is None


def test_check_transition_journals_and_notifies_on_escalation(temp_db):
    _set_snapshot(temp_db, _iso(0), 48000, 60000, -20.0)
    with mock.patch("shared.notify.send_text") as sent:
        out = dm.check_digue_transition()
    assert out["status"] == "gel_15"
    assert out["transition"] == "escalation"  # normal (default) -> gel_15
    assert out["notified"] is True
    sent.assert_called_once()
    # une row journalisée
    from shared import storage

    row = storage.get_latest_digue_alert()
    assert row["status"] == "gel_15"
    assert row["transition"] == "escalation"


def test_check_transition_no_change_second_cycle_no_notify(temp_db):
    _set_snapshot(temp_db, _iso(0), 48000, 60000, -20.0)
    with mock.patch("shared.notify.send_text"):
        dm.check_digue_transition()  # 1er : escalation
    with mock.patch("shared.notify.send_text") as sent2:
        out = dm.check_digue_transition()  # 2e : même état
    assert out["transition"] == "no_change"
    assert out["notified"] is False
    sent2.assert_not_called()


def test_check_transition_skips_when_signal_unavailable(temp_db):
    """Pas de snapshot => skip propre, 0 row, 0 notify (fail-open, pas de fabrication)."""
    with mock.patch("shared.notify.send_text") as sent:
        out = dm.check_digue_transition()
    assert out["status"] is None
    sent.assert_not_called()
    from shared import storage

    assert storage.get_latest_digue_alert() is None


# ---------- override Digue 1 (déblocage : cooldown + substance, jamais un clic) ----------

_VALID_PROTOCOL = (
    "Thèses cluster relues, sentinelles S4/S5 vertes, pas d'inflation de conviction, "
    "régime jugé correction cyclique — je maintiens et rouvre les ajouts."
)


def test_gate_allows_when_normal(temp_db):
    _set_snapshot(temp_db, _iso(0), 54646, 60258, -9.31)
    allow, msg = dm.gate_allows_buy()
    assert allow is True
    assert msg == ""


def test_gate_blocks_when_frozen_no_override(temp_db):
    _set_snapshot(temp_db, _iso(0), 48000, 60000, -20.0)
    allow, msg = dm.gate_allows_buy()
    assert allow is False
    assert "GELÉ" in msg


def test_override_refused_when_not_frozen(temp_db):
    _set_snapshot(temp_db, _iso(0), 54646, 60258, -9.31)
    ok, msg = dm.grant_override(_VALID_PROTOCOL)
    assert ok is False
    assert "Aucun gel" in msg


def test_override_refused_too_short(temp_db):
    _set_snapshot(temp_db, _iso(0), 48000, 60000, -20.0)
    ok, msg = dm.grant_override("ok débloque")
    assert ok is False
    assert "trop courte" in msg


def test_override_refused_during_cooldown(temp_db):
    """Cooldown incompressible : justification parfaite mais gel trop récent → refus."""
    _set_snapshot(temp_db, _iso(0), 48000, 60000, -20.0)
    from shared import storage

    storage.update_state(digue_gel_started_at=datetime.now(UTC).isoformat())  # gel = maintenant
    ok, msg = dm.grant_override(_VALID_PROTOCOL)
    assert ok is False
    assert "Cooldown" in msg


def test_override_granted_after_cooldown_then_gate_allows(temp_db):
    """Cooldown écoulé + protocole substantiel → override accordé → gate ré-autorise."""
    _set_snapshot(temp_db, _iso(0), 48000, 60000, -20.0)
    from shared import storage

    old = (datetime.now(UTC) - timedelta(days=dm.DIGUE_COOLDOWN_DAYS + 1)).isoformat()
    storage.update_state(digue_gel_started_at=old)
    ok, msg = dm.grant_override(_VALID_PROTOCOL)
    assert ok is True
    assert "accordé" in msg
    allow, gate_msg = dm.gate_allows_buy()
    assert allow is True
    assert "OVERRIDE" in gate_msg


def test_override_expires(temp_db):
    """Override expiré → gate re-bloque."""
    _set_snapshot(temp_db, _iso(0), 48000, 60000, -20.0)
    from shared import storage

    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    storage.update_state(
        digue_override={"granted_at": past, "expires_at": past, "text": _VALID_PROTOCOL}
    )
    allow, _ = dm.gate_allows_buy()
    assert allow is False


# ---------- honnêteté d'agrégat + staleness (cure 04/07/2026) ----------
# Classe « agrégat partiel ≠ total » : une row partielle (throttle yfinance un
# soir) compare un total tronqué au HWM book-complet → faux gel fabriqué.


def _purge_snapshots(db_path):
    c = sqlite3.connect(db_path)
    c.execute("DELETE FROM portfolio_snapshots")
    c.commit()
    c.close()


def test_partial_snapshot_row_ignored(temp_db):
    """Row partielle (13/26 pricées, dd -50 fabriqué) IGNORÉE : l'état se lit
    sur la dernière row complète (→ normal, pas de faux gel).

    HWM canonique (rewire 04/08) : le DD est RECALCULÉ contre canonical_hwm()
    (ancre policy 59 224), plus lu depuis la row (hwm_value_eur legacy).
    1 - 54646/59224 = -7.73%."""
    _set_snapshot(temp_db, _iso(1), 54646, 60258, -9.31)  # complète, hier
    _set_snapshot(temp_db, _iso(0), 30000, 60258, -50.0, n_priced=13)  # partielle
    st = dm.current_digue_state()
    assert st["available"] is True
    assert st["status"] == "normal"
    assert st["frozen"] is False
    assert st["drawdown_pct"] == pytest.approx(-7.73, abs=0.01)


def test_partial_only_fail_open(temp_db):
    """Seule une row partielle existe → signal indisponible, PAS de gel fabriqué."""
    _set_snapshot(temp_db, _iso(0), 30000, 60258, -50.0, n_priced=13)
    st = dm.current_digue_state()
    assert st["available"] is False
    assert st["frozen"] is False
    allow, msg = dm.gate_allows_buy()
    assert allow is True and msg == ""


def test_stale_snapshot_fail_open(temp_db):
    """Snapshot complet mais fossile (> DIGUE_STALE_AFTER_DAYS) → indisponible :
    un gel/dégel ne se décide pas sur une donnée qui a cessé d'être un signal."""
    _set_snapshot(temp_db, _iso(dm.DIGUE_STALE_AFTER_DAYS + 1), 48000, 60000, -20.0)
    st = dm.current_digue_state()
    assert st["available"] is False
    assert st["frozen"] is False
    allow, _ = dm.gate_allows_buy()
    assert allow is True


def test_stale_boundary_still_available(temp_db, monkeypatch):
    """Boundary : âge == DIGUE_STALE_AFTER_DAYS reste un signal (stale strict au-delà).
    Horloge FIGÉE pour tuer la fenêtre de flake minuit-UTC."""
    frozen = datetime.now(UTC)

    class _FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen if tz else frozen.replace(tzinfo=None)

    monkeypatch.setattr(dm, "datetime", _FrozenDT)
    day = (frozen.date() - timedelta(days=dm.DIGUE_STALE_AFTER_DAYS)).isoformat()
    _set_snapshot(temp_db, day, 48000, 60000, -20.0)
    st = dm.current_digue_state()
    assert st["available"] is True
    assert st["status"] == "gel_15"


# ---------- gel-hold + tolérance writer/reader + notify aveuglement (revue 04/07) ----------


def test_tolerated_gap_rows_consumed(temp_db):
    """Rows writer-tolérées (gap ≤ DIGUE_MAX_UNPRICED_GAP) consommées : un petit
    ticker durablement unpriced ne crée pas de corridor de désarmement. Gap 2
    = boundary tolérée, gap 3 = anormale (ignorée, fallback row précédente)."""
    _set_snapshot(temp_db, _iso(1), 54646, 60258, -9.31, n_priced=24)  # gap 2 : toléré
    _set_snapshot(temp_db, _iso(0), 30000, 60258, -50.0, n_priced=23)  # gap 3 : ignoré
    st = dm.current_digue_state()
    assert st["available"] is True
    assert st["status"] == "normal"
    # HWM canonique (04/08) : DD recalculé vs ancre 59 224, cf test_partial ci-dessus.
    assert st["drawdown_pct"] == pytest.approx(-7.73, abs=0.01)


def test_gel_hold_when_signal_lost_during_active_gel(temp_db):
    """Régression revue 04/07 : un gel ACTIF ne se dissout PAS sur signal perdu.
    Dernière évidence journalisée = gel → frozen maintenu, gate bloque et le dit."""
    _set_snapshot(temp_db, _iso(0), 48000, 60000, -20.0)
    with mock.patch("shared.notify.send_text"):
        dm.check_digue_transition()  # journalise gel_15
    _purge_snapshots(temp_db)  # pipeline snapshot cassé (simulé)
    st = dm.current_digue_state()
    assert st["available"] is False
    assert st["frozen"] is True
    assert st.get("signal_stale_hold") is True
    assert st["status"] == "gel_15"
    assert st["prorata_armed"] is False  # jamais d'armement sur donnée absente
    allow, msg = dm.gate_allows_buy()
    assert allow is False
    assert "MAINTENU" in msg


def test_no_gel_fabricated_when_signal_lost_without_gel(temp_db):
    """Sans gel journalisé, signal perdu = fail-open inchangé (pas de gel fantôme)."""
    _set_snapshot(temp_db, _iso(0), 54646, 60258, -9.31)
    with mock.patch("shared.notify.send_text"):
        dm.check_digue_transition()  # journalise normal
    _purge_snapshots(temp_db)
    st = dm.current_digue_state()
    assert st["frozen"] is False
    allow, _ = dm.gate_allows_buy()
    assert allow is True


def test_blindness_notified_once_then_cleared(temp_db):
    """Aveuglement → notify UNE fois par épisode (flag state), pas par run ;
    retour du signal → flag levé."""
    from shared import storage

    _set_snapshot(temp_db, _iso(0), 48000, 60000, -20.0)
    with mock.patch("shared.notify.send_text"):
        dm.check_digue_transition()  # journalise gel_15
    _purge_snapshots(temp_db)
    with mock.patch("shared.notify.send_text") as sent:
        dm.check_digue_transition()
        dm.check_digue_transition()  # 2e run : flag posé → silence
    assert sent.call_count == 1
    assert "AVEUGLE" in sent.call_args_list[0].args[0]
    assert storage.load_state().get("digue_stale_notified")
    _set_snapshot(temp_db, _iso(0), 48000, 60000, -20.0)  # signal revient
    with mock.patch("shared.notify.send_text"):
        dm.check_digue_transition()
    assert storage.load_state().get("digue_stale_notified") is None


def test_check_transition_partial_only_no_fabrication(temp_db):
    """Chemin complet check_digue_transition avec row partielle seule : status
    None, AUCUNE row digue_alerts fabriquée, seul le notify d'aveuglement part."""
    from shared import storage

    _set_snapshot(temp_db, _iso(0), 54646, 60258, -9.31)
    with mock.patch("shared.notify.send_text"):
        dm.check_digue_transition()  # journal : normal (le monitor a vécu)
    _purge_snapshots(temp_db)
    _set_snapshot(temp_db, _iso(0), 30000, 60258, -50.0, n_priced=13)
    with mock.patch("shared.notify.send_text") as sent:
        out = dm.check_digue_transition()
    assert out["status"] is None
    row = storage.get_latest_digue_alert()
    assert row["status"] == "normal"  # rien fabriqué depuis la row partielle
    assert sent.call_count == 1
    assert "AVEUGLE" in sent.call_args[0][0]
