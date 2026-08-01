#!/usr/bin/env python3
"""Pre-commit : parse chaque YAML staged (yaml.safe_load_all).

Ferme la CLASSE d'erreur ScannerError — scalaire bloc `>` dans un mapping en
flux, prise 2× en une heure le 01/08 (2e occurrence = doctrine, règle LESSONS).
Une forme YAML malformée devient non-committable : mécanique, pas vigilance
(L27 — « j'écrirai toujours en bloc » est de la doctrine morte-née). La couche
SÉMANTIQUE (assumption_graph.py valide assumptions.yaml : types, références,
cycles, méta-règles, drills) chaîne naturellement derrière — c'est déjà un
exécutable à code de retour.

safe_load_all : gère les multi-documents (`---`). safe_load : jamais load()
(pas d'exécution de tags Python arbitraires).
"""
import sys

import yaml


def main(paths):
    rc = 0
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                list(yaml.safe_load_all(f))
        except yaml.YAMLError as e:
            print(f"YAML invalide (parse) : {p}\n  {e}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
