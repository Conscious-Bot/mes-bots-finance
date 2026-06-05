# Post #06 — Trois jours de CI rouge invisible

**Drafted: 2026-06-05** · commit `d3b23bf` · à sceller avec git tag `publish-post-06-YYYYMMDD` après relecture.

*Français. Un debug, une leçon — pas un récit d'alpha. La discipline qui ne se voit pas quand elle marche.*

---

## Trois jours de CI rouge invisible

J'ai pushé 25 commits hier. Le CI était rouge depuis trois jours. Je ne l'avais pas vu.

Pas par négligence ostentatoire. Par le mécanisme classique : Github affiche une coche verte ou un X rouge en haut à droite d'une page que je ne consulte pas. Je push, je passe au commit suivant. Personne ne m'a interrompu. Le X rouge ne fait pas de bruit.

Quand je l'ai enfin regardé, le diagnostic a pris quatre minutes. Le fix, dix lignes.

---

Un test précis échouait. Un seul, sur 943. Et — c'est la partie qui m'a accroché — il **passait quand je le lançais tout seul**. Solo, vert. En suite complète, rouge. Tous les jours, déterministe.

Ce pattern a un nom dans la profession : *test pollution*. Un autre test, plus haut dans l'ordre alphabétique, fait quelque chose qui change l'état global de l'interpréteur Python d'une façon que mon test ne tolère pas. Et comme les tests qui *passent* sont silencieux, l'ordre de pollution n'est pas évident à reconstituer.

Le test vérifiait qu'un log d'erreur est bien émis quand on essaie d'enregistrer une prédiction avec une méthodologie non documentée. C'est une vérification de garde-fou : si quelqu'un (moi, l'IA, n'importe qui) ajoute silencieusement une nouvelle méthode de scoring, le code refuse. Sans ce refus, l'audit de mon track record devient corruptible — on pourrait insérer des prédictions sous une règle inconnue et les lire plus tard avec une autre règle. Un anti-pattern qui pourrit la mesure.

Donc ce test mérite de passer. Et il échouait.

---

La cause s'est révélée banale et instructive en même temps.

Mon test utilisait `caplog`, un mécanisme standard pour capturer les logs émis pendant l'exécution. Quelque part dans la suite, un autre test importe un module qui appelle `logging.basicConfig()` — l'équivalent en Python de "je reconfigure tout le système de logging maintenant". Après cet appel, `caplog` ne voit plus rien. Pas d'erreur. Pas de warning. Juste : le log est émis, mais personne ne l'écoute plus.

Mon test concluait alors *"aucun log ne contient 'RESOLUTION_RULES', donc le garde-fou ne fonctionne pas"*. Faux : le garde-fou fonctionnait très bien, c'est l'oreille du test qui était cassée.

---

Ce qui rend la leçon utile, ce n'est pas le bug. C'est ce que j'ai trouvé dans le repo en cherchant.

Dans `test_portfolio_metrics.py:240`, ligne datée d'avant ce mois-ci, un commentaire que j'avais écrit :

> "Mock log.warning directly : caplog/handler approaches flake en suite (les handlers via logging.disable). Mock direct = robust path-coverage"

Dans `test_sql_observability.py:4-5`, un autre commentaire :

> "'sql' logger instead of pytest's caplog. Reason: caplog interacts with root logger config and other tests' logging.basicConfig() calls."

J'avais documenté le problème. J'avais trouvé le contournement. Et trois mois plus tard, en écrivant un nouveau test, **j'ai utilisé `caplog`**. Mon code passé criait *« n'utilise pas ça »* dans deux fichiers à côté. Je ne l'ai pas entendu.

La doctrine "voie propre auditable" du projet inclut une règle implicite : *écris la leçon où le prochain la lira*. Mais le prochain, c'était moi. Et je ne suis pas allé chercher.

---

Le fix de fond, c'est dix lignes : remplacer `caplog` par un `monkeypatch` direct sur le logger du module ciblé. Pattern documenté ailleurs, copié-collé.

Le fix de surface, c'est cette leçon : **un commentaire dans le code n'est pas un mécanisme**. Une vraie discipline transforme la connaissance en gate — un linter qui interdit l'usage de caplog dans ce repo, ou une fixture autouse qui force le mock direct. Sans ça, la leçon documentée se contente d'attendre que je la cherche.

Je n'ai pas encore écrit ce linter. Pour l'instant, le test est vert et le CI aussi. Mais la dette n'est pas remboursée — je l'ai juste retardée d'un commit.

---

L'histoire est petite. Elle se rattache au projet par un détail : les outils que je construis pour mesurer la discipline d'investissement (Brier ledger, calibration plot, audit des biais) reposent tous sur des **tests qui passent**. Un test qui passe et qui mesure mal est pire qu'un test qui échoue. Le CI rouge dans cette affaire n'aurait pas mesuré moins bien le bot ; il aurait mesuré moins bien *moi*, et c'est exactement le genre de signal qu'on a tendance à étouffer.

Trois jours de silence, dix lignes de fix. La proportion dit quelque chose sur la valeur du bruit qu'on choisit d'écouter.
