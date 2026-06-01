"""Anti-regression guard for [[currency-native-invariant]] mix bugs.

Cf docs/LESSONS.md L12. Tout calcul `%` impliquant un prix-these
(`stop_price`, `target_full`, `target_partial`, `entry_price` -- NATIVE)
DOIT passer par un helper qui injecte `_cached_price_native`, jamais inline
avec `current_price_eur`.

Bug recurrent attrape 2 fois (4063.T cible +23876% 31/05 wave 9 dans
_theses, puis stop -11089% 01/06 dans _mauboussin_sizing). Filet de
securite : ce test fait fail si le pattern interdit reapparait.

Ce test est syntaxique (string match), pas semantique. Il accepte des
faux positifs (commentaires, docstrings) -- bandage volontaire pour ne
plus jamais re-attraper le bug, meme au prix d'une false alarm.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RENDER_PY = Path(__file__).resolve().parent.parent / "dashboard" / "render.py"

# Pattern banni : `current_price_eur` ou `current_eur` apparait dans la meme
# *expression* qu'un champ prix-these (stop/target/entry). On detecte sur la
# meme ligne pour minimiser les faux positifs (multiline trop large).
NATIVE_FIELDS = ("stop_price", "target_full", "target_partial", "entry_price")
EUR_FIELDS = ("current_price_eur", "current_eur")


def _scan_lines() -> list[tuple[int, str]]:
    text = RENDER_PY.read_text(encoding="utf-8")
    flagged: list[tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        # Skip pure comments + docstrings (begin with # ou triple quote ou
        # contains "Bug fix" -- les commentaires explicatifs n'executent pas).
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
            continue
        # Si une ligne ASSIGNE current_price_eur depuis un dict (ex
        # `"current_price_eur": ln.current_price_eur`), c'est legitime --
        # pas un mix dans une formule. On skip si pas d'operateur arithm.
        has_arith = any(op in line for op in ("-", "/", "*"))
        if not has_arith:
            continue
        has_eur = any(f in line for f in EUR_FIELDS)
        has_native = any(f in line for f in NATIVE_FIELDS)
        if has_eur and has_native:
            flagged.append((i, stripped))
    return flagged


def test_no_eur_native_mix_in_render():
    """Fail si une ligne de render.py mix current_price_eur avec stop_price /
    target_full / target_partial / entry_price dans une expression arithmetique.

    Cf docs/LESSONS.md L12 + memory `currency_native_render_helper`. Passer
    par `_stop_distance_pct_native()` ou un helper jumeau, jamais inline.
    """
    flagged = _scan_lines()
    assert not flagged, (
        "Mix EUR/native detecte dans dashboard/render.py (violation L12):\n"
        + "\n".join(f"  line {i}: {ln}" for i, ln in flagged)
        + "\n\nFix : utiliser _stop_distance_pct_native(tk, stop_price) ou "
        "extraire un helper jumeau (target_distance_pct_native, etc.)."
    )


def test_helper_canonique_existe():
    """Le helper `_stop_distance_pct_native` doit exister dans render.py.
    Si refactor le supprime, fail explicite (pas de regression silencieuse)."""
    text = RENDER_PY.read_text(encoding="utf-8")
    assert "def _stop_distance_pct_native(" in text, (
        "Helper canonique `_stop_distance_pct_native` introuvable dans "
        "dashboard/render.py. Cf [[currency-native-render-helper]] memory + "
        "docs/LESSONS.md L12. Ne pas supprimer sans extraire un jumeau qui "
        "consomme `_cached_price_native`."
    )


def test_asym_sentinel_target_hit():
    """`_asym_format()` doit traiter ratio>=999 comme sentinel TARGET_HIT
    et rendre un badge ('cible'), pas le nombre brut '999.0×'. Cf
    intelligence/asymmetry.py qui retourne 999.0 quand current >= target_full."""
    text = RENDER_PY.read_text(encoding="utf-8")
    # Cherche def _asym_format puis verifie qu'il a un branchement >=999
    m = re.search(r"def _asym_format\(.*?\n(.*?)(?=\ndef )", text, re.DOTALL)
    assert m, "_asym_format function not found in render.py"
    body = m.group(1)
    assert re.search(r"ratio\s*>=\s*999", body), (
        "_asym_format ne gere pas le sentinel `ratio >= 999` (TARGET_HIT). "
        "Cf intelligence/asymmetry.py ligne ~105. Sans ce branchement, "
        "l'affichage rend '999.0×' qui lit faux."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
