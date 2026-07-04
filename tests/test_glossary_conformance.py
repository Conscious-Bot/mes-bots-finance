"""Conformité vocabulaire canonique — le dashboard rend les labels du GLOSSARY.

docs/GLOSSARY.md (figé v1.0) + memory glossaire_canonique : toute surface
user-facing utilise les 5 axes FR (Solidité/Pari/Doublon/Santé/Calibrage), pas le
jargon ancien (T1/T2/star/cluster cap/edge/overlaps/other bets). Source unique des
labels = _DIM_LABELS (render.py). Ce test attrape la RE-dérive (doctrine L29 :
chaque surface diffuse le canonique, aucune ne rebypasse — la classe, pas
l'instance). Source-read : pas de DB, CI-safe.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = Path("dashboard/render.py").read_text()

# Jargon banni des LABELS RENDUS (pas des commentaires/docstrings ni des clés
# internes type quality_T1_plus). On matche les segments de texte dans les
# f-strings de rendu : entre > et < , ou dans un data-tip/title, hors #comment.
_BANNED_LABELS = [
    "Other bets target",       # → « Autres paris — cible »
    "Overlaps seen by prices",  # → « Doublons — vus par les prix »
    ">Overlaps<",
    "Chokepoint",              # → Incontournable
    ">Franchise<",             # → Solide
]


def _rendered_lines() -> list[str]:
    """Lignes qui produisent du HTML rendu (contiennent une balise), hors
    lignes de commentaire pur."""
    out = []
    for ln in _SRC.splitlines():
        stripped = ln.lstrip()
        if stripped.startswith("#"):
            continue
        if "<" in ln and ">" in ln:
            out.append(ln)
    return out


def test_no_old_jargon_in_rendered_labels():
    rendered = "\n".join(_rendered_lines())
    hits = [b for b in _BANNED_LABELS if b in rendered]
    assert not hits, (
        f"Jargon ancien réapparu dans des labels rendus : {hits}. "
        "Utiliser le vocabulaire canonique (docs/GLOSSARY.md + _DIM_LABELS) : "
        "Doublons / Autres paris / Solidité / Pari principal / Santé / Calibrage."
    )


def test_dim_labels_are_canonical_fr():
    """La source unique _DIM_LABELS porte les 5 axes FR canoniques."""
    # extrait le bloc _DIM_LABELS = { ... }
    m = re.search(r"_DIM_LABELS = \{(.+?)\n\}", _SRC, re.DOTALL)
    assert m, "_DIM_LABELS introuvable (source unique des labels d'axes)"
    block = m.group(1)
    for canonical in ("Solidité haute", "Doublons", "Autres paris", "Calibrage",
                      "Pari principal", "Santé"):
        assert canonical in block, f"axe canonique absent de _DIM_LABELS : {canonical}"
    # le jargon ancien ne doit PAS être une valeur de label
    for old in ('"High solidity"', '"Overlaps"', '"Other bets"', '"Bet principal"'):
        assert old not in block, f"label d'axe non-canonique dans _DIM_LABELS : {old}"


def test_calibration_collision_resolved():
    """« Calibration » (scoring) et « Calibrage » (axe sizing) ne se recroisent
    plus — désambiguïsation figée du GLOSSARY. L'axe sizing = 'Calibrage' dans
    _DIM_LABELS ; 'Calibration' ne subsiste que pour le scorer V2."""
    m = re.search(r"_DIM_LABELS = \{(.+?)\n\}", _SRC, re.DOTALL)
    block = m.group(1) if m else ""
    assert "Calibrage" in block
    assert "Calibration" not in block, (
        "l'axe sizing doit être 'Calibrage', pas 'Calibration' (collision GLOSSARY)"
    )
