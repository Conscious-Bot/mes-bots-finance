"""Gate d'identité Telegram (bot/main.py:authorize_middleware) — audit 04/07 E1.

Sans cette gate, tout expéditeur trouvant le @username pouvait exécuter les
commandes d'écriture (/position_buy, /kill_exec, /digue_override). On vérifie :
refus fail-closed hors allowlist, passage owner, mode dev (allowlist vide).

Pas de pytest-asyncio dans le repo → on drive la coroutine via asyncio.run.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from telegram.ext import ApplicationHandlerStop

import bot.main as main


def _update(chat_id=None, user_id=None, text="/portfolio"):
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id) if chat_id is not None else None,
        effective_user=SimpleNamespace(id=user_id, username="x") if user_id is not None else None,
        message=SimpleNamespace(text=text),
    )


def _run(update):
    return asyncio.run(main.authorize_middleware(update, None))


def test_owner_passes(monkeypatch):
    monkeypatch.setattr(main, "_authorized_chat_ids", lambda: {4242})
    _run(_update(chat_id=4242, user_id=4242))  # ne doit PAS lever


def test_stranger_blocked(monkeypatch):
    monkeypatch.setattr(main, "_authorized_chat_ids", lambda: {4242})
    with pytest.raises(ApplicationHandlerStop):
        _run(_update(chat_id=9999, user_id=9999))


def test_user_id_match_passes_in_group(monkeypatch):
    """Chat de groupe : chat_id = groupe, mais user_id owner autorisé → passe."""
    monkeypatch.setattr(main, "_authorized_chat_ids", lambda: {4242})
    _run(_update(chat_id=-100, user_id=4242))


def test_empty_allowlist_dev_mode_allows(monkeypatch):
    """TELEGRAM_CHAT_ID=0 (dev local) → gate désactivée, pas de blocage."""
    monkeypatch.setattr(main, "_authorized_chat_ids", lambda: set())
    _run(_update(chat_id=9999, user_id=9999))


def test_no_effective_ids_blocked(monkeypatch):
    """Update sans chat ni user identifiables + allowlist active → refus."""
    monkeypatch.setattr(main, "_authorized_chat_ids", lambda: {4242})
    with pytest.raises(ApplicationHandlerStop):
        _run(_update(chat_id=None, user_id=None))


def test_allowlist_reads_owner_and_extra(monkeypatch):
    monkeypatch.setattr(main.config, "telegram_chat_id", lambda: 4242)
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111, 222 , bad")
    ids = main._authorized_chat_ids()
    assert ids == {4242, 111, 222}  # 'bad' ignoré, pas de crash


def test_allowlist_empty_when_unconfigured(monkeypatch):
    monkeypatch.setattr(main.config, "telegram_chat_id", lambda: 0)
    monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
    assert main._authorized_chat_ids() == set()


def test_gate_wired_before_telemetry():
    """Câblage source : la gate est en group=-2 (avant télémétrie -1)."""
    from pathlib import Path

    src = Path("bot/main.py").read_text()
    assert "authorize_middleware), group=-2" in src
    assert "log_handler_call_middleware), group=-1" in src
