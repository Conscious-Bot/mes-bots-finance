---
description: Passe les gates qualité en une commande (ruff + mypy + pytest + smoke render)
---

# /gates — Suite 5-gates en un run

**Pourquoi** : éviter la friction de lancer ruff / mypy / pytest / dashboard regen séparément à chaque fin de chantier. Une commande, un verdict.

**Quand l'invoquer** :
- Avant tout commit substantiel (chantier > 1 fichier touché)
- Avant tout `/close` de fin de session
- Après un audit de cleanup pour vérifier l'état final

## Exécuter

```bash
source venv/bin/activate && \
echo "=== G1 ruff ===" && ruff check . 2>&1 | tail -5 && \
echo "=== G2 mypy (best-effort, gate non-bloquant) ===" && (command -v mypy >/dev/null && mypy intelligence/ shared/storage.py 2>&1 | tail -5 || echo "mypy not installed / not configured -- skip") && \
echo "=== G3 pytest full suite ===" && pytest -q --tb=no 2>&1 | tail -3 && \
echo "=== G4 dashboard regen smoke ===" && PYTHONPATH=. python3 -c "from dashboard.render import render; render(); print('regen OK')" 2>&1 | tail -1 && \
echo "=== G5 git status (working tree sain ?) ===" && git status --short
```

## Lecture du verdict

- **G1 ruff** : `Found N errors` accepté si N == 8 (préexistants documentés cf task #33 backlog). Plus que 8 = nouveau ajouté par la session courante → fixer avant commit.
- **G2 mypy** : non bloquant aujourd'hui (gate absent dans le projet — task #33). À activer dès qu'on touche intelligence/* ou shared/storage.py sérieusement.
- **G3 pytest** : doit dire `N passed` sans `failed`. Si rouge → STOP, fix avant tout commit.
- **G4 regen** : `regen OK` = `dashboard/render.py` charge sans exception + écrit `dashboard.html`. Smoke important si tu viens de toucher un panneau.
- **G5 git status** : working tree doit refléter SEULEMENT les fichiers que tu viens de toucher consciemment. Si fichier inattendu → investigue avant commit.

## Anti-pattern

- Lancer les gates individuellement par habitude → friction qui finit par être skipée → régression atterrit en main.
- Commit "ça marche en local" sans avoir lancé /gates → 2 fails atterrissent au prochain pull → re-débuggage.

## Référence

- Pattern 5-gates dans `CLAUDE.md` § "Discipline non négociable" : *"gates chaînées `&&` (`ruff` + `import` + serve reload) après chaque patch"*.
- État ruff résiduel : `docs/LESSONS.md` mention task #33 (8 préexistants placeholder vars dashboard/render.py panel inachevé).
