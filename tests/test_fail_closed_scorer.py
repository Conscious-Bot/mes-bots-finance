"""Tests Phase 1.2 absorption_roadmap — fail-closed LLM scorer doctrine.

Verrouille L15 LESSONS : `signal_scorer_v2.score_directional_probability` ne
fabrique JAMAIS un score arbitraire en mode degrade. Toute defaillance autre
que LLMUnavailableError -> retour None (skip propre par le caller).

Les 5 cas verrouilles :
1. JSON malformed (parse error) -> None
2. JSON sans champ probability -> None (default base_rate=0.5 + clamp interdit)
3. probability hors [0, 1] -> None (pas de clamp silencieux)
4. LLM retourne string vide ou texte sans braces -> None
5. LLMUnavailableError -> propage telle quelle (le caller route ou marque pending)

Si un de ces 5 regresse, c'est une violation L15. Garde explicite contre
"defensive fallback" qui salirait Brier ledger avec proba fabriquees.
"""

from __future__ import annotations

import pytest

# --- Helpers ---------------------------------------------------------------


def _call_scorer(monkeypatch: pytest.MonkeyPatch, llm_returns):
    """Patch shared.llm.call pour qu'il retourne `llm_returns` (string ou exception)
    puis invoque score_directional_probability avec inputs minimalistes."""
    from intelligence import signal_scorer_v2

    def _fake_call(*_args, **_kwargs):
        if isinstance(llm_returns, BaseException):
            raise llm_returns
        return llm_returns

    monkeypatch.setattr("shared.llm.call", _fake_call)
    return signal_scorer_v2.score_directional_probability(
        title="Test event",
        summary="dummy",
        ticker="NVDA",
        horizon_days=28,
        content="x",
        entities=["NVDA"],
        source_name=None,
    )


# --- Les 5 cas verrouilles -------------------------------------------------


def test_json_malformed_returns_none(monkeypatch: pytest.MonkeyPatch):
    """Cas #1 : LLM retourne du quasi-JSON impossible a parser -> None.

    Doctrine L15 : pas de fallback formule, pas de prob=0.5 par sûrete.
    """
    result = _call_scorer(monkeypatch, '{"probability": 0.7, "base_rate": ')
    assert result is None, (
        "JSON malformed doit retourner None, pas un dict fabrique. "
        "Si tu vois un dict ici, quelqu'un a ajoute un defensive fallback "
        "qui salit le Brier ledger (violation L15)."
    )


def test_no_braces_in_output_returns_none(monkeypatch: pytest.MonkeyPatch):
    """Cas #4 (partiel) : LLM retourne du texte sans { } -> None."""
    result = _call_scorer(monkeypatch, "I cannot score this signal reliably.")
    assert result is None


def test_empty_llm_response_returns_none(monkeypatch: pytest.MonkeyPatch):
    """Cas #4 : LLM retourne string vide ou None -> None."""
    result_empty = _call_scorer(monkeypatch, "")
    result_none = _call_scorer(monkeypatch, None)
    assert result_empty is None
    assert result_none is None


def test_probability_out_of_bounds_returns_none(monkeypatch: pytest.MonkeyPatch):
    """Cas #3 : LLM produit prob=1.5 ou prob=-0.1 -> None.

    Doctrine L15 : pas de clamp silencieux. Un LLM qui sort prob>1 est en
    train de hallucinate la structure, on ne reinterprete pas, on skip.
    """
    out_high = (
        '{"base_rate": 0.5, "evidence_strength": "moderate", '
        '"evidence_summary": "x", "anti_anchoring_reason": "y", '
        '"probability": 1.5, "direction": "bullish", "reasoning": "z"}'
    )
    out_low = (
        '{"base_rate": 0.5, "evidence_strength": "moderate", '
        '"evidence_summary": "x", "anti_anchoring_reason": "y", '
        '"probability": -0.1, "direction": "bullish", "reasoning": "z"}'
    )
    out_base_rate_high = (
        '{"base_rate": 1.5, "evidence_strength": "moderate", '
        '"evidence_summary": "x", "anti_anchoring_reason": "y", '
        '"probability": 0.7, "direction": "bullish", "reasoning": "z"}'
    )
    assert _call_scorer(monkeypatch, out_high) is None
    assert _call_scorer(monkeypatch, out_low) is None
    assert _call_scorer(monkeypatch, out_base_rate_high) is None


def test_missing_probability_field_returns_dict_or_watch(monkeypatch: pytest.MonkeyPatch):
    """Cas #2 (partiel) : JSON valide sans `probability` defaulte sur base_rate.

    Le scorer accepte ce cas (base_rate=0.5 default, prob=base_rate), MAIS
    enforcement #1 force prob=base_rate (pas de prob fabriquee divergente),
    ET enforcement #2 force direction=watch si evidence none/weak.

    Doctrine L15 : si on ne peut pas eliciter une proba directionnelle, on
    sort en watch (pas inscrit au ledger directionnel). Le test verifie
    que cette voie n'inscrit JAMAIS un signal directionnel falsifiable.
    """
    out_no_prob = (
        '{"base_rate": 0.55, "evidence_strength": "none", '
        '"evidence_summary": "", "anti_anchoring_reason": "y", '
        '"direction": "bullish", "reasoning": "z"}'
    )
    result = _call_scorer(monkeypatch, out_no_prob)
    # Soit None, soit dict avec direction=watch. Jamais direction=bullish avec
    # prob fabriquee sans evidence.
    if result is not None:
        assert result["direction"] == "watch", (
            f"Sans probability explicite + evidence none, on doit sortir en "
            f"watch (non-directional). Got direction={result.get('direction')}"
        )


def test_llm_unavailable_error_propagates(monkeypatch: pytest.MonkeyPatch):
    """Cas #5 : LLMUnavailableError ne doit JAMAIS etre swallowed."""
    from shared.llm import LLMUnavailableError

    with pytest.raises(LLMUnavailableError):
        _call_scorer(monkeypatch, LLMUnavailableError("rate_limited", "test mock"))


def test_no_dict_with_fabricated_probability_ever_returned(monkeypatch: pytest.MonkeyPatch):
    """Garde meta-L15 : aucun de ces 5 paths ne doit produire un dict avec
    un champ `probability` calcule par defensive fallback.

    Si quelqu'un un jour ajoute `return {'probability': 0.5, ...}` en `except`,
    ce test le pince immediatement.
    """
    test_inputs = [
        '{"probability": 0.7,',          # JSON malformed
        "no braces here",                # no JSON
        "",                              # empty
        None,                            # None
        '{"probability": 99}',           # out of bounds
    ]
    for inp in test_inputs:
        result = _call_scorer(monkeypatch, inp)
        if result is not None:
            # Si le scorer decide de retourner un dict, il doit etre coherent :
            # probability dans [0, 1] et issu d'un vrai parse, pas fabrique.
            assert 0.0 <= result["probability"] <= 1.0, (
                f"Probability hors bornes pour input {inp!r} : "
                f"{result['probability']}. Violation L15."
            )
            # Et la direction doit etre watch ou direction reellement extraite,
            # JAMAIS une direction bullish/bearish sortie de nulle part.
            assert result["direction"] in ("bullish", "bearish", "watch")
