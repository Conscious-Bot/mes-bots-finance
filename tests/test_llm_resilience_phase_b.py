"""#93 Phase B -- unit tests (mock-based) sur cost cap soft + Haiku auto
+ Telegram alert transitions + active_model state.

Spec user 03/06 (resilience_architecture_spine + degraded_restitution_contract) :
spine = Opus -> Haiku (80% cap) -> rule+BGE (LLM down) -> templates. La
phase B implemente la branche "Opus -> Haiku" et le wiring observability
(badge + alert) pour que la degradation ne soit JAMAIS silencieuse.

Tests :
1. _should_downgrade_to_haiku() honore le seuil 80%
2. _resolve_model() force Haiku quand soft cap franchi
3. _check_cost_cap() set status degraded AVANT de raise CostCapExceeded (100%)
4. set_llm_status() fire Telegram exactement une fois sur transition
5. set_llm_status() no-op si statut+reason identiques (debounce naturel)
6. active_model persiste dans bot_state.json + lu par get_llm_status

Pas property-based (control-flow + I/O state). Pas e2e (l'appel reel Anthropic
serait branche live et casserait sur LLMUnavailableError de prod).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from shared import llm


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Isole chaque test : bot_state.json prive + warned counter reset."""
    # Override BOT_STATE_PATH-equivalent : patch storage.load/save_state.
    state: dict = {}

    def _load():
        return dict(state)

    def _save(s):
        state.clear()
        state.update(s)

    monkeypatch.setattr("shared.storage.load_state", _load)
    monkeypatch.setattr("shared.storage.save_state", _save)
    # Reset module-level cost cap counter.
    monkeypatch.setattr(llm, "_COST_CAP_LAST_WARNED", 0.0)
    yield state


# ─── 1. _should_downgrade_to_haiku() threshold ───────────────────────────


def test_downgrade_haiku_off_below_80pct(monkeypatch):
    monkeypatch.setenv("LLM_COST_CAP_USD_24H", "10.0")
    monkeypatch.delenv("LLM_COST_CAP_DISABLE", raising=False)
    monkeypatch.setattr(llm, "_get_cost_usage_24h", lambda: 7.5)  # 75%
    assert llm._should_downgrade_to_haiku() is False


def test_downgrade_haiku_on_at_80pct(monkeypatch):
    monkeypatch.setenv("LLM_COST_CAP_USD_24H", "10.0")
    monkeypatch.delenv("LLM_COST_CAP_DISABLE", raising=False)
    monkeypatch.setattr(llm, "_get_cost_usage_24h", lambda: 8.0)  # 80% exact
    assert llm._should_downgrade_to_haiku() is True


def test_downgrade_haiku_off_when_cap_disabled(monkeypatch):
    monkeypatch.setenv("LLM_COST_CAP_DISABLE", "1")
    monkeypatch.setattr(llm, "_get_cost_usage_24h", lambda: 9999)
    assert llm._should_downgrade_to_haiku() is False


# ─── 2. _resolve_model() honore le downgrade ─────────────────────────────


def test_resolve_model_normal_synthesize_returns_opus(monkeypatch):
    monkeypatch.setattr(llm, "_should_downgrade_to_haiku", lambda: False)
    model, tier = llm._resolve_model(tier="synthesize")
    assert "opus" in model.lower()
    assert tier == "synthesize"


def test_resolve_model_softcap_forces_haiku_even_on_synthesize(monkeypatch):
    monkeypatch.setattr(llm, "_should_downgrade_to_haiku", lambda: True)
    model, tier = llm._resolve_model(tier="synthesize")
    assert "haiku" in model.lower()
    assert tier == "synthesize+haiku_softcap"


def test_resolve_model_softcap_noop_on_extract_tier(monkeypatch):
    """Si tier='extract' deja Haiku, pas de marker softcap (rien a downgrade)."""
    monkeypatch.setattr(llm, "_should_downgrade_to_haiku", lambda: True)
    model, tier = llm._resolve_model(tier="extract")
    assert "haiku" in model.lower()
    assert "softcap" not in tier  # deja sur Haiku, pas de marker


# ─── 3. _check_cost_cap() set status AVANT de raise ──────────────────────


def test_check_cost_cap_hard_sets_degraded_before_raise(monkeypatch, reset_state):
    monkeypatch.setenv("LLM_COST_CAP_USD_24H", "10.0")
    monkeypatch.delenv("LLM_COST_CAP_DISABLE", raising=False)
    monkeypatch.setattr(llm, "_get_cost_usage_24h", lambda: 10.5)  # 105%
    # Mute Telegram pendant le test
    with patch("shared.notify.send_text"), pytest.raises(llm.CostCapExceeded):
        llm._check_cost_cap()
    # State doit avoir ete ecrit AVANT le raise
    st = llm.get_llm_status()
    assert st["status"] == "degraded"
    assert st["reason"] == "cost_cap_hard"


# ─── 4. Telegram alert sur transition (exactement une fois) ──────────────


def test_set_status_transition_healthy_to_degraded_fires_alert(reset_state):
    # Init healthy
    with patch("shared.notify.send_text") as mock_send:
        llm.set_llm_status("healthy", reason=None, active_model="sonnet")
        # healthy->healthy = no transition => no alert
        # Mais le test fixture state est vide au depart -> set_llm_status
        # ecrit la 1ere fois. La 1ere ecriture nest pas une transition.
        first_call_count = mock_send.call_count

        llm.set_llm_status("degraded", reason="credit_exhausted", active_model=None)
        assert mock_send.call_count == first_call_count + 1
        msg = mock_send.call_args[0][0]
        assert "degraded" in msg.lower() or "⚠" in msg


def test_set_status_no_alert_on_same_state(reset_state):
    """set_llm_status no-op si statut+reason identiques -> pas d'alert spam."""
    with patch("shared.notify.send_text") as mock_send:
        llm.set_llm_status("degraded", reason="credit_exhausted")
        n_after_first = mock_send.call_count
        # Re-fire identique
        llm.set_llm_status("degraded", reason="credit_exhausted")
        llm.set_llm_status("degraded", reason="credit_exhausted")
        assert mock_send.call_count == n_after_first  # no new alert


def test_set_status_recovery_fires_alert(reset_state):
    """degraded -> healthy = alert 'LLM recovered'."""
    with patch("shared.notify.send_text") as mock_send:
        llm.set_llm_status("degraded", reason="credit_exhausted")
        before = mock_send.call_count
        llm.set_llm_status("healthy", reason=None, active_model="sonnet")
        assert mock_send.call_count == before + 1
        msg = mock_send.call_args[0][0]
        assert "recover" in msg.lower() or "✅" in msg


def test_set_status_degraded_to_degraded_different_reason_no_alert(reset_state):
    """degraded(rate_limited) -> degraded(credit_exhausted) NE doit PAS spam.

    Un mode degrade reste degrade. Les details vont dans state.reason +
    le log, pas dans des alerts Telegram en cascade.
    """
    with patch("shared.notify.send_text") as mock_send:
        llm.set_llm_status("degraded", reason="rate_limited")
        before = mock_send.call_count
        llm.set_llm_status("degraded", reason="credit_exhausted")
        # Transition table inclut PAS (degraded, degraded) -> 0 alert nouvelle
        # MAIS set_llm_status ecrit quand meme l'etat (reason different).
        assert mock_send.call_count == before


# ─── 5. active_model persiste + remonte ──────────────────────────────────


def test_active_model_persists_in_state(reset_state):
    llm.set_llm_status("healthy", reason=None, active_model="sonnet")
    st = llm.get_llm_status()
    assert st["active_model"] == "sonnet"

    llm.set_llm_status("degraded", reason="cost_cap_soft", active_model="haiku")
    st = llm.get_llm_status()
    assert st["status"] == "degraded"
    assert st["active_model"] == "haiku"


def test_model_short_name_helper():
    assert llm._model_short_name("claude-haiku-4-5-20251001") == "haiku"
    assert llm._model_short_name("claude-sonnet-4-6") == "sonnet"
    assert llm._model_short_name("claude-opus-4-7") == "opus"
    assert llm._model_short_name(None) is None
    assert llm._model_short_name("") is None
