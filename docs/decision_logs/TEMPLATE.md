# Decision Log #XX — [titre court verbe-action]

**Date** : [DD mois YYYY]
**Owner** : Olivier Legendre
**Trigger** : [événement/contexte qui force la décision]
**Outcome** : [résumé 1-ligne du résultat décidé]

---

## Le contexte / Le bug / La friction

[Description honnête de la situation observée qui nécessite décision. Inclure mesures
empiriques quand possible (n, %, dates). Si c'est un bug, décrire les symptômes avant
le diagnostic.]

---

## La cause racine / L'analyse

[Investigation en couches : surface → cause technique → cause méthodologique → cause
structurelle. Mentionner les hypothèses initiales (correctes ET fausses) — l'évolution
du raisonnement est la valeur du log.]

---

## La décision

[Action(s) prise(s) avec rationale explicite. Code change / config / process change.]

---

## INVALIDANTS EX-ANTE (premortem) — section obligatoire

*Inspirée par Annie Duke "Thinking in Bets" + Klein "premortem". À remplir AVANT de
mesurer l'outcome, pas après. Liste 3-5 observables précis qui forceraient révision
ou abandon de cette décision dans les N jours/semaines à venir.*

| # | Observable | Seuil de révision | Horizon mesure |
|---|---|---|---|
| 1 | [ex: Brier moyen scorer V2 sur batch 10/06] | [ex: > 0.30] | [ex: 10/06/2026] |
| 2 | [ex: Reliability gap sur bucket 70-80%] | [ex: > 15pp] | [ex: 10/06/2026] |
| 3 | [ex: % predictions outcome="neutral"] | [ex: > 50%] | [ex: 10/06/2026] |
| 4 | [optionnel : observable secondaire] | [seuil] | [horizon] |
| 5 | [optionnel : observable tail-risk] | [seuil] | [horizon] |

**Engagement** : si un de ces seuils est franchi, je révise/abandonne cette décision
publiquement dans le decision_log de révision.

---

## Métriques de succès

[Quoi est mesuré post-décision pour évaluer si elle a marché. Distinct des invalidants :
les invalidants sont des trigger de révision, les métriques de succès sont des
indicateurs de validation positive.]

| Métrique | Cible | Date d'évaluation |
|---|---|---|
| [ex: Brier moyen batch 10/06] | [ex: ≤ 0.20] | [ex: 11/06/2026] |
| [ex: spread probability distribution] | [ex: ≥ 3 buckets distincts] | [ex: 11/06/2026] |

---

## Révisions du jugement (timeline)

*À remplir SI la conviction/décision évolue au fil du temps. Distinct des résolutions
finales. Mesure l'agilité cognitive (Julia Galef "Scout Mindset").*

| Date | Conviction avant | Conviction après | Trigger | Note |
|---|---|---|---|---|
| [JJ/MM] | [c4 / forte / actée] | [c2 / faible / abandonnée] | [observation X] | [contexte révision] |

---

## Outcome (à remplir post-horizon)

[Résultat empirique vs invalidants ex-ante et métriques succès. Si invalidant
franchi, lien vers le decision_log de révision.]

**Résultat brut** : [chiffres bruts]
**Verdict** : [SUCCÈS / ÉCHEC PARTIEL / ÉCHEC / RÉVISÉ EN COURS]
**Apprentissage transférable** : [ce qui s'applique au-delà de cette décision spécifique]

---

## Méta-réflexion (process > outcome)

*Annie Duke "Thinking in Bets" : juger la qualité de décision, pas la qualité du
résultat (= "resulting"). Une bonne décision peut donner un mauvais outcome
(et inversement). Cette section juge le PROCESS.*

- **Information disponible au moment de la décision** : [ce qu'on savait]
- **Information manquante qu'on aurait pu obtenir** : [ce qu'on aurait dû chercher]
- **Biais identifiés en rétro** : [ancrage / overconfidence / sunk cost / autres]
- **Décision optimale ex-post avec info actuelle** : [contrefactuel honnête]
- **Verdict process** : [BON / AMÉLIORABLE / MAUVAIS — indépendant du résultat]

---

## Notes / Références

[Liens vers ADR, commits, autres decision logs, sources externes (livres, papers).]
