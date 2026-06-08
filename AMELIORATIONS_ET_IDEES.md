# PRESAGE — Axes d'amélioration & nouvelles idées (creuse profond)

> Exploration froide du cœur `intelligence/` (84 modules) au HEAD `0042956`. Classé par **levier** (impact/effort), pas par catégorie. Chaque idée est ancrée dans un module ou une table existante, jamais générique.

## 0. Corrections à l'audit de la veille (intégrité avant tout)

Deux constats de `AUDIT_TECHNIQUE.md` étaient **faux** après inspection profonde — je les corrige :

- **Factor concentration : déjà mécanisée.** `intelligence/factor_exposures.py` décompose le book par `macro_factor` (capex-IA / cycle mémoire / EUR-USD / défense / terres rares-Chine), expose un composite honnête (« 77 % pari IA élargi ») **et** fait des stress tests déterministes (capex-IA −30 %, EUR/USD +10 %, restriction Chine). C'est branché dans `dashboard/render.py`. Mon P0.1 (« le système ne mécanise pas la concentration ») était erroné. Ce qui reste vrai : ce n'est pas encore un **monitor à transition** (cf §Feature-3).
- **`lock_in` : déjà construit et déjà déclenché.** Wiré dans `shared/positions.py:216` (hook post-commit), il a capturé un événement réel : vente SNOW le 03/06 (`bias_events` id=5, `auto_detected`, résolution +90j programmée 01/09). Le README (« non instrumenté à ce jour ») est **périmé**, pas le code.
- **P0.2 reformulé.** Le resolver n'est PAS cassé : sur 184 prédictions NULL, **0 sont en retard**, 184 sont en vol légitime (161 à horizon 30j, créées récemment). Le N=35 résolu n'est pas un bug, c'est l'**arithmétique d'un système de 26 jours sur des horizons 30j**. Le problème réel n'est pas la résolution — c'est la **latence structurelle de la boucle** (cf Feature-1).

Leçon transversale : **la doc canonique ment au prochain agent sur au moins 3 faits matériels.** Pour un projet dont l'`AGENT_HANDOFF.md` *est* le contrat de reprise, c'est le défaut le plus coûteux du repo — détaillé en Intra-3.

---

## 1. Le vrai actif : la boucle-de-soi (lire avant tout le reste)

`self_loop.py` encode la seule distinction qui compte stratégiquement :

| | Boucle-marché | Boucle-de-soi |
|---|---|---|
| Question | « ma thèse était-elle juste ? » | « ma discipline a-t-elle aidé ou nui ? » |
| Sortie | calibration / Brier | quantification de biais |
| Défendabilité | **commoditisable** (tout le monde calibre) | **unique à l'utilisateur** |
| Asset | non | **oui — c'est Path 6** |

**Implication directe sur la priorisation :** presque tout l'effort récent (16 mentor-gates, Performance V3, IR vs SPY, calibration isotonic) alimente la boucle-marché — la partie *commoditisable*. La boucle-de-soi est encore en **V0** (J+30 seul, contrefactuel « hold strict » seul, exposition CLI). **Inverser ce ratio est le mouvement à plus haut levier du projet.** Les idées ci-dessous sont triées dans cet esprit.

---

## 2. INTRA — refactoring / durcissement

**Intra-1 · Gates CI grep (P0, effort faible).** Rendre réels deux invariants aujourd'hui fictifs : `yfinance` hors `prices.py` (19 fichiers) et `sqlite3.connect("data/bot.db")` littéral (9 sites) = build rouge. Le bypass yfinance reste le seul vrai SPOF (toute la donnée prix dépend de Yahoo sans cache partagé). Les 9 chemins DB hardcodés sont des bugs (cassent l'override `DB_PATH` → tapent la prod en test).

**Intra-2 · Découper `render.py` (6348 l, 121 fns).** Extraire `render_data.py` (fetch/agrégation DB), `render_html.py` (templates), `svg_paths.py` (maths sparkline — `_spk_smooth_path` 412 l, pure, testable). 306 commits/14j sur ce fichier = surface de régression maximale. Le module SVG isolé gagne des property-tests gratuits.

**Intra-3 · Réconcilier la doc avec le code (sous-estimé hier).** L'`AGENT_HANDOFF.md` se veut le contrat de reprise pour agent IA, et il est faux sur : « 414 tests » (réel 1107), `render.py` « 1860 l » (réel 6348), `lock_in` « non instrumenté » (réel : firing), factor-exposure absent (réel : branché). **Antidote durable :** un script `scripts/doc_drift_check.py` en pré-commit qui regénère les chiffres volatils (compte tests, LOC des fichiers cités, état des modules « non instrumentés ») et échoue si la doc diverge. La doctrine « type quand tu touches » appliquée à la doc.

**Intra-4 · Réveiller ou tuer le code mort.** `probabilistic.py`, `reconcile.py`, `shadow_decisions.py` = zéro import. `shadow_decisions` est probablement la coquille de l'idée Feature-6 (shadow book) — soit on la ressuscite pour ça, soit on la supprime. Ne pas laisser de modules zombies dans un repo qui prêche la taste.

**Intra-5 · `except Exception` × 644.** En tension avec la doctrine fail-closed (L15). Cibler les plus chauds (jobs cron, `scoring_orchestrator`, resolver) : un catch large dans le resolver pourrait avaler silencieusement un échec de prix et laisser une prédiction NULL pour toujours. Remplacer par except typés + log + compteur d'échecs observables.

---

## 3. FEATURE — étendre ce qui est à moitié construit

**Feature-1 · Sondes de calibration court-horizon (attaque la latence de boucle).** 161/184 prédictions en vol sont à 30j → la boucle-marché a une latence minimale de 30 jours, et N_résolu ne peut croître que d'un cran/mois. Idée : émettre des **prédictions-sondes 7j** découplées des thèses de conviction (qui restent 18-24m), purement pour accumuler du Brier vite. En 8 semaines tu passes de N=35 à N~100+ et la calibration cesse d'être du bruit. À tagger `probe` pour ne pas polluer le track-record de conviction. C'est le déblocage le plus direct du problème de puissance statistique.

**Feature-2 · `self_loop` V0 → V1 (le moat).** La roadmap est déjà écrite dans le docstring : ajouter horizons 60/90/180, contrefactuels `rotate_to_X` (pas seulement « hold strict »), et **un panneau dashboard**. Aujourd'hui la boucle-de-soi est invisible (CLI). La rendre visible = transformer l'asset unique en quelque chose qu'on peut montrer (acquéreur, abonné Substack).

**Feature-3 · Factor concentration en monitor à transition.** `factor_exposures` calcule mais n'**alerte** pas. Le pattern monitor (`docs/templates/monitor_pattern.md`, déjà utilisé par `kill_criteria` / `over_cap`) est fait pour ça : seuil « AI-broad > 75 % » → événement journalisé + notif Telegram à la transition. Réutilise un gabarit figé, ~3× plus rapide que le 1er monitor. Ferme le trou « panneau statique vs garde active ».

**Feature-4 · Calibration conditionnelle au régime.** `macro_regime` existe (22 fichiers le référencent). Slicer le Brier par régime : « bien calibré en risk-on, surconfiant en risk-off » est un insight de 2e ordre que l'archi peut déjà produire — il manque juste le N (cf Feature-1 qui le débloque). Insight méta sur *quand* le jugement de l'utilisateur se dégrade, pas seulement *de combien*.

**Feature-5 · Anti-monoculture de la source.** Les 76 sources sont massivement des newsletters Substack macro (Tooze, Macro Compass, Coin Metrics, StL Fed…). Input narratif **corrélé** : les mêmes penseurs réflexifs → faux sentiment de diversité de signal. `sources` track déjà `credibility` + `half_life` + `n_correct` ; ajouter une métrique de **corrélation inter-sources** (deux sources qui disent toujours la même chose à T0 ne comptent pas comme deux confirmations). Anti-double-comptage du signal, cohérent avec la doctrine anti-double-instrumentation.

---

## 4. NEW — idées net-new à fort levier

**New-1 · Pre-registration cryptographique des prédictions (le plus haut ROI narratif).** Pour Path 5/6, l'asset est un track-record *vérifiable*. Aujourd'hui il est « trust me » : rien n'empêche techniquement une édition rétroactive. Hasher chaque prédiction à la création (`probability_at_creation` + `target_date` + `baseline_price`) et committer le hash de façon horodatée-tamper-evident (git tag signé, ou OpenTimestamps/blockchain anchor). Différence entre « je l'avais dit » et « **prouvablement** dit à T0 ». Quelques heures de dev, change la nature de l'asset.

**New-2 · Shadow book — le coût € cumulé du biais (le graphe qui vend la thèse).** Maintenir un portefeuille parallèle « si j'avais suivi chaque signal de discipline » vs le réel, et tracer le **€ cumulé que les biais ont coûté**, avec en regard combien PRESAGE en a rattrapés. La matière première existe (`bias_events.counterfactual_json` + `decision_counterfactual`, 214 lignes). C'est **le slide unique** d'un deck acquéreur / du post de lancement : une courbe « voici ce que mes biais m'ont coûté, voici ce que l'instrument a sauvé ». Ressuscite `shadow_decisions.py` (Intra-4).

**New-3 · Moteur calibration-as-content (ferme la boucle vers la distribution).** `posts/` existe déjà. Auto-générer depuis la DB le post mensuel « voici ce que j'ai prédit / ce qui s'est passé / mon Brier / mes biais rattrapés ». L'arc d'auto-correction du jugement **est** le contenu (cf brand line « la vérité dans le bruit »). Connecte l'instrument (boucle) à l'asset Path 6 (audience) sans travail éditorial manuel récurrent.

**New-4 · Panel adversarial nommé au moment de la décision.** `decision_copilot` fait déjà un contre-argument Claude unique. Les 16 mentor-gates existent mais ne servent qu'à l'**intake** des thèses. Les réutiliser comme **voix dissidentes nommées** au moment du geste : Taleb sur le tail, Lynch sur le prix-vs-croissance, 2-3 one-liners en désaccord, chacun cité sur une evidence DB. Zéro nouveau modèle, UX à forte taste, et ça donne enfin un usage *décisionnel* aux gates (qui sinon restent du name-dropping en amont, comme noté dans l'audit produit).

**New-5 · Backtest des règles de discipline elles-mêmes.** `shared/backtest.py` (bt/ffn) est censé valider `lock_in` / `over_cap` / `kill_criteria` sur historique walk-forward — mais 2 fichiers seulement touchent « backtest ». Boucler : la question n'est pas « mon book bat-il SPY » (Performance V3 le fait déjà) mais « **mes règles de discipline auraient-elles ajouté de l'alpha sur 5 ans de mes propres patterns** ». C'est la validation de l'instrument, pas du portefeuille — et c'est ce qu'un acquéreur audite.

---

## 5. Red-team — ce qui peut faire capoter tout ça

**Le risque dominant : la sophistication dépasse l'évidence.** Magnifique instrument de mesure, N=35 de signal. Chaque feature méta élargit l'écart appareil/données. **Règle proposée (à graver) :** aucune nouvelle couche de scoring/calibration tant que N_résolu < 100. D'ici là, l'effort va à l'**ingestion** et à la **réduction de latence de boucle** (Feature-1), pas à de nouveaux étages.

**Overfitting single-user.** Calibrer sur 35 outcomes d'une personne risque de fitter du bruit qui ressemble à du skill. La boucle-de-soi (correction de biais) y est robuste — un biais comportemental est stable. La boucle-marché (Brier) ne l'est pas à ce N. Encore une raison de prioriser la première.

**Monoculture de signal** (Feature-5 audit) : si toutes les sources sont les mêmes macro-penseurs, le système calibre la justesse d'un consensus, pas d'un edge. L'echo-chamber est dans l'input, pas seulement dans la tête de l'utilisateur.

**Ce qui changerait ma conclusion :** si N_résolu était déjà > 100 avec spread Brier multi-buckets, je dirais « continue d'enrichir la calibration ». Il est à 35 sur 1 bucket élargi → la conclusion « gèle le méta, nourris la boucle » tient.

## 6. Séquence recommandée (90 jours)

1. **Semaine 1** : Intra-1 (gates CI) + Intra-3 (doc drift check) + New-1 (pre-registration). Trois gestes courts, fondations honnêtes.
2. **Semaines 2-4** : Feature-1 (sondes 7j) — démarre l'horloge statistique maintenant, tout le reste en dépend.
3. **Semaines 4-8** : New-2 (shadow book) + Feature-2 (self_loop V1 + panneau). L'asset unique devient visible.
4. **Semaines 8-12** : New-3 (calibration-as-content) une fois que N donne des chiffres montrables. Intra-2 (split render) en tâche de fond.

> Synthèse : le code est meilleur que ce que l'audit initial laissait croire — deux des « manques » étaient des features déjà construites mais **mal documentées et sous-exploitées**. Le projet ne souffre pas d'un déficit de capacité, mais d'un **déséquilibre d'allocation** : trop d'effort sur la partie commoditisable (calibration de marché) et pas assez sur la partie défendable (boucle-de-soi) et sur ce qui la nourrit (latence de boucle, pre-registration, shadow book). Rééquilibrer, et geler le méta jusqu'à N=100.
