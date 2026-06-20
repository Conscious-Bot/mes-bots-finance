"""Runner : orchestre les 3 lentilles + format DEAD (N/3).

Triangulation strict :
- 1 lens KO  -> WATCH (a regarder)
- 2 lens KO  -> CANDIDATE (medium confidence)
- 3 lens KO  -> DEAD (haute confiance, candidat suppression)

Sortie : structure pour report.py (markdown backlog).

Aucune ecriture, aucune modification. Verdict = jamais. 'candidat pour
ton jugement' = TOUJOURS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import lens_decision, lens_runtime, lens_static


@dataclass
class TriangulatedFinding:
    """Synthese par symbole : combien de lentilles l'ont flag."""
    name: str                            # symbole / fichier / handler / source
    n_lenses: int                        # 1..3
    confidence_label: str                # WATCH | CANDIDATE | DEAD
    evidence: dict[str, str] = field(default_factory=dict)  # lens -> citation
    excluded: bool = False
    exclusion_reason: str | None = None


def _confidence_label(n: int) -> str:
    return {1: "WATCH", 2: "CANDIDATE", 3: "DEAD"}.get(n, "UNKNOWN")


def run(lenses: tuple[str, ...] = ("static", "runtime", "decision"),
        window_days: int = 90,
        targets: list[str] | None = None,
        vulture_min_confidence: int = 80) -> dict[str, Any]:
    """Lance les 3 lentilles, triangle les findings, retourne un dict riche.

    Args:
        lenses: subset a executer. Defaut = toutes.
        window_days: fenetre runtime + decision.
        targets: dirs/files pour lens statique. None = defaut.
        vulture_min_confidence: 80 par defaut.

    Returns:
        dict avec :
        - 'static', 'runtime', 'decision' : raw outputs de chaque lens
        - 'triangulated' : list[TriangulatedFinding] sorted by confidence DESC
        - 'summary' : counts par label
    """
    out: dict[str, Any] = {}

    if "static" in lenses:
        out["static"] = lens_static.scan(
            targets=targets, min_vulture_confidence=vulture_min_confidence
        )
    if "runtime" in lenses:
        out["runtime"] = lens_runtime.scan(window_days=window_days)
    if "decision" in lenses:
        out["decision"] = lens_decision.scan(window_days=window_days)

    # Triangulation par 'name' canonique
    by_name: dict[str, dict[str, str]] = {}
    excluded_map: dict[str, tuple[bool, str | None]] = {}

    for c in (out.get("static", {}).get("candidates_raw") or []):
        by_name.setdefault(c.name, {})["static"] = (
            f"[{c.tool}/{c.rule}] {c.file}:{c.line} ({c.confidence}%)"
        )
        if c.excluded:
            excluded_map[c.name] = (True, c.exclusion_reason)
    for c in (out.get("runtime", {}).get("handlers") or []):
        by_name.setdefault(c.name, {})["runtime"] = c.evidence
    for c in (out.get("runtime", {}).get("crons") or []):
        by_name.setdefault(c.name, {})["runtime"] = c.evidence
    for c in (out.get("decision", {}).get("sources") or []):
        by_name.setdefault(c.name, {})["decision"] = c.evidence
    for c in (out.get("decision", {}).get("tickers") or []):
        by_name.setdefault(c.name, {})["decision"] = c.evidence

    triangulated: list[TriangulatedFinding] = []
    for name, evidence in by_name.items():
        excluded, reason = excluded_map.get(name, (False, None))
        triangulated.append(TriangulatedFinding(
            name=name,
            n_lenses=len(evidence),
            confidence_label=_confidence_label(len(evidence)),
            evidence=evidence,
            excluded=excluded,
            exclusion_reason=reason,
        ))

    # Sort : DEAD first, then CANDIDATE, then WATCH ; excluded en bas
    triangulated.sort(key=lambda f: (
        0 if not f.excluded else 1,    # actifs avant exclus
        -f.n_lenses,                    # plus de lentilles = plus haut
        f.name,
    ))

    summary = {
        "DEAD": sum(1 for f in triangulated if f.n_lenses == 3 and not f.excluded),
        "CANDIDATE": sum(1 for f in triangulated if f.n_lenses == 2 and not f.excluded),
        "WATCH": sum(1 for f in triangulated if f.n_lenses == 1 and not f.excluded),
        "excluded": sum(1 for f in triangulated if f.excluded),
        "total_findings": len(triangulated),
    }

    out["triangulated"] = triangulated
    out["summary"] = summary
    out["meta"] = {
        "lenses_run": list(lenses),
        "window_days": window_days,
        "vulture_min_confidence": vulture_min_confidence,
        "targets": targets or ["dashboard/", "intelligence/", "shared/", "bot/"],
    }
    return out
