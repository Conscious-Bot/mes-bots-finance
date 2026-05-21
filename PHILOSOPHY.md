# PHILOSOPHY — Le spine du bot

## L'idee fixe

**Ce bot n'est pas un outil d'analyse. C'est un systeme d'apprentissage en boucle fermee qui s'enrichit en continu a partir de ses propres predictions et de leurs outcomes.**

Chaque jour qui passe, chaque these loggee, chaque digest produit, chaque alerte envoyee nourrit la memoire structuree du systeme. Au bout de 6 mois, 12 mois, 24 mois, le bot n'est plus le meme outil — non pas parce que son code a change, mais parce que son contexte est devenu radicalement plus riche, plus calibre, plus personnel.

## La boucle fondamentale

INGESTION -> PROCESSING -> DECISION -> PREDICTION -> [TIME] -> OUTCOME -> RETROSPECTION -> CONTEXT ENRICHMENT -> [LOOP]

Chaque cycle :
1. **Ingere** des signaux (newsletters, X, TG, prix, macro, earnings)
2. **Process** via LLM avec prompts specialises + contexte historique
3. **Decide** : score, probabilite, conviction, sizing
4. **Logge la prediction** avec horizon mesurable
5. **Attend** que l'horizon expire
6. **Mesure l'outcome** objectivement (prix, evenement, fait)
7. **Retrospecte** : calibration, pattern, credibility
8. **Enrichit le contexte** pour les prochains cycles

## Les 6 boucles concretes qui materialisent la philosophie

1. **Prediction Ledger** — chaque prediction tracee avec outcome mesurable
2. **Calibration Engine** — verifier si la conviction 70% donne vraiment 70% de succes, drift injecte dans prompts
3. **Pattern Library** — extraction des conditions qui produisent succes/echecs
4. **Source Credibility** — score par source affine par feedback ET outcomes objectifs
5. **User Bias Detector** — tes erreurs recurrentes mesurees et flaggees
6. **Retrieval Engine** — analogues historiques injectes dans chaque nouvelle analyse

## Ce qui s'ameliore vs ce qui ne change pas

**S'AMELIORE :**
- Calibration des predictions
- Ponderation des sources
- Reconnaissance des patterns
- Detection de tes biais
- Pertinence des analogues retrouves

**NE CHANGE PAS :**
- Le LLM (Claude reste Claude)
- L'architecture du code
- Les principes de risk management

Le bot ne devient pas plus intelligent au sens IA. Le contexte qu'il manipule devient plus riche, plus precis, plus aligne avec la realite du marche et avec toi.

## Les limites honnetes

- **Edge erosion** : les marches s'adaptent
- **Data drift** : les regimes changent
- **Maintenance** : audits trimestriels necessaires
- **Evolution perso** : ton style change, le bot doit suivre

Mais dans ces limites, la trajectoire est ascendante. Un systeme avec 18 mois d'historique structure est qualitativement superieur a un systeme neuf.

## Consequence pour chaque decision de design

Pour chaque feature, on se pose la question :
**Est-ce que ca enrichit la boucle d'apprentissage, ou est-ce une feature isolee ?**

Si isolee : reconsiderer ou integrer a la boucle.
Si enrichit : prioriser et bien instrumenter (logging propre, outcomes mesurables).

## Consequence pour les prompts

Chaque prompt doit :
- Produire un output **mesurable** (probabilites, claims testables)
- Avec un **horizon** explicite
- Recevoir le **contexte historique pertinent** en injection (lessons, analogues, calibration drift)

## Consequence pour la memoire

SQLite n'est pas du stockage operationnel. C'est **le cerveau cumulatif du bot**.
Chaque table sert la boucle : signals -> predictions -> outcomes -> patterns -> context.

## La regle d'or

**Tout output non instrumente est gaspille.**

Si une analyse, une alerte, un score n'a pas :
- une revendication mesurable
- un horizon
- un mecanisme de retour d'outcome
- une injection dans le contexte futur

Alors c'est un produit jetable, pas une brique de la boucle.
