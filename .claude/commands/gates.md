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

La commande mypy est LA MÊME que le job CI (`.github/workflows/ci.yml`) — parité
locale↔CI stricte, plus de surprise « vert en local, rouge en CI » (cure 04/07).

```bash
source venv/bin/activate && \
echo "=== G1 ruff (strict 0) ===" && ruff check . 2>&1 | tail -5 && \
echo "=== G2 mypy (strict-typed modules = commande CI exacte) ===" && \
  mypy shared/math_helpers.py shared/storage.py shared/llm.py shared/edgar.py shared/prices.py shared/notify.py shared/config.py \
       shared/crypto.py shared/echo.py shared/embeddings.py shared/macro.py shared/data_source_base.py \
       data_sources/gmail_.py \
       intelligence/learning.py intelligence/materiality_v2.py intelligence/asymmetry.py intelligence/digest.py \
       intelligence/journal.py intelligence/credibility.py intelligence/bias_tagger.py intelligence/signal_classify.py \
       intelligence/materiality_boost.py intelligence/half_life.py intelligence/regime.py \
       intelligence/calendar.py intelligence/analyze.py intelligence/thesis.py \
       risk/risk_engine.py risk/sizing.py \
       --follow-imports=silent 2>&1 | tail -5 && \
echo "=== G3 pytest full suite ===" && pytest -q --tb=no 2>&1 | tail -3 && \
echo "=== G4 dashboard regen smoke ===" && PYTHONPATH=. python3 -c "from dashboard.render import render; render(); print('regen OK')" 2>&1 | tail -1 && \
echo "=== G5 git status (working tree sain ?) ===" && git status --short
```

## Lecture du verdict

- **G1 ruff** : `All checks passed!` attendu. La baseline est à ZÉRO (les 8
  préexistants task #33 ont été résorbés) — toute erreur = introduite par la
  session courante, à fixer avant commit. Plus de tolérance « N==8 ».
- **G2 mypy** : `Success: no issues found` sur les modules strict-typed. C'est la
  gate CI — si elle casse, la CI cassera aussi. `note: unused section(s)` est
  informatif (pyproject overrides non atteints), pas un échec.
- **G3 pytest** : doit dire `N passed` sans `failed`. Attention : les tests
  `live_book`/`live_data` lisent `data/bot.db` et peuvent être rouges sur dette
  d'état du book (ex. thèse orpheline) sans que ce soit ta régression — vérifier
  que le fail est bien un `live_*` orthogonal avant de s'alarmer. La CI, elle,
  skippe ces marqueurs (`-m "not slow and not live_data"`).
- **G4 regen** : `regen OK` = `dashboard/render.py` charge sans exception + écrit
  `dashboard.html`. Smoke important si tu viens de toucher un panneau.
- **G5 git status** : working tree doit refléter SEULEMENT les fichiers que tu
  viens de toucher consciemment. Si fichier inattendu → investigue avant commit.

## Anti-pattern

- Lancer les gates individuellement par habitude → friction qui finit par être skipée → régression atterrit en main.
- Commit "ça marche en local" sans avoir lancé /gates → 2 fails atterrissent au prochain pull → re-débuggage.

## Référence

- Pattern 5-gates dans `CLAUDE.md` § "Discipline non négociable" : *"gates chaînées `&&` (`ruff` + `import` + serve reload) après chaque patch"*.
- Ruff : baseline 0 (task #33 résorbée). Parité mypy local↔CI établie 04/07.
