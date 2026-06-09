"""Audit canonical drift : suivi des SPEC_*.md (gravé != appliqué).

L25 LESSONS — un canonique gravé sans mécanisme de suivi devient un objet
mort. Ce script reporte pour chaque SPEC_*.md :
  - présence du footer "Implementation Status"
  - état déclaré (NOT_STARTED / IN_PROGRESS / IMPLEMENTED / DRIFTED)
  - existence des fichiers cibles déclarés
  - nombre de références dans le code (.py)
  - candidats doublons (titres synonymes)

Exit code :
  0 si tout SPEC a footer + fichiers cibles existants (si état IMPLEMENTED)
  1 si au moins un SPEC sans footer Implementation Status
  2 si IMPLEMENTED déclaré mais fichiers cibles absents (drift indicator)

Intégration /close : rituel de clôture appelle ce script en sortie pour
verrouiller "graver implique suivre" (cf docs/LESSONS.md L25).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Synonymes utilisés pour détecter doublons (cf L25 cas fondateur : LINK/LIAISON,
# TAXONOMY/PROFILES). Ajout libre — si deux SPECs partagent un mot, signal.
_SYNONYM_GROUPS: list[set[str]] = [
    {"link", "liaison", "binding", "wire"},
    {"taxonomy", "profile", "profiles", "category"},
    {"vocabulary", "lexicon", "ontology"},
    {"ledger", "journal", "log"},
    {"consensus", "agreement"},
]

# États reconnus dans le footer (case-insensitive match).
_VALID_STATES = {"NOT_STARTED", "NON COMMENCÉE", "IN_PROGRESS", "EN COURS",
                 "IMPLEMENTED", "IMPLÉMENTÉE", "DRIFTED"}


def _parse_footer(text: str) -> dict | None:
    """Extract Implementation Status footer fields. Return None si absent."""
    m = re.search(r"##\s*\d+\.\s*Implementation Status\s*\n(.*?)(?:\n##|\Z)",
                  text, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    body = m.group(1)
    fields = {}
    for line in body.splitlines():
        match = re.match(r"\s*-\s*\*\*([^*]+)\*\*\s*:\s*(.+)", line)
        if match:
            key = match.group(1).strip().lower()
            val = match.group(2).strip()
            fields[key] = val
    return fields


def _parse_target_files(field_value: str) -> list[tuple[str, bool]]:
    """Parse 'Fichiers cibles' field → list of (path, already_exists_per_doc).

    'à créer' = pas encore créé (pas un drift si état NOT_STARTED).
    'à refactor' / 'à étendre' = existe et touché.
    Sinon = existe (canonical owner).
    """
    out = []
    # Split on `,` ou `;`
    parts = re.split(r"[;,]", field_value)
    for raw in parts:
        raw = raw.strip()
        # Extract backtick'd path
        path_match = re.search(r"`([^`]+)`", raw)
        if not path_match:
            continue
        path = path_match.group(1)
        annotation = raw.lower()
        already_exists = "à créer" not in annotation
        out.append((path, already_exists))
    return out


def _count_code_refs(spec_basename: str) -> int:
    """Count .py files which reference the SPEC by basename or path."""
    needle = spec_basename
    n = 0
    for py in _REPO_ROOT.rglob("*.py"):
        rel = str(py.relative_to(_REPO_ROOT))
        if any(p in rel for p in ("venv/", "__pycache__/", ".git/", "tests/")):
            continue
        try:
            content = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if needle in content:
            n += 1
    return n


def _detect_duplicates(specs: list[Path]) -> list[tuple[str, str, str]]:
    """Return list of (spec_a, spec_b, shared_concept) for synonym overlaps."""
    out = []
    names = [(s.stem.lower().replace("spec_", ""), s.name) for s in specs]
    for i, (tokens_a, name_a) in enumerate(names):
        words_a = set(re.split(r"_+", tokens_a))
        for tokens_b, name_b in names[i + 1:]:
            words_b = set(re.split(r"_+", tokens_b))
            for group in _SYNONYM_GROUPS:
                hits_a = words_a & group
                hits_b = words_b & group
                if hits_a and hits_b and hits_a != hits_b:
                    concept = " / ".join(sorted(hits_a | hits_b))
                    out.append((name_a, name_b, concept))
    return out


def audit() -> int:
    specs = sorted(_REPO_ROOT.glob("SPEC_*.md"))
    if not specs:
        print("Aucun SPEC_*.md trouve a la racine.")
        return 0

    print(f"=== Audit canonical drift @ {len(specs)} SPECs ===\n")

    n_missing_footer = 0
    n_drifted = 0
    rows = []

    for spec in specs:
        text = spec.read_text(encoding="utf-8", errors="ignore")
        footer = _parse_footer(text)
        refs = _count_code_refs(spec.name)

        if footer is None:
            rows.append({
                "spec": spec.name,
                "footer": "ABSENT",
                "state": "?",
                "targets_ok": "?",
                "code_refs": refs,
                "drift": False,
            })
            n_missing_footer += 1
            continue

        state_raw = footer.get("implémentation") or footer.get("implementation") or "?"
        state_norm = state_raw.upper()
        targets_raw = footer.get("fichiers cibles") or footer.get("target files") or ""
        targets = _parse_target_files(targets_raw)
        # Drift : si état IMPLEMENTED mais fichiers cibles absents.
        drifted = False
        targets_status = []
        for path, should_exist in targets:
            full = _REPO_ROOT / path
            exists = full.exists()
            targets_status.append((path, exists, should_exist))
            if should_exist and not exists:
                drifted = True
        if "IMPLEMENTED" in state_norm or "IMPLÉMENTÉ" in state_norm:
            if any(not e for _, e, should in targets_status if should):
                drifted = True
        if drifted:
            n_drifted += 1

        rows.append({
            "spec": spec.name,
            "footer": "OK",
            "state": state_raw[:30],
            "targets_ok": f"{sum(1 for _, e, s in targets_status if e or not s)}/{len(targets_status)}" if targets_status else "n/a",
            "code_refs": refs,
            "drift": drifted,
        })

    # Render table
    print(f"{'SPEC':<40} {'Footer':<8} {'État':<30} {'Cibles':<8} {'Refs':<6} {'Drift':<6}")
    print("-" * 100)
    for r in rows:
        flag = "DRIFT" if r["drift"] else ""
        print(f"{r['spec']:<40} {r['footer']:<8} {r['state']:<30} {r['targets_ok']:<8} {r['code_refs']:<6} {flag:<6}")

    # Duplicate detection
    dupes = _detect_duplicates(specs)
    if dupes:
        print("\n=== Doublons candidats (concepts synonymes partagés) ===")
        for a, b, concept in dupes:
            print(f"  {a} <-> {b}  [{concept}]")
    else:
        print("\nAucun doublon candidat detecte.")

    # Summary
    print(f"\n=== Récap ===")
    print(f"  SPECs total            : {len(specs)}")
    print(f"  Sans footer Impl Status: {n_missing_footer} (= dette doctrinale)")
    print(f"  Drift detecte          : {n_drifted}")
    print(f"  Orphelins (refs=0)     : {sum(1 for r in rows if r['code_refs'] == 0)}")

    if n_missing_footer > 0:
        print(f"\nFAIL : {n_missing_footer} SPEC(s) sans footer Implementation Status.")
        print("Ajoute la section '## N. Implementation Status' avec : Gravé, Implémentation, Fichiers cibles, Prochain step.")
        return 1
    if n_drifted > 0:
        print(f"\nWARN : {n_drifted} SPEC(s) drifted (IMPLEMENTED declare mais cible absente).")
        return 2
    print(f"\nOK : tous les SPECs ont footer + cibles consistantes.")
    return 0


if __name__ == "__main__":
    sys.exit(audit())
