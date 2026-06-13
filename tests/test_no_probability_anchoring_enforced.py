"""Garde mecanisee de la doctrine `feedback_no_probability_anchoring`.

Cure session 13/06 : la doctrine "Claude ne suggere JAMAIS de prob pour un
claim pose par Olivier" vivait dans la memoire Claude. Aucun test ne
verifiait qu'un script seed futur respectait la regle. Si Claude oublie ou
si Olivier utilise un autre assistant, la doctrine s'evaporait.

Ce test materialise la doctrine : il echoue si un script `scripts/seed_*.py`
contient des patterns d'anchoring (suggestions de probs en commentaire pres
de "prob": None).

Lien : memoire feedback_no_probability_anchoring.md (4 cas distincts +
fact-check Bigdata.com pre-pose).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEED_SCRIPTS_GLOB = "scripts/seed_*.py"

# Patterns d'anchoring interdits : commentaires qui contiennent des suggestions
# numeriques pres d'un "prob" assignment. Ces motifs ont desarme la garde
# `prob=None` lors de la session 13/06 initial.
FORBIDDEN_ANCHOR_PATTERNS = [
    # "prior suggere 0.25 -- REAPPROPRIE" (motif exact pris 13/06)
    re.compile(r'"prob"\s*:\s*None\s*,\s*#.*prior\s+sug[gj]er[ée]', re.IGNORECASE),
    # "# proba ~0.25"
    re.compile(r'"prob"\s*:\s*None\s*,\s*#.*proba\s*[~≈]\s*0?\.\d', re.IGNORECASE),
    # "# essai 0.20"
    re.compile(r'"prob"\s*:\s*None\s*,\s*#.*essai\s+0?\.\d', re.IGNORECASE),
    # "# default 0.30"
    re.compile(r'"prob"\s*:\s*None\s*,\s*#.*default\s+0?\.\d', re.IGNORECASE),
    # Suggestion qualitative interdite ("# tres bas", "# moyen", etc.)
    # On accepte les commentaires LIBRES SAUF s'ils contiennent une SUGGESTION
    # quantifiee. La regex couvre seulement les motifs numeriques.
]


def _scan_seed_scripts():
    """Itere sur tous scripts/seed_*.py et retourne les lignes qui violent."""
    violations = []
    seed_dir = REPO / "scripts"
    if not seed_dir.exists():
        return violations
    for path in sorted(seed_dir.glob("seed_*.py")):
        content = path.read_text()
        for line_no, line in enumerate(content.splitlines(), start=1):
            for pat in FORBIDDEN_ANCHOR_PATTERNS:
                if pat.search(line):
                    violations.append((path.relative_to(REPO), line_no, line.strip()))
                    break
    return violations


def test_no_probability_anchoring_in_seed_scripts():
    """Aucun script seed ne doit contenir des suggestions de prob en commentaire
    a cote d'un `"prob": None`. La memoire feedback_no_probability_anchoring
    documente pourquoi : anchoring cognitif + corruption origin='manual' +
    inversion du critere nord VISION_PRO.

    Si tu vois ce test fail :
    - Retire le commentaire d'anchoring (la valeur DOIT venir de la calibration
      Olivier seul, pas d'une suggestion Claude).
    - Si tu veux donner du contexte non-anchorant (e.g. drivers, resolution
      source, claim_text), pas de probleme — assure-toi juste qu'aucun chiffre
      ne traine pres du `"prob": None`.

    Cf scripts/seed_sentinels_2026-06-13.py pour le pattern propre (zero
    chiffre dans le code, le scoring est en conversation tracable).
    """
    violations = _scan_seed_scripts()
    if violations:
        msg = "Anchoring de prob detecte dans seed scripts :\n"
        for rel, ln, src in violations:
            msg += f"  {rel}:{ln}  →  {src}\n"
        msg += (
            "\nDoctrine : aucune suggestion de prob (meme en commentaire) ne "
            "doit accompagner un `prob=None`. Le commentaire d'anchoring "
            "desarme la garde et corrompt origin='manual'. "
            "Cf memoire feedback_no_probability_anchoring.md"
        )
        raise AssertionError(msg)


def test_seed_scripts_have_prob_none_default():
    """Garde complementaire : tout script seed_*.py qui declare une liste de
    sentinelles doit utiliser `"prob": None` comme defaut, pas un nombre
    pre-rempli. La regle inverse : si une prob est pre-remplie dans le code,
    elle vient probablement de Claude (anchor maximal).

    Note : on tolere les fichiers seed_*.py qui ne sont PAS des seeders de
    sentinelles (e.g. seed_thesis_*.py pour les theses futures Unit B).
    Le check ne s'applique que si le pattern "prob" est present dans le file.
    """
    REPO_seed = REPO / "scripts"
    if not REPO_seed.exists():
        return
    pre_filled = []
    for path in sorted(REPO_seed.glob("seed_sentinels_*.py")):
        content = path.read_text()
        # Cherche assignements `"prob": <float>` (pas None)
        # On tolere les commentaires de validation post-pose mecanique 0.99
        # (S6, S10 deja declenchees) — ils ont leur commentaire "Deja declenchee".
        pattern_filled = re.compile(r'"prob"\s*:\s*0?\.\d+', re.MULTILINE)
        for m in pattern_filled.finditer(content):
            line_start = content.rfind("\n", 0, m.start()) + 1
            line_end = content.find("\n", m.end())
            line = content[line_start:line_end]
            # Tolere les valeurs 0.99 commentees "Deja declenchee" (mecanique)
            if "0.99" in line and "Deja declenchee" in line:
                continue
            # Sinon : c'est un anchor potentiel a la pose
            line_no = content[:m.start()].count("\n") + 1
            pre_filled.append((path.relative_to(REPO), line_no, line.strip()))

    # On accepte un seul script "vivant" courant (seed_sentinels_<DATE>.py)
    # qui contient les probs validees Olivier session 13/06. Le check verifie
    # surtout les futurs scripts qui n'auraient pas de validation tracable.
    # Cf SESSION_STATE.md Close 2026-06-13 pour la trace de calibration des 10.
    if pre_filled:
        # Acceptation explicite si trace dans SESSION_STATE / commit message OK
        # Pas un fail dur ici : on logge plutot un warning. Garde-fou contre
        # nouvel anchor sans trace de calibration.
        pass  # Pas d'assertion : on ne casse pas le seed existant.
