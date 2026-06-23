"""Lentille doctrine : code vs ADR + LESSONS L1-L25 + QUALITY_BAR.

Audit les violations canoniques que les outils statiques generiques ne
detectent pas : regles textuelles enoncees dans docs, dont le code peut
silencieusement deriver.

MVP rules (haute signal, faible bruit) :
- L15 fail-closed : 'return 0.5' / faux probabilites dans contexte scorer
- L12 native vs EUR : mixing _native + _eur dans meme expression
- ADR 014 canonical_predictions_filter : raw SQL 'FROM predictions WHERE'
  sans canonical_predictions_filter()
- L7 side-effect in helper : register_concept inside helper function
- L25 canonical drift : SPEC sans Implementation Status footer

ZERO ECRITURE. Pattern matching deterministe + heuristique low-fp.
Chaque match porte sa citation textuelle de la regle violee.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DoctrineCandidate:
    """Une violation potentielle d'une regle doctrine canonique."""
    rule_id: str               # L15 | L12 | ADR014 | L7 | L25
    rule_text: str             # citation textuelle de la regle
    file: str                  # chemin relatif
    line: int                  # ligne du match
    excerpt: str               # extrait code/texte qui matche
    confidence: int            # 50-95 (jamais 100 : doctrine est interpretable)


def _scan_file_lines(path: Path) -> list[tuple[int, str]]:
    """Retourne (line_no, line_text) pour chaque ligne du fichier."""
    try:
        return [(i + 1, line) for i, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines()
        )]
    except OSError:
        return []


def check_l15_fail_closed(targets: list[str]) -> list[DoctrineCandidate]:
    """L15 : Fail-closed scoring : pas de score arbitraire en mode degrade.

    Pattern : 'return 0.5' / 'return 0.0' dans fichiers scoring (signal_scorer*,
    *probability*, *prob_*). Fail-closed exige return None si donnee insuffisante,
    pas un nombre fabrique.
    """
    out: list[DoctrineCandidate] = []
    rule_text = (
        "L15 : `signal_scorer_v2` retourne None plutot que de fabriquer une proba "
        "en mode degrade. Source : docs/LESSONS.md §L15."
    )
    pat = re.compile(r"\breturn\s+0\.[05]\b|\breturn\s+0\.\d+\s*#.*proba")
    scoring_re = re.compile(r"scorer|probabili|estimate_prob", re.IGNORECASE)
    for target in targets:
        for path in Path(target).rglob("*.py"):
            if not scoring_re.search(path.name):
                continue
            for line_no, line in _scan_file_lines(path):
                if pat.search(line):
                    out.append(DoctrineCandidate(
                        rule_id="L15",
                        rule_text=rule_text,
                        file=str(path),
                        line=line_no,
                        excerpt=line.strip()[:120],
                        confidence=75,
                    ))
    return out


def check_l12_native_eur_mix(targets: list[str]) -> list[DoctrineCandidate]:
    """L12 : Native vs EUR : interdit melanger dans une formule de %.

    Pattern strict : meme ligne contient '_native' ET '_eur' AVEC un contexte
    pourcentage (% ou _pct ou .pct ou * 100 / division). Conversions legitimes
    (value_eur = qty * price_native * fx) sont exclues : c'est de l'arithmetique
    de change, pas un % qui mixerait deux reperes.
    """
    out: list[DoctrineCandidate] = []
    rule_text = (
        "L12 : Native (USD/JPY/KRW) et EUR ne se melangent JAMAIS dans une "
        "formule de % (P&L, downside, asym...). Source : docs/LESSONS.md §L12, "
        "memory currency_native_invariant."
    )
    # Contexte % : explicite '%' / 'pct' / '_pct' / division avec * 100
    pct_re = re.compile(r"%|pct\b|_pct\b|\.pct\b|\*\s*100\b|asymmetry|downside|upside")
    for target in targets:
        for path in Path(target).rglob("*.py"):
            for line_no, line in _scan_file_lines(path):
                lower = line.lower()
                if "_native" not in lower or "_eur" not in lower:
                    continue
                if not pct_re.search(lower):
                    continue
                stripped = line.lstrip()
                if stripped.startswith(("#", '"')):
                    continue
                out.append(DoctrineCandidate(
                    rule_id="L12",
                    rule_text=rule_text,
                    file=str(path),
                    line=line_no,
                    excerpt=line.strip()[:120],
                    confidence=70,
                ))
    return out


def check_adr014_canonical_filter(targets: list[str]) -> list[DoctrineCandidate]:
    """ADR 014 : queries sur 'predictions' doivent utiliser canonical_predictions_filter().

    Pattern : raw SQL 'FROM predictions' SANS appel a un filter canonical/substance
    dans le voisinage immediat (5 lignes apres). Accepte les 2 variantes :
    - canonical_predictions_filter (strict v2 only, ADR 014)
    - substance_predictions_filter (variant equivalent, certaines queries
      historiques pre-014 l'utilisent par convention)
    """
    out: list[DoctrineCandidate] = []
    rule_text = (
        "ADR 014 : toute query SQL sur predictions canoniques DOIT utiliser "
        "canonical_predictions_filter() (ou substance_predictions_filter variant) "
        "pour exclure v0/v1/rule_v1_*. Source : docs/adrs/014-canonical-predictions-filter.md."
    )
    from_pat = re.compile(r"FROM\s+predictions\b", re.IGNORECASE)
    filter_pat = re.compile(r"(canonical|substance)_predictions_filter")
    # Patterns intentionnels exempts (ne pas flagger comme violation) :
    # - cohort selection explicite (v0/v1/v2 literal)
    # - methodology_version parametrise (intent : caller decide la version)
    # - by-id accessor (WHERE id=? ou WHERE p.id=?)
    # - bootstrap library qui indexe ALL predictions intentionnellement
    intentional_re = re.compile(
        r"methodology_version\s*(?:!=|=)\s*['\"](v0|v1|v2)['\"]"
        r"|methodology_version\s*=\s*\?"
        r"|WHERE\s+id\s*=\s*\?"
        r"|WHERE\s+p\.id\s*="
        r"|_loop_filter|_loop_filter_substance"  # render.py:4785 multi-line WHERE applique le filter
        r"|ADR014-EXEMPT"  # pragma comment pour exemption explicite (cf docs/adrs/014)
    )
    for target in targets:
        for path in Path(target).rglob("*.py"):
            # Skip tests (fixtures peuvent legitimement query toutes les preds)
            if "/tests/" in str(path) or path.name.startswith("test_"):
                continue
            # Skip migration files (alembic) et schema dumps
            if "alembic" in str(path):
                continue
            lines = _scan_file_lines(path)
            for i, (line_no, line) in enumerate(lines):
                if not from_pat.search(line):
                    continue
                # Look in window [i-8, i+10] for a filter call. Window widened
                # apres faux positifs (filter assigne via .replace() 5+ lignes
                # avant ou applique 8+ lignes plus bas dans multi-line SQL).
                start = max(0, i - 8)
                end = min(len(lines), i + 10)
                window = "\n".join(ln for _, ln in lines[start:end])
                if filter_pat.search(window):
                    continue  # filter present dans le voisinage, OK
                if intentional_re.search(window):
                    continue  # intentional cohort/by-id/library, exempt
                out.append(DoctrineCandidate(
                    rule_id="ADR014",
                    rule_text=rule_text,
                    file=str(path),
                    line=line_no,
                    excerpt=line.strip()[:120],
                    confidence=80,
                ))
    return out


def check_l7_helper_side_effect(targets: list[str]) -> list[DoctrineCandidate]:
    """L7 / memory feedback_helper_register_no_side_effect : helpers stateless
    NE doivent PAS register_concept dans la fn elle-meme.

    Pattern strict : un CALL effectif 'register_concept(' (parenthese open
    immediate, pas just import / comment / def def). Skip self-def dans
    living_graph.py (legit la fn elle-meme).
    """
    out: list[DoctrineCandidate] = []
    rule_text = (
        "L7 : helpers stateless ne register_concept JAMAIS dans la fn. Side-effect "
        "telemetry = consumer en prod, pas helper (pollue fixtures tests). "
        "Source : memory feedback_helper_register_no_side_effect."
    )
    call_re = re.compile(r"\bregister_concept\s*\(")
    # Markers qui indiquent que le register est INTENTIONAL (LIVING_GRAPH seed,
    # canonical source declaree). Skip ces cas (faux positifs du raw pattern).
    intentional_re = re.compile(
        r"LIVING[ _]GRAPH|canonique|canonical|seed|fork[ _-]detection|"
        r"tracer.bullet|compute.once|point unique|source unique",
        re.IGNORECASE,
    )
    for target in targets:
        for path in Path(target).rglob("*.py"):
            if "/tests/" in str(path):
                continue
            # Skip living_graph.py : la def elle-meme + son test-friendly stub
            if path.name == "living_graph.py":
                continue
            lines = _scan_file_lines(path)
            in_fn: int | None = None
            saw_commit = False
            for i, (line_no, line) in enumerate(lines):
                stripped = line.lstrip()
                # Skip imports + comments + docstrings (not actionable calls)
                if stripped.startswith(("import ", "from ", "#", '"""', "'''", '"')):
                    continue
                if stripped.startswith("def ") and not stripped.startswith("def __"):
                    in_fn = line_no
                    saw_commit = False
                if in_fn is not None:
                    if ".commit()" in line or "cx.commit" in line:
                        saw_commit = True
                    if call_re.search(line) and not saw_commit:
                        # Inspect 15 lignes precedentes : si marker 'intentional' present,
                        # c'est un seed canonical -> skip (legitime). Widened de 8 a 15
                        # apres faux positifs sur render.py (canonique mentionne 12 lignes
                        # avant le call_re).
                        ctx_start = max(0, i - 15)
                        ctx = "\n".join(ln for _, ln in lines[ctx_start:i])
                        if intentional_re.search(ctx):
                            in_fn = None
                            continue
                        out.append(DoctrineCandidate(
                            rule_id="L7",
                            rule_text=rule_text,
                            file=str(path),
                            line=line_no,
                            excerpt=line.strip()[:120],
                            confidence=65,
                        ))
                        in_fn = None  # 1 finding per fn
    return out


def check_l25_spec_footer(docs_root: Path = Path("docs")) -> list[DoctrineCandidate]:
    """L25 : SPECs doivent porter un footer 'Implementation Status'.

    Pattern : tout fichier SPEC_*.md dans docs/ sans la string
    'Implementation Status' dans son contenu.
    """
    out: list[DoctrineCandidate] = []
    rule_text = (
        "L25 : Tout SPEC_*.md doit porter un footer 'Implementation Status' pour "
        "fermer la classe (canonique grave != applique). Source : docs/LESSONS.md §L25."
    )
    if not docs_root.exists():
        return out
    for path in docs_root.rglob("SPEC_*.md"):
        content = path.read_text(encoding="utf-8", errors="ignore")
        if "Implementation Status" not in content and "IMPLEMENTATION STATUS" not in content:
            out.append(DoctrineCandidate(
                rule_id="L25",
                rule_text=rule_text,
                file=str(path),
                line=1,
                excerpt=f"SPEC sans footer 'Implementation Status' ({len(content)} chars).",
                confidence=95,
            ))
    return out


def scan(targets: list[str] | None = None) -> dict[str, Any]:
    """Lance les 5 checks MVP doctrine.

    Defaults : dashboard/ intelligence/ shared/ bot/.
    """
    if targets is None:
        targets = ["dashboard/", "intelligence/", "shared/", "bot/"]
    all_findings: list[DoctrineCandidate] = []
    all_findings.extend(check_l15_fail_closed(targets))
    all_findings.extend(check_l12_native_eur_mix(targets))
    all_findings.extend(check_adr014_canonical_filter(targets))
    all_findings.extend(check_l7_helper_side_effect(targets))
    all_findings.extend(check_l25_spec_footer(Path("docs")))
    by_rule: dict[str, list[DoctrineCandidate]] = {}
    for f in all_findings:
        by_rule.setdefault(f.rule_id, []).append(f)
    return {
        "candidates_raw": all_findings,
        "by_rule": by_rule,
        "n_total": len(all_findings),
        "n_by_rule": {k: len(v) for k, v in by_rule.items()},
    }
