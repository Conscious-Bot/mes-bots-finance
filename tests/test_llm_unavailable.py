"""#93 Composant A1 -- unit tests (mock-based) sur detection LLMUnavailableError.

Garantit que les erreurs Anthropic credit_exhausted / rate_limited sont
mappees explicitement (raise LLMUnavailableError specifique), pas
swallow-and-return-None.

Spec user 03/06 : "JAMAIS default=0.5, JAMAIS drop silencieux (lecon
tennis-bot). Le bug '28/28 failed en silence' doit devenir impossible."

NB : control-flow / exception mapping = unit tests a mock. Property-based
reserve aux math (rule scorer #94 C1, Brier segmente #95).
"""

from __future__ import annotations

import pytest

from shared.llm import LLMUnavailableError, _classify_anthropic_error


class _MockResponse:
    """Mock anthropic.APIError.response qui expose status_code."""

    def __init__(self, status_code: int):
        self.status_code = status_code


# ─── Detection credit_exhausted (HTTP 400 + "credit balance too low") ─────────


def test_credit_balance_too_low_message_matches():
    """Le message canonique '...credit balance is too low...' est detecte."""
    e = Exception(
        "Error code: 400 - {'type': 'error', 'error': "
        "{'type': 'invalid_request_error', 'message': "
        "'Your credit balance is too low to access the Anthropic API.'}}"
    )
    out = _classify_anthropic_error(e)
    assert out is not None
    assert isinstance(out, LLMUnavailableError)
    assert out.reason == "credit_exhausted"


def test_credit_balance_too_low_lowercase_variant():
    """Insensible a la casse exacte."""
    e = Exception("credit balance too low or invalid")
    out = _classify_anthropic_error(e)
    assert out is not None
    assert out.reason == "credit_exhausted"


def test_credit_exhausted_preserves_upstream_msg():
    """upstream_msg conserve le message brut pour debug aval."""
    msg = "Error code: 400 - {'msg': 'credit balance is too low etc etc'}"
    e = Exception(msg)
    out = _classify_anthropic_error(e)
    assert out is not None
    assert msg in out.upstream_msg


# ─── Detection rate_limited (HTTP 429) ────────────────────────────────────────


def test_429_status_code_attribute():
    """Detection via status_code direct sur l'exception."""
    e = Exception("Too many requests")
    e.status_code = 429
    out = _classify_anthropic_error(e)
    assert out is not None
    assert out.reason == "rate_limited"


def test_429_status_code_via_response_attribute():
    """Detection via e.response.status_code (anthropic SDK style)."""
    e = Exception("rate limit hit")
    e.response = _MockResponse(429)
    out = _classify_anthropic_error(e)
    assert out is not None
    assert out.reason == "rate_limited"


def test_rate_limit_message_match():
    """Detection fallback sur substring 'rate limit'."""
    e = Exception("API rate limit exceeded for tier sonnet")
    out = _classify_anthropic_error(e)
    assert out is not None
    assert out.reason == "rate_limited"


def test_retry_after_extraction():
    """Si l'erreur contient un nombre plausible de secondes, retry_after extrait."""
    e = Exception("rate limit: retry after 60 seconds")
    out = _classify_anthropic_error(e)
    assert out is not None
    assert out.retry_after == 60


# ─── Non-classification : laisser remonter tel quel ────────────────────────────


def test_generic_500_not_classified():
    """500 ISE != indispo upstream sur credit -- laisser remonter brut."""
    e = Exception("Internal server error")
    e.status_code = 500
    assert _classify_anthropic_error(e) is None


def test_generic_400_without_credit_message_not_classified():
    """400 sans message credit = bug request, pas LLM unavailable."""
    e = Exception("Error 400: malformed JSON in request body")
    e.status_code = 400
    assert _classify_anthropic_error(e) is None


def test_json_decode_error_not_classified():
    """JSONDecodeError = output LLM malformed, pas indispo upstream."""
    import json
    try:
        json.loads("not json")
    except json.JSONDecodeError as e:
        assert _classify_anthropic_error(e) is None


def test_network_timeout_not_classified():
    """TimeoutError = network, pas notre perimetre 1A."""
    e = TimeoutError("connection timed out")
    assert _classify_anthropic_error(e) is None


# ─── Propriete : type stable de l'exception levee ──────────────────────────────


def test_llm_unavailable_error_is_runtime_error():
    """LLMUnavailableError est RuntimeError -- catch large 'except RuntimeError'
    fonctionne mais on prefere catch explicite 'except LLMUnavailableError'."""
    e = LLMUnavailableError("credit_exhausted", "test")
    assert isinstance(e, RuntimeError)
    assert isinstance(e, LLMUnavailableError)


def test_llm_unavailable_error_reason_required():
    """Le reason est obligatoire et figure dans str()."""
    e = LLMUnavailableError("credit_exhausted", "test msg")
    assert "credit_exhausted" in str(e)


def test_llm_unavailable_distinct_from_cost_cap():
    """CostCapExceeded != LLMUnavailableError. Premier = decision locale,
    second = upstream. Doivent rester distinguables pour traitement aval."""
    from shared.llm import CostCapExceeded
    cap = CostCapExceeded("local cap reached")
    unavailable = LLMUnavailableError("credit_exhausted", "upstream said no")
    assert not isinstance(cap, LLMUnavailableError)
    assert not isinstance(unavailable, CostCapExceeded)


# ─── Integration : pytest.raises explicit ────────────────────────────────────


def test_raises_can_catch_specifically():
    """Pattern usage : catch LLMUnavailableError specifiquement."""
    def some_consumer():
        raise LLMUnavailableError("credit_exhausted", "test")

    with pytest.raises(LLMUnavailableError) as exc:
        some_consumer()
    assert exc.value.reason == "credit_exhausted"


# ─── Consumers : mock llm pour valider catch + marquage pending_llm ──────────


def test_materiality_v2_propagates_llm_unavailable(monkeypatch):
    """materiality_v2.score_materiality_structured laisse remonter LLMUnavailableError
    (ne swallow pas en None silencieux). Le caller est responsable du marquage."""
    from intelligence import materiality_v2

    def _raise(*_args, **_kwargs):
        raise LLMUnavailableError("credit_exhausted", "test mock")

    monkeypatch.setattr("shared.llm.call", _raise)
    with pytest.raises(LLMUnavailableError):
        materiality_v2.score_materiality_structured(
            title="Test",
            summary="dummy",
            content="x",
            entities=["NVDA"],
            source_credibility=0.5,
        )


def test_signal_scorer_v2_propagates_llm_unavailable(monkeypatch):
    """signal_scorer_v2.score_directional_probability laisse remonter LLMUnavailableError."""
    from intelligence import signal_scorer_v2

    def _raise(*_args, **_kwargs):
        raise LLMUnavailableError("credit_exhausted", "test mock")

    monkeypatch.setattr("shared.llm.call", _raise)
    with pytest.raises(LLMUnavailableError):
        signal_scorer_v2.score_directional_probability(
            title="Test",
            summary="dummy",
            ticker="NVDA",
            horizon_days=30,
            content="x",
            entities=["NVDA"],
            source_name=None,
        )


def test_llm_status_set_to_degraded_on_unavailable(monkeypatch, tmp_path):
    """Quand call() catch credit_exhausted, set_llm_status('degraded') est invoque."""
    from shared import llm as llm_mod

    captured = []

    def _fake_set_status(status, reason=None, active_model=None):  # noqa: ARG001
        captured.append((status, reason))

    monkeypatch.setattr(llm_mod, "set_llm_status", _fake_set_status)

    # Mock le client anthropic pour qu'il leve une erreur credit_low
    class _FakeClient:
        class _Msgs:
            @staticmethod
            def create(**kwargs):
                raise Exception(
                    "Error code: 400 - {'error': "
                    "{'message': 'Your credit balance is too low'}}"
                )
        messages = _Msgs()

    monkeypatch.setattr(llm_mod, "client", lambda: _FakeClient())
    monkeypatch.setattr(llm_mod, "_check_cost_cap", lambda: None)

    with pytest.raises(LLMUnavailableError):
        llm_mod.call("test prompt", task="signal_scoring")

    assert ("degraded", "credit_exhausted") in captured


def test_llm_status_set_to_healthy_on_success(monkeypatch):
    """Quand call() reussit, set_llm_status('healthy') est invoque (recovery path)."""
    from shared import llm as llm_mod

    captured = []

    def _fake_set_status(status, reason=None, active_model=None):  # noqa: ARG001
        captured.append((status, reason))

    monkeypatch.setattr(llm_mod, "set_llm_status", _fake_set_status)

    class _FakeResp:
        class _Content:
            text = "  hello world  "
        content = [_Content()]
        usage = None

    class _FakeClient:
        class _Msgs:
            @staticmethod
            def create(**kwargs):
                return _FakeResp()
        messages = _Msgs()

    monkeypatch.setattr(llm_mod, "client", lambda: _FakeClient())
    monkeypatch.setattr(llm_mod, "_check_cost_cap", lambda: None)
    monkeypatch.setattr(llm_mod, "_compute_cost", lambda *a, **k: 0.0)
    monkeypatch.setattr(llm_mod, "_log_call", lambda *a, **k: None)

    out = llm_mod.call("test prompt", task="signal_scoring")
    assert out == "hello world"
    assert ("healthy", None) in captured
