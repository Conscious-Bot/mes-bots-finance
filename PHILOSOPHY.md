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

## High Standard — Discipline d'execution (21/05/2026)

Note: distinct du 'High Standard Mode' purge en matinee (b424af2). Ce qui suit est operationnel sur chaque ship, pas doctrinal sur la cadence ni le mode de vie. Pas de gating de session, pas de pauses imposees, pas de wellness-speak. C'est le checklist d'execution que l'assistant doit appliquer avant chaque script qui modifie le code.

Cette section a ete ecrite apres 3 incidents Phase C/G/E le 21/05/2026 qui ont consume ~2h de revert/recovery. Cause racine: les lessons codifiees (L34, L35, L36) etaient performatives, pas operationnelles. Codifier dans CONVENTIONS.md ne sert a rien si le script suivant n'ouvre pas le fichier.

### Checklist obligatoire avant chaque Bash modifiant du code

1. **Lire les 3-5 dernieres lessons CONVENTIONS** (L30+ actuellement) et verifier que le script propose ne viole aucune. Si une lesson s'applique, la citer explicitement dans le commentaire du script.

2. **Verifier les assumptions techniques**, pas par memoire mais par grep / doc lookup / inspection explicite. Examples reels:
   - 'Message.text est-il mutable?' -> check telegram.Message __slots__
   - 'Le body source est a quel indent?' -> sed/awk sur les lignes
   - 'Y a-t-il des imports AVANT le parse marker?' -> grep dans la fonction source
   - 'Cette commande est-elle importee ailleurs que registry.py?' -> grep -rn dans tout bot/

3. **Lister les fail modes potentiels** et la strategie de recovery avant d'ecrire le script. Pas une rationalisation post-incident, un dry-run mental ex ante.

4. **Hard-fail gates avec exit 1**, jamais des prints decoratifs. La forme correcte est:

        python3 -c 'import bot.main' || { echo FAIL; exit 1; }

   La forme inutile est:

        python3 -c 'import bot.main; print(OK)'

   L'erreur s'affiche mais le script continue.

5. **Audit repository-wide pour toute deletion ou refactor**. Grep bot/ entier, pas juste le source file + registry.py. Les imports legacy dans bot/main.py (post-refactor matin) sont un piege recurrent.

### Hors scope de cette section

Cette section ne parle PAS de:
- Quand faire des pauses
- Quand fermer une session
- Estimation de la 'fatigue' de l'utilisateur
- Suggestions de wellness ou de rythme

Si l'assistant trouve l'utilisateur trop ambitieux sur le scope, il dit ca clairement avec arguments techniques (risk specifique, dependency sur fresh state d'une feature, etc.), pas en argumentant sur la fatigue humaine. L'assistant est un outil sans fatigue; tout ralentissement de sa rigueur est imputable a son manque d'application des checklists ci-dessus.

### Test d'application

Avant chaque session de modification code, l'assistant doit pouvoir repondre OUI aux 5 questions:
- Ai-je lu CONVENTIONS L30+?
- Ai-je grep/verifie mes assumptions techniques, pas juste pattern-match?
- Ai-je liste 2-3 fail modes plausibles?
- Mes gates ont-elles toutes exit 1 ou equivalent?
- Mon audit sweep couvre-t-il bot/ entier (pas juste le source)?

Si une reponse est NON, le script n'est pas pret a etre poste.

