"""Tests SYNTHÈSE HEBDO (Format B) — guards + fail-closed, sans LLM ni DB live.

Cf docs/templates/weekly_synthesis_prompt.md §3 (guards) + mémoire spec.
Le LLM est injecté (llm_call=...) → tests déterministes, hermétiques.
"""
from intelligence import weekly_synthesis as ws

_PAYLOAD = {
    "book_context": "Book: 22 lignes détenues, cluster AI-compute ~60%.",
    "signals": [{"id": 1, "score": 4, "title": "t", "summary": "s"}],
    "reactions": [],
    "events": [{"date": "2026-08-05", "ticker": "INFN", "description": "Infineon earnings"}],
    "open_questions": "Q1 HBM contracté-vs-cyclique.",
    "n_material": 1,
}


# ─── Provenance guard ────────────────────────────────────────────────────────

def test_provenance_guard_flags_bare_number():
    out = ws._provenance_guard("Le FCF ressort à 784 M$ cette semaine.")
    assert "PROVENANCE" in out, "un chiffre significatif sans [#id] doit être flaggé"


def test_provenance_guard_passes_with_id():
    out = ws._provenance_guard("Le FCF ressort à 784 M$ [#1462] cette semaine.")
    assert "PROVENANCE" not in out, "un chiffre avec [#id] ne doit PAS être flaggé"


def test_provenance_guard_passes_with_print_tag():
    out = ws._provenance_guard("Azure +43% [print MSFT 2026-07-30].")
    assert "PROVENANCE" not in out


# ─── Fail-closed L15 ─────────────────────────────────────────────────────────

def test_render_fail_closed_empty_payload():
    assert "INDISPONIBLE" in ws.render_weekly({})


def test_render_fail_closed_empty_llm():
    out = ws.render_weekly(_PAYLOAD, llm_call=lambda _p: "")
    assert "INDISPONIBLE" in out, "réponse LLM vide → incident, jamais un essai fabriqué"


def test_render_fail_closed_llm_exception():
    def _boom(_p):
        raise RuntimeError("timeout enrich")
    out = ws.render_weekly(_PAYLOAD, llm_call=_boom)
    assert "INDISPONIBLE" in out and "timeout" in out


# ─── Render applique les guards ──────────────────────────────────────────────

def test_render_applies_provenance_guard():
    out = ws.render_weekly(_PAYLOAD, llm_call=lambda _p: "La marge atteint 76% sans source.")
    assert "PROVENANCE" in out, "le render doit passer la sortie LLM par le provenance guard"


def test_render_passes_payload_into_prompt():
    captured = {}
    def _capture(prompt):
        captured["p"] = prompt
        return "ok [#1]"
    ws.render_weekly(_PAYLOAD, llm_call=_capture)
    assert "book_context".upper() in captured["p"].upper()
    assert "Infineon earnings" in captured["p"], "les events déterministes doivent être dans le payload"
    assert "guide de voix" in captured["p"].lower(), "le contrat de style (template) doit être injecté verbatim"
