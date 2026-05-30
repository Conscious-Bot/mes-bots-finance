# Post #04 — version bilingue

*Français d'abord, English below. Le post est sur un sous-bug que le test régression a attrapé immédiatement. Pas de chute construite, c'est l'exemple le plus pur du pattern.*

---
---

## 🇫🇷 Le fix qui n'était pas un fix

*Quand le test que tu écris pour empêcher un bug attrape ton propre patch.*

---

Le bug était simple, le contexte court. Mon système avait deux variables pointant vers la même base de données : `DB_PATH` (chemin absolu) et `_DB_PATH` (chemin relatif au répertoire courant). Une moitié du code lisait l'une, l'autre moitié lisait l'autre. Tant que je travaillais depuis la racine du projet, les deux pointaient au même fichier et tout fonctionnait. Le jour où mes tests ont monkeypatché `_DB_PATH` vers une base temporaire pour s'isoler de la production, l'autre moitié du code a continué à lire `DB_PATH` — et a tranquillement écrit dans la base de production. Sans crash. Sans alerte. Juste un signal fantôme et une source créée en prod par accident, attrapés par hasard parce qu'un autre test a échoué.

Le diagnostic est sec : **deux sources de vérité pour la même chose = un bug structurel qui revient à chaque fois que quelqu'un en utilise une seule.**

J'écris le fix, évident à mes yeux. Un alias : `_DB_PATH = DB_PATH`. Maintenant les deux variables pointent au même objet, et un monkeypatch sur l'une propage à l'autre. Bug fermé.

Je ne commit pas. Avant ça, j'écris un test régression — exactement la discipline que la session avait codifiée dix fois. Le test fait deux choses : (1) vérifier que les deux variables pointent au même fichier au démarrage, (2) vérifier qu'un monkeypatch sur `DB_PATH` propage à `_DB_PATH`.

Le test 1 passe. Le test 2 échoue immédiatement.

Pourquoi ? Parce que `_DB_PATH = DB_PATH` en Python n'est pas un alias dynamique. C'est une copie de référence à un instant donné. Quand je remplace ensuite `DB_PATH` par une nouvelle valeur via `setattr`, l'attribut `DB_PATH` du module change, mais `_DB_PATH` continue de pointer vers l'ancien `DB_PATH`. L'alias est cosmétique. Le bug est intact.

Le fix n'était pas un fix.

---

J'avais passé la journée à coder un pattern : *« vérifier d'abord, conclure après »*. À chaque étape de l'arc principal, j'avais résisté à l'envie de conclure. À chaque étape, vérifier avait révélé un bug une couche plus profonde. À l'étape 9, j'avais appliqué ce même pattern à mon propre fix — et le test régression avait fait son travail. Le pattern marche. Y compris contre la personne qui l'écrit.

Je remplace l'alias statique par un `__getattr__` au niveau du module (Python 3.7+) qui résout `_DB_PATH` dynamiquement vers la valeur courante de `DB_PATH` à chaque accès. Cette fois, le monkeypatch propage. Le test 2 passe.

Ce qu'il faut voir n'est pas la subtilité Python. C'est la séquence. **Le test n'a pas été écrit pour attraper *ce* bug** — il a été écrit pour vérifier que la consolidation marchait. Et c'est précisément parce qu'il a été écrit avant le commit qu'il a attrapé un sous-bug que je ne soupçonnais pas. Si j'avais commit l'alias statique sans test et écrit le test seulement après *« pour vérifier que c'était bien fixé »*, le test aurait été écrit pour passer. C'est le piège classique : écrire les tests qui confirment ce qu'on croit avoir fait, pas ceux qui contestent.

---

La leçon n'est pas *« écrivez vos tests avant »*. C'est plus précis. Le test régression doit être écrit pour répondre à une question dont vous ne connaissez pas la réponse. Si vous écrivez le test en sachant ce qu'il va trouver, ce n'est pas un test, c'est une décoration. Le test 2 a passé pour moi parce que j'étais convaincu que `_DB_PATH = DB_PATH` était trivialement correct. Le test l'a contesté avant moi. C'est la seule différence qui compte.

Et c'est pour ça que ce sous-bug a sa place dans le narratif : non parce qu'il était subtil, mais parce qu'il a démontré que le pattern *« vérifier d'abord »* s'applique aussi au patch qui matérialise le pattern. Aucune exception. Y compris à dix heures du soir, après neuf itérations, quand on est sûr que cette fois c'est fini.

Cette fois-là, ça ne l'était pas.

---
---

## 🇬🇧 The Fix That Wasn't a Fix

*When the regression test you write to prevent one bug catches your own patch.*

---

The bug was simple, the context short. My system had two variables pointing at the same database: `DB_PATH` (absolute path) and `_DB_PATH` (path relative to the current directory). Half the code read one, the other half read the other. As long as I worked from the project root, both pointed at the same file and everything functioned. The day my tests monkeypatched `_DB_PATH` to a temporary database to isolate from production, the other half of the code kept reading `DB_PATH` — and quietly wrote to the production database. No crash. No alert. Just one ghost signal and a source created in prod by accident, caught by chance because *another* test failed.

The diagnosis is dry: **two sources of truth for the same thing = a structural bug that returns every time someone uses only one of them.**

I write the fix, obvious to me. An alias: `_DB_PATH = DB_PATH`. Now both variables point to the same object, and a monkeypatch on one will propagate to the other. Bug closed.

I don't commit. Before that, I write a regression test — exactly the discipline the session had codified ten times. The test does two things: (1) verify that both variables point to the same file at startup, (2) verify that a monkeypatch on `DB_PATH` propagates to `_DB_PATH`.

Test 1 passes. Test 2 fails immediately.

Why? Because `_DB_PATH = DB_PATH` in Python isn't a dynamic alias. It's a reference copy at one moment in time. When I later replace `DB_PATH` with a new value via `setattr`, the module's `DB_PATH` attribute changes, but `_DB_PATH` keeps pointing at the old `DB_PATH`. The alias is cosmetic. The bug is intact.

The fix wasn't a fix.

---

I'd spent the day coding a pattern: *"verify first, conclude after."* At every step of the main arc, I'd resisted the urge to conclude. At every step, verifying had revealed a bug one layer deeper. At step nine, I'd applied that same pattern to my own fix — and the regression test had done its job. The pattern works. Including against the person writing it.

I replace the static alias with a module-level `__getattr__` (Python 3.7+) that resolves `_DB_PATH` dynamically to the current value of `DB_PATH` on each access. This time, the monkeypatch propagates. Test 2 passes.

What you have to see isn't the Python subtlety. It's the sequence. **The test wasn't written to catch *that* bug** — it was written to verify the consolidation worked. And precisely because it was written before the commit, it caught a sub-bug I hadn't suspected. If I'd committed the static alias without the test and written the test afterward *"to verify it was indeed fixed"*, the test would have been written to pass. That's the classic trap: writing tests that confirm what you think you did, not ones that contest it.

---

The lesson isn't *"write your tests first."* It's more precise. The regression test has to be written to answer a question whose answer you don't know. If you write the test knowing what it will find, it's not a test, it's decoration. Test 2 passed for me because I was convinced `_DB_PATH = DB_PATH` was trivially correct. The test contested it before I did. That's the only difference that matters.

And that's why this sub-bug belongs in the narrative: not because it was subtle, but because it demonstrated that the *"verify first"* pattern applies even to the patch that materializes the pattern. No exceptions. Including at ten at night, after nine iterations, when you're sure this time it's done.

That time, it wasn't.
