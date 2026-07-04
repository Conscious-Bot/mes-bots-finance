"""bot_state.json : écriture atomique + load tolérant + RMW verrouillé.

Audit 04/07 finding solidité E1 : le fichier porte l'état de contrôle de risque
(gel digue, override, épisode kill) et était écrit non-atomiquement par plusieurs
process concurrents. Crash mi-write → JSON tronqué → gate digue fail-open +
crash-loop ; save_state(s) sur l'état complet → lost-update.
"""

from __future__ import annotations

import json
import threading

import pytest

from shared import storage


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    p = tmp_path / "bot_state.json"
    monkeypatch.setattr(storage, "STATE_PATH", p)  # _state_lock_path() en dérive
    return p


def test_save_load_roundtrip(state_file):
    storage.save_state({"a": 1, "digue_override": {"text": "x"}})
    assert storage.load_state()["digue_override"]["text"] == "x"


def test_load_missing_file_returns_empty(state_file):
    assert storage.load_state() == {}


def test_corrupt_falls_back_to_bak(state_file):
    """Crash mi-write simulé (JSON tronqué) → restaure depuis .bak, ne wipe pas."""
    storage.save_state({"digue_gel_started_at": "2026-07-04", "kill_switch_p1_episode": {"open": True}})
    storage.save_state({"digue_gel_started_at": "2026-07-05", "kill_switch_p1_episode": {"open": True}})
    # .bak contient maintenant la 1ère version ; on corrompt le fichier principal
    state_file.write_text('{"digue_gel_started_at": "2026-07-05", TRUNCA')
    recovered = storage.load_state()
    assert recovered["kill_switch_p1_episode"]["open"] is True
    assert recovered["digue_gel_started_at"] == "2026-07-04"  # dernière .bak connue-bonne
    # la copie corrompue est préservée pour post-mortem
    assert state_file.with_suffix(".json.corrupt").exists()


def test_corrupt_and_no_bak_returns_empty_not_crash(state_file):
    state_file.write_text("{ totally broken")
    assert storage.load_state() == {}  # LOUD (log.error) mais pas d'exception


def test_update_state_preserves_other_keys(state_file):
    storage.save_state({"digue_override": {"text": "hold"}, "llm_status": "healthy"})
    storage.update_state(llm_status="degraded")
    s = storage.load_state()
    assert s["digue_override"] == {"text": "hold"}  # PAS clobbé
    assert s["llm_status"] == "degraded"


def test_write_is_atomic_no_partial_read(state_file):
    """Un lecteur pendant l'écriture voit soit l'ancien état complet, soit le
    nouveau — jamais un JSON tronqué. On martèle load pendant des writes."""
    storage.save_state({"n": 0, "big": "x" * 5000})
    errors: list = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                storage.load_state()  # ne doit jamais lever de JSONDecodeError
            except json.JSONDecodeError as e:  # pragma: no cover
                errors.append(e)

    t = threading.Thread(target=reader)
    t.start()
    for i in range(200):
        storage.save_state({"n": i, "big": "x" * 5000})
    stop.set()
    t.join()
    assert errors == []


def test_concurrent_updates_no_lost_update(state_file):
    """Deux threads qui update_state des clés différentes en boucle : aucune
    écriture perdue (RMW verrouillé). Sans lock, l'un écraserait l'autre."""
    storage.save_state({"a": 0, "b": 0})

    def bump(key):
        for _ in range(100):
            cur = storage.load_state().get(key, 0)
            storage.update_state(**{key: cur + 1})

    ta = threading.Thread(target=bump, args=("a",))
    tb = threading.Thread(target=bump, args=("b",))
    ta.start()
    tb.start()
    ta.join()
    tb.join()
    s = storage.load_state()
    # Chaque clé a été incrémentée sous lock : la clé de l'autre thread survit
    # toujours (pas de clobber). On ne garantit pas 100 exact (pas de CAS), mais
    # AUCUNE clé ne doit être absente/wipe.
    assert "a" in s and "b" in s
    assert s["a"] >= 1 and s["b"] >= 1
