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


---

## High Standard Mode (13 mai 2026)

Décision : pivoter du mode "marathon ship velocity" vers mode "solidification > velocity" pour viser Path 5/6 (acquihire ou content + subscription).

### Reconnaissance honnête
Le bot fait beaucoup en 14h marathon. Mais beaucoup ≠ propre. Beaucoup ≠ vendable. Beaucoup ≠ defensible si quelqu'un me demande "comment je sais que ton Brier score est juste ?"

### Nouveau principe : Velocity solidified
Chaque nouvelle feature doit passer ces 5 gates :
1. **Tests** : les invariants math sont vérifiés (property-based où applicable)
2. **Cost** : le coût LLM est modélisé avant ship
3. **Observabilité** : success rate + duration tracked
4. **Failure modes** : que se passe-t-il si ça crashe / drift / API down ?
5. **Doc** : ADR si décision architecturale, sinon REFERENCE update

### KPIs enforcés (pas aspirationnels)
Chaque KPI a maintenant : cadence de check, seuil de dégradation, action déclenchée. Voir TODO.md section Dimension 2.

### Inversion temporelle
Avant : "qu'est-ce que je peux ajouter ?"
Maintenant : "qu'est-ce que je peux solidifier OU supprimer ?"

Les tickers, handlers, sous-groupes qui ne produisent pas de matière décisionnelle sur 90j sont candidats à suppression. La complexité a un coût cognitif réel.

### Mantra
**Plus de précision dans la mesure > plus de surface monitorée.**
**Plus de discipline dans l'usage > plus de discipline dans le code.**
**Plus de track record > plus de features.**


---

## Clarification 2026-05-16 — Reframe "Observation Mode"

Le terme "observation mode strict" écrit Day 2-3 était trop large et créait blocage cognitif sur 25 jours. Reframe empirique :

### Vrai contraint : Measurement pipeline immutable jusqu'à J+28

Ce qui est **FERMÉ** jusqu'à 2026-06-10 (batch resolution 45 predictions cohort) :

1. Modification du scoring system (materiality_v2 weights, composite formula)
2. Modification de la resolution logic (auto-resolve crons, outcome computation)
3. Modification du schema predictions / theses / outcomes (sauf migrations PIT formelles)
4. Modification du filter `/digest` threshold après J+28 actif
5. Modification de la cascade LLM tiers (cost contamination)
6. Modification des Brier computation paths

**Raison** : ces modifs contamineraient les 45 predictions in-flight et invalideraient le premier Brier mesurable empiriquement.

### Ce qui est **OUVERT** normalement avec les 5 gates High Standard :

- Bug fixes critiques découverts par usage (Day 4 a shippé 4 fixes pendant "observation")
- Refactor mécanique sans changement de comportement (Sprint 1.1 chunks)
- Nouveaux handlers READ-ONLY (queries, displays, dashboards)
- Nouvelles features qui n'écrivent PAS dans predictions/theses/outcomes
- Type hints sweep, ruff cleanup
- Documentation restructure
- CI activation
- Backup automation
- Display improvements (formatting, chunking, FX, etc.)

### Test pour décider si une feature est shipable avant J+28

Une seule question : **"Cette feature modifie-t-elle ce qui va être mesuré par Brier le 10 juin ?"**

- Oui → bloqué jusqu'à 11 juin
- Non → 5 gates normales (tests + cost + observability + failure modes + doc)

### Ce qui ne change pas du High Standard Mode

Les 5 gates restent intactes. Lessons #11 (verify avant commit) et #12 (audit ≠ fix) restent enforced. La discipline cognitive n'est pas le contraint qui pose problème. C'est le scope du contraint qui était mal calibré.
