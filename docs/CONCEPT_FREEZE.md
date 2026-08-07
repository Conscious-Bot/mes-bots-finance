# CONCEPT FREEZE — le concept est clos. Il ne reste que l'usage.

**Déclaré le 2026-08-04** (trois jours avant l'échéance — la semaine de gel s'est pliée en une journée).
**Provenance** : audit de clôture 03/08 (information / conseil / dashboard / méthode / signaux) ·
verdicts des deux conseils 03/08 · exécution 04/08 (TODO.md « semaine de gel », tout coché).

---

## Ce qui est GELÉ (le périmètre — construit, prouvé, fini)

- **Information** : ingestion Gmail (kill-list 10 sources, test-verrouillée retrait-seulement) + EDGAR
  primaire + prix. AUCUNE source ne s'ajoute. Le scorer (fail-closed L15) ne se tune pas (L16).
- **Conseil** : digest sous gate mécanique (« le LLM propose, le gate dispose » — 0 urgent = normal) ·
  weekly synthesis · alertes/digue Telegram. Aucun raffinement (nature, claim_id, lanes… : morts).
- **Dashboard** : 6 pages décision-relevantes, 3 pages retirées du DOM (fonctions vivantes non
  affichées). AUCUN travail visuel, panneau, polish — jamais.
- **Méthode** : 4 couches doctrinales + registre (18+ hypothèses, garde H11, dead-man's-switch) ·
  digues sur HWM canonique (ancre policy 59 224) · enum biais + divorce tagger déclaré ·
  gel = propriété de l'échelle BOOK (D1). AUCUNE nouvelle hypothèse, monitor, couche, extension.
- **Fiabilité** : backup + offsite + restauration PROUVÉE (7 s) · rotation count-based · dead-man
  horaire (disque/backup/token/bot) · H9c prouvée (drill non-Mac 04/08). Ça tourne seul.

## Les TROIS seules classes de changement autorisées

1. **RÉPARATION** — quelque chose est *cassé ou faux* (un test rouge, une garde qui ment, un crash).
   Corriger l'instance, fermer la classe. Rien d'autre.
2. **SOUSTRACTION** — retirer, jamais ajouter. Une source, un panneau, un sous-système qui meurt.
3. **DÉCLENCHÉ-PAR-FALSIFIEUR** — une obligation émise par le registre lui-même (un falsifieur qui
   tire, une péremption d'exposition, un palier de digue). C'est de l'OPÉRATION, pas du build.

**Tout le reste est interdit jusqu'à N ≥ 50 paris résolus.** Pas « plus tard » : interdit.
Le pourcentage d'amélioration possible n'est pas un argument — c'est le musée qui frappe à la porte.

## Ce qu'est l'USAGE (la seule activité à partir de maintenant)

- **Poser des paris pré-enregistrés** — 20 en 60 jours (échéance : ~03/10/2026). C'est la seule
  chose qui compose. À J+60, si N stagne : on remet en cause la vision SaaS, on ne repolit pas.
- **Exécuter les gates telles qu'écrites** (ou les suspendre par protocole digue, journalisé).
- **Tenir le journal** : décisions structurées, résistances documentées, revues fait/prix.
- **Laisser les resolvers tourner** : +30/60/90j, Brier, digue 04h, dead-man horaire, weekly dim. 18h.
- **Mesurer les contrats de mort** : digest (urgent→décision|résistance ≥ 50 % sur 4 sem., sinon il
  meurt) · weekly (4 sem., sinon mort) · re-drill H9b+H9c avant le 30/10.

## Dettes déclarées (gelées, datées — pas des tâches)

- `date_du_fait` par signal (ACT-006 résidu, option b, 04/08) — dormant jusqu'à N ≥ 50.
- `book_share_of_networth` (couche vie 6/7) + devise de l'objectif Séoul — dus par le gérant, à son heure.
- Bascules registre H9c→TENUE + H5/ACT-004 : **retenues** sur le one-liner moteur
  (`assumption_graph.py:120`, patch fourni) — classe RÉPARATION, à passer par Cowork.

## Le serment opérationnel

> Le système a le droit de dire « je ne sais pas ». Il n'a pas le droit de se taire en tombant.
> Le gérant a le droit de désobéir à une règle. Il n'a pas le droit de le faire sans l'écrire.
> L'instrument est fini. **Ce qui compose maintenant, c'est le temps — et il ne se rachète pas.**

---

## LA FONCTION OBJECTIF (scellée le 07/08 — tout le reste est moyen)

> **PRESAGE maximise la vitesse d'apprentissage d'un décideur tout en minimisant
> la récurrence des erreurs coûteuses.**

Dashboards, graphes, digests, tribunaux, hypothèses, paris : des moyens, pas la fin.

**Le filtre (toute fonctionnalité future, sans exception)** : *réduit-elle la fréquence,
le coût ou la récurrence d'une classe d'erreurs ?* « Intéressante » → rejet. « Plus joli »
→ rejet. « Aide à explorer » → insuffisant. « Réduit durablement les erreurs de sizing » /
« diminue le délai d'admission d'une erreur » → mérite d'exister.

**Le dashboard ne répond qu'à trois questions** : que risque-je de faire de faux
aujourd'hui ? · quelles erreurs suis-je en train de ne plus faire ? · qu'est-ce qui
exige réellement une décision ? Le reste est de la navigation.

**Développement post-gel, inversé** : on ne part plus d'une fonctionnalité — on part
d'une CLASSE D'ERREURS (comment la détecte-t-on ? la bloque-t-on ? mesure-t-on sa
disparition ? prouve-t-on qu'elle ne revient plus ?) et alors seulement on code.

**L'objectif unique des trois prochains mois** : accumuler assez de données pour
RÉFUTER tout ce que nous croyons aujourd'hui. Si le reason-matching ne sert à rien,
si des classes ne disparaissent jamais, si des protections sont inutiles → suppression.
Ce qui survivra à la réfutation est le cœur irréductible de PRESAGE. Le gel protège,
l'operate nourrit, **le dégel juge** — ce n'est pas une release, c'est un jour de
résultats.

---

## LECTURE PRÉCISÉE DU GEL (07/08 — synthèse, le gel ne bouge pas)

**Interdit jusqu'au dégel** : nouvelle architecture · nouvelle couche · nouveau
sous-système · ledger d'erreurs dédié · écran « Improve » · multi-tenant · nouveau
moteur/base/registres.
**Autorisé immédiatement** : supprimer · fusionner · renommer pour clarifier ·
changer la hiérarchie visuelle · améliorer une carte existante · modifier un
workflow existant — tribunaux, paris, nettoyage, cards, regroupement d'écrans,
pilotes silencieux.

**La règle qui remplace les discussions de priorisation** :
> Avant le dégel, PRESAGE ne gagne pas en ajoutant des capacités. Il gagne en
> rendant les capacités existantes inévitables, visibles et impossibles à contourner.

**Métrique du mois (le seul compteur)** : ratio Suppression/Ajout — cible extrême
**Ajouts : 0 · Suppressions : 100+**. Le diagnostic : PRESAGE souffre de
surprésentation, pas de manque d'intelligence — elle est là, noyée.
