"""#94 Phase 4 -- Degraded restitution contract tests.

Garanties :
1. Format canonique : "⦿ <surface> indisponible (LLM · <reason>)"
2. Pas de prose qui imite le raisonnement (defense vs faux verbe d'opinion)
3. Reason None gracieusement gere ('?' au lieu de None bare)
4. Rule fallback marker explicite la determinisme + hors headline
5. is_synthesized_marker detecte correctement
6. Consumers chat.py + analyze.py utilisent la source unique (pas de
   duplication de strings dans le code)

Spec user 03/06 (degraded_restitution_contract) :
  "The form that imitates reasoning without reasoning = the only thing banned."
"""

from __future__ import annotations

import pytest

from dashboard.restitution import (
    LLM_UNAVAILABLE_MARKER_PREFIX,
    format_llm_unavailable_marker,
    format_rule_fallback_provenance,
    is_synthesized_marker,
)

# ─── 1. Format canonique ──────────────────────────────────────────────────


def test_format_canonical_credit_exhausted():
    """credit_exhausted -> marker structure attendu."""
    out = format_llm_unavailable_marker("credit_exhausted")
    assert out == "⦿ synthèse indisponible (LLM · credit_exhausted)"


def test_format_canonical_rate_limited():
    out = format_llm_unavailable_marker("rate_limited")
    assert out == "⦿ synthèse indisponible (LLM · rate_limited)"


def test_format_custom_surface():
    """surface param permet de specialiser sans inventer."""
    out = format_llm_unavailable_marker("cost_cap_hard", surface="why_matters")
    assert out == "⦿ why_matters indisponible (LLM · cost_cap_hard)"


def test_format_reason_none_becomes_question_mark():
    """reason=None -> '?' (honnete sur l'inconnu, pas de fausse provenance)."""
    out = format_llm_unavailable_marker(None)
    assert "?" in out
    assert out == "⦿ synthèse indisponible (LLM · ?)"


def test_format_reason_empty_string_becomes_question_mark():
    out = format_llm_unavailable_marker("")
    assert out == "⦿ synthèse indisponible (LLM · ?)"


# ─── 2. Anti-prose defense (le ban absolu de la spec) ────────────────────


def test_marker_contains_no_verb_of_opinion():
    """Pas de 'pense', 'croit', 'estime', 'va revenir', etc. dans le marker."""
    banned_substrings = [
        "pense", "croit", "estime", "considere",
        "va revenir", "reviendra", "patientez", "attendez",
        "be back", "thinks", "believes", "will return",
        # Verbes d'analyse fake
        "selon le bot", "selon le copilot",
        "le bot reviendra", "le copilot reviendra",
    ]
    for reason in ("credit_exhausted", "rate_limited", "cost_cap_hard", None, ""):
        marker = format_llm_unavailable_marker(reason).lower()
        for banned in banned_substrings:
            assert banned.lower() not in marker, (
                f"Marker contient pattern interdit '{banned}' : {marker!r}"
            )


def test_marker_is_short():
    """Marker doit etre court (sec). >100 chars = soupcon de prose."""
    for reason in ("credit_exhausted", "rate_limited", "cost_cap_hard"):
        marker = format_llm_unavailable_marker(reason)
        assert len(marker) <= 80, f"Marker trop long ({len(marker)} chars) : {marker!r}"


def test_marker_has_single_label_then_provenance():
    """Structure : '⦿ <label> (LLM · <reason>)'. Une seule parenthese, pas
    de double phrase, pas de point milieu."""
    marker = format_llm_unavailable_marker("credit_exhausted")
    assert marker.count("(") == 1
    assert marker.count(")") == 1
    # Pas de '. ' (point + espace = phrase suivante = prose)
    assert ". " not in marker, f"Phrase de prose detectee dans marker : {marker!r}"


# ─── 3. is_synthesized_marker detection ──────────────────────────────────


def test_is_synthesized_marker_true_on_canonical_marker():
    marker = format_llm_unavailable_marker("credit_exhausted")
    assert is_synthesized_marker(marker) is True


def test_is_synthesized_marker_true_with_leading_whitespace():
    """Tolerance whitespace (rendu HTML peut indenter)."""
    assert is_synthesized_marker("   ⦿ synthèse indisponible (LLM · x)") is True


def test_is_synthesized_marker_false_on_normal_text():
    assert is_synthesized_marker("L'analyse montre une remontee de prix") is False
    assert is_synthesized_marker("NVDA: bullish 75%") is False
    assert is_synthesized_marker("") is False


# ─── 4. Rule fallback provenance marker ──────────────────────────────────


def test_rule_fallback_provenance_for_fallback_tag():
    out = format_rule_fallback_provenance("rule_v1_fallback")
    assert out == "⦿ rule_v1_fallback (déterministe, hors headline canonique)"


def test_rule_fallback_provenance_for_shadow_tag():
    out = format_rule_fallback_provenance("rule_v1_shadow")
    assert out == "⦿ rule_v1_shadow (déterministe, hors headline canonique)"


def test_rule_fallback_provenance_empty_for_canonical_tag():
    """v2 (canonical) ne porte pas de marker provenance -- c'est l'attendu."""
    assert format_rule_fallback_provenance("v2") == ""
    assert format_rule_fallback_provenance("v1") == ""
    assert format_rule_fallback_provenance("v0") == ""


def test_rule_fallback_provenance_empty_for_unknown_tag():
    """Defense vs futur tag mal route : marker vide plutot que faux marker."""
    assert format_rule_fallback_provenance("ensemble_v1") == ""
    assert format_rule_fallback_provenance("") == ""


# ─── 5. Consumers wired via source unique (pas de duplication) ──────────


def test_marker_prefix_is_centralized():
    """LLM_UNAVAILABLE_MARKER_PREFIX est la constante autorisee."""
    assert LLM_UNAVAILABLE_MARKER_PREFIX == "⦿"


def test_chat_py_uses_centralized_helper():
    """Le wire dashboard/chat.py doit importer format_llm_unavailable_marker
    (defense contre regression vers strings dupliquees)."""
    import inspect

    import dashboard.chat as _chat

    src = inspect.getsource(_chat)
    # Soit l'import, soit le nom d'usage doit etre present
    assert "format_llm_unavailable_marker" in src, (
        "dashboard/chat.py doit utiliser format_llm_unavailable_marker (source "
        "unique) -- pas de string '⦿' dupliquee."
    )


def test_analyze_py_uses_centralized_helper():
    """Idem pour intelligence/analyze.py."""
    import inspect

    import intelligence.analyze as _analyze

    src = inspect.getsource(_analyze)
    assert "format_llm_unavailable_marker" in src, (
        "intelligence/analyze.py doit utiliser format_llm_unavailable_marker."
    )


# ─── 6. Idempotence / round-trip ─────────────────────────────────────────


@pytest.mark.parametrize("reason", ["credit_exhausted", "rate_limited", "cost_cap_hard", None, ""])
def test_marker_is_idempotent(reason):
    """Format identique sur appels repetes (pas de timestamp ni randomness)."""
    a = format_llm_unavailable_marker(reason)
    b = format_llm_unavailable_marker(reason)
    assert a == b


def test_marker_round_trips_through_is_synthesized_check():
    """Tout marker genere doit etre detecte par is_synthesized_marker."""
    for reason in ("credit_exhausted", "rate_limited", None):
        for surface in ("synthèse", "why_matters", "narrative"):
            m = format_llm_unavailable_marker(reason, surface=surface)
            assert is_synthesized_marker(m), (
                f"Marker {m!r} non detecte par is_synthesized_marker (regression)"
            )
