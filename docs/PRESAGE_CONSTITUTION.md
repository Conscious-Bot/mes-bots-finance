# PRESAGE — CONSTITUTION (v1, 01/08/2026)

> Document de tête. Il ne décrit ni un portefeuille ni des règles : il décrit
> **la structure** qui autorise des règles. Trois couches strictement séparées.
> Toute page du système appartient à exactement UNE couche ; un document qui les
> mélange est une dette.
>
> **Calibration d'ambition, énoncée une fois** : l'architecture vise la rigueur d'un
> système de décision auditable. La VALIDATION, elle, n'existe pas : N se compte en
> dizaines de décisions résolues. Prétendre le contraire violerait l'axiome 1.

---

## COUCHE 1 — AXIOMES (invariants ; ne changent presque jamais)

Test d'admission d'un axiome : **non-dérivable** depuis les autres, **orthogonal**
aux autres, et **nécessaire** (le retirer casse le système). Le nombre n'est pas
sacré ; l'orthogonalité l'est.

| # | Axiome | Contenu | Ce qu'il absorbe |
|---|---|---|---|
| A1 | **Évidence** | qualité, indépendance et fraîcheur des faits ; tout datum = (valeur, asof, source) | provenance, vérifiabilité, anti-écho |
| A2 | **Incertitude** | distribution des résultats — **jointe**, jamais marginale | corrélation (propriété de la jointe, PAS une primitive) |
| A3 | **Utilité** | préférence sur les états de richesse, dont la **perte intolérable** | aversion au risque, backstop, « tolerable loss » |
| A4 | **État** | capital et engagements réellement exposés à l'instant t | poids, expositions, liquidités |
| A5 | **Temps** | horizon, dates de résolution, valeur d'attente | patience, compounding, échéances |
| A6 | **Irréversibilité** | coût et délai pour défaire une décision | liquidité (cas particulier), lock-ups, engagements |
| A7 | **Apprentissage** | boucle qui met à jour A1-A6 à partir des résolutions | calibration, doctrines, resolver |
| A8 | **Persistance des primitives** | **aucune grandeur dérivée n'est source de vérité** | scores, probabilités, confiance, conviction |

**A8, énoncé complet** : on persiste les **observations, les primitives et les
justifications** ; jamais les dérivées. Une dérivée est soit (a) **recalculée à la
demande** par un solveur, soit (b) **figée en journal immuable attaché à une décision**
avec la version du solveur — c'est la seule exception, imposée par le tribunal
d'auditabilité : dans cinq ans il faut pouvoir reconstruire ce que le système
calculait à l'époque, alors que le solveur aura changé —, soit (c) **mise en cache**
avec `asof` + hash des entrées (une mémo, jamais un état). Conséquences immédiates :
« confiance », « conviction », « score de moat », « p » ne sont plus des champs
stockés mais des sorties de fonction. Le corollaire opérationnel : **on ne migre
jamais des données historiques quand un solveur change.**

**Reformulation du rôle du système (remplace « supprimer la subjectivité »)** :
*le système ne supprime pas le jugement, il le rend **atomique, explicite et
falsifiable**.* Décomposer « moat = 5 » en coûts de bascule, concentration client,
durée des contrats et historique de pricing n'élimine pas l'estimation — cela la rend
vérifiable composante par composante.

**Dérivations explicites (donc EXCLUES des axiomes)** : corrélation ⊂ A2 · liquidité
⊂ A6 · conviction → remplacée par **poids d'évidence** (A1) et **probabilité
postérieure** (A2) · prix → n'est pas un axiome, c'est une observation (et jamais un
input direct de décision) · performance → conséquence, jamais objectif.

**Objectif du système, reformulé** : *maximiser la qualité des décisions sous
information imparfaite.* La performance en est une conséquence, mesurée mais non visée.

| A9 | **Reproductibilité** | toute décision est rejouable depuis l'état de l'époque | hash graphe + politiques + solveur + données |
| A10 | **Réfutabilité interne** | le système doit pouvoir se contredire lui-même | métriques dérivées, méta-règles, validateurs |

**A9, avec sa frontière** : chaque décision épingle `assumptions_hash`, `policy_hash`,
`solver_version`, `data_asof` — hash de la **structure parsée** (un commentaire ne
change pas le hash). **Limite écrite** : toute décision touchée par un LLM n'est pas
rejouable ; sa sortie est **archivée comme artefact**, jamais présumée reproductible.
La couche déterministe se rejoue, la couche interprétative s'archive.

**A10 — Réfutabilité interne** : *toute doctrine de PRESAGE doit pouvoir être mise en
défaut par un composant interne, à partir de données ou de dérivations, sans que ce
composant ait été construit pour cette réfutation précise.* Popper appliqué non pas
aux investissements, mais au framework lui-même. Preuves du 01/08/2026 : les objets
de preuve ont exposé des compteurs d'observations inventés · la sévérité dérivée a
exposé 11 divergences dont 3 raccourcis de modélisation (`modules: [ALL]`) · les
méta-règles ont exposé deux hypothèses falsifiées sans action bloquante. Aucun de ces
trois composants n'avait été écrit pour trouver cela.

**Règle anti-Goodhart (renforcée)** : *aucune métrique dérivée ne peut, à elle seule,
justifier une modification du système* — pas même comme diagnostic. Toute modification
exige **une métrique ET une explication causale**. Contre-exemple canonique : un rayon
de souffle qui baisse peut signifier « le système est plus modulaire » ou « quelqu'un
a supprimé des arêtes ». Corollaire d'implémentation : toute métrique structurelle est
publiée avec le **hash du graphe et son nombre d'arêtes**.

**L'ACTIF PRIMAIRE (reformulation 01/08, dé-privilégie la notion d'hypothèse)** :
*le modèle causal est l'actif primaire ; hypothèses, graphes, DAG et règles n'en sont
que des **représentations auditables**.* Une même croyance (« le compute restera
contraint ») peut s'écrire en une hypothèse, en trois, en réseau bayésien ou en graphe
causal — la décision ne dépend pas du format, elle dépend du modèle sous-jacent. Cette
formulation évite de figer l'architecture actuelle comme définitive. Conséquence :
l'apprentissage crédite **les relations**, pas seulement les nœuds — si une décision
se révèle bonne, il faut savoir si c'est l'hypothèse ou l'arête qui avait raison.

**Deux axes distincts, JAMAIS multipliés — matrice de lecture** :

| Centralité \ Influence décisionnelle | Haute | Faible |
|---|---|---|
| **Haute** | pilier confirmé | **hypothèse systémique jamais testée — danger maximal** (ex. H12) |
| **Faible** | règle locale efficace | candidat à l'élagage |

`centralité` est calculable aujourd'hui ; `influence décisionnelle` exige le registre
d'attribution (inexistant). Un score unique détruirait cette information.

**Vue d'audit — asymétrie entrée/sortie** (dérivée des métriques existantes, aucun
concept neuf) : un nœud à fort degré entrant et faible rayon de souffle sortant
signale une **arête manquante**, pas une faible importance. Produit une **liste
d'audit**, jamais un score — un score deviendrait une cible.

**Provenance typée (registre d'attribution, à construire)** : un composant est
`consulté`, `utilisé` ou `déterminant`. Sans cette distinction, on créditera dans six
mois des composants qui étaient simplement « dans la pièce ».

**Refus documenté (01/08)** : la propriété « l'architecture apprend sur sa propre
capacité à représenter le monde » est réelle mais **ne reçoit pas de nom** — A7
(apprentissage met à jour A1-A6) et A10 (réfutabilité interne) la portent déjà.
Nommer coûterait de la cognition sans ajouter de capacité. Premier refus produit par
la règle de parcimonie conceptuelle ci-dessous.

## RÈGLE D'ADMISSION SOUVERAINE (gravée 01/08/2026 — prime sur tout le reste)

> **Toute évolution de PRESAGE doit démontrer soit une amélioration mesurable de sa
> capacité à prendre de meilleures décisions, soit une amélioration mesurable de sa
> capacité à détecter ses propres erreurs. À défaut de l'une ou de l'autre, elle
> n'entre pas.**

Deux catégories légitimes, aucune troisième :
1. **Décisionnelle** — meilleur rendement ajusté du risque, moins de pertes
   permanentes, meilleure calibration, moins de décisions subies.
2. **Épistémique** — détection d'incohérences, remplacement d'une assertion par un
   théorème vérifié, gain d'auditabilité, réduction du risque de fausse confiance.

Test opérationnel, à poser à chaque proposition : *montre la décision qui sera
meilleure, ou l'erreur qui sera détectée et qui échappe aujourd'hui au système.*
Cette règle prime sur les six tribunaux (qui jugent la QUALITÉ d'une règle) : elle
juge son DROIT D'EXISTER. Elle s'applique aux propositions de l'humain comme à celles
du système.

**AUTO-RÉFUTABILITÉ DE LA CONSTITUTION (A10 retournée sur elle-même)** : *aucune ligne
de ce document n'est exemptée de réfutation empirique.* La constitution est une
hypothèse de plus haut niveau, jamais une autorité. Un système très cohérent devient
psychologiquement difficile à contredire — c'est le mode de mort le plus probable de
PRESAGE, avant tout défaut technique. Les axiomes eux-mêmes doivent figurer au registre
d'hypothèses le jour où une observation les met en tension.

**FILE D'ATTENTE DE PRESSION (protocole de gel)** : toute envie de modifier la
constitution ou une politique est **notée, pas exécutée** — avec ce qui l'a déclenchée,
si le problème est récurrent ou ponctuel, et quelle donnée manque pour trancher. Après
quelques semaines, l'essentiel se révélera lié à un événement isolé ; le reste, qui
revient sans cesse, mérite une évolution. **Frontière stricte** : la file concerne les
changements CONCEPTUELS. Un **défaut démontré** (backup en échec, incohérence détectée,
obligation bloquante ouverte) se corrige immédiatement — il a déjà sa preuve, il n'a
pas besoin de récurrence.

**INDICATEURS DE SANTÉ OPÉRATIONNELLE** (observations, jamais des scores de
performance) : part des décisions dont le resolver est terminé (cible ~100 %) · âge
médian des hypothèses non revues · nombre d'obligations bloquantes ouvertes. Un système
juste mais mal entretenu dérive ; ces trois nombres détectent la dérive par négligence,
que rien d'autre ne voit.

**Corollaire — cohérence interne ≠ utilité externe.** Une architecture peut être
élégante, falsifiable, entièrement auditée et sans aucune valeur ajoutée. Le seul
verdict qui compte est empirique.

**Immuabilité des témoins** : les baselines de comparaison (équipondération des mêmes
noms rebalancée trimestriellement, buy-and-hold du book initial) sont **gelées avant
toute décision** et ne sont **JAMAIS remplacées ni ajustées** au motif qu'elles « ne
sont plus pertinentes » — ce serait détruire le témoin. On peut en **ajouter** une
nouvelle (un ETF sectoriel, par exemple) ; on ne retire jamais les anciennes. La
classification de chaque décision (*identique / modifiée / bloquée* par PRESAGE) est
posée **au moment de la décision**, jamais reconstruite après coup.

**INVARIANT DU MOTEUR (01/08)** : *le moteur ne produit que des **observations** ou
des **obligations**. Jamais d'interprétations persistées.* Autorisé : une propagation,
une liste d'hypothèses à revoir, des arêtes non justifiées, des composants sans
preuve, des dépendances asymétriques. Interdit : « indice de robustesse », « score de
cohérence », « Structural Inconsistency = 0,74 » — des interprétations de sorties déjà
disponibles, qui créent un objet cognitif sans augmenter la capacité.

**TEST D'ADMISSION D'UN CONCEPT (trois questions, remplace « reconstructible → interdit »)**
La version stricte (« tout ce qui est reconstructible depuis les primitives est
interdit ») détruit le vocabulaire opérationnel : *backstop*, *ballast*,
*decision-trigger*, *force d'étayage*, *rayon de souffle* sont tous reconstructibles.
Nos deux refus n'avaient pas la même cause — d'où trois questions :

1. **Cache-t-il un jugement ou un paramètre non auditable ?** → INTERDIT (viole A8).
   Cas : « Structural Inconsistency » (l'*attendu* n'est défini par personne).
2. **Ne fait-il que nommer une sortie existante, sans usage fréquent ?** → INTERDIT
   (viole H11 : coût cognitif sans gain). Cas : « Architecture adaptative ».
3. **Est-ce une compression substituable 1:1, sans paramètre caché, d'usage
   fréquent ?** → **AUTORISÉ** : ce n'est pas un concept, c'est une **définition**,
   et sa fréquence d'emploi paie son coût.

**RÈGLE DE CROISSANCE (remplace « nommer ce qu'on retire »)** — distinguer deux
croissances : la **conceptuelle** (notion, axiome, catégorie nouvelle) coûte de la
cognition et tombe sous H11 ; la **connective** (arête, provenance, lien entre
concepts existants) augmente la puissance sans changer le langage et **doit rester
libre**. Toute proposition doit donc : **supprimer** un concept, **relier** deux
concepts existants, ou **démontrer** qu'aucune des deux options ne suffit avant
d'introduire un concept neuf.

**Labels humains = roues d'entraînement** : `severity.declared` (humain) coexiste avec
`severity.derived` (calculé) tant que le moteur se calibre. La **divergence est le
signal** — elle désigne un graphe incomplet, une intuition fausse, ou un solveur
défaillant. `declared` ne disparaît que le jour où les divergences sont rares ET
expliquées.

## COUCHE 2 — SOLVEURS (interchangeables ; évoluent avec l'état de l'art)

Un solveur est une **fonction** qui transforme des axiomes instanciés en une sortie
exploitable. Il est remplaçable sans amender la couche 1. On nomme donc le RÔLE, pas
l'outil.

| Rôle | Interface (entrées → sortie) | Implémentation actuelle | Remplaçants possibles |
|---|---|---|---|
| **Belief Updater** | prior + évidence datée → postérieur | mise à jour manuelle écrite (dette) | Bayes explicite, ensembles, marchés de prédiction |
| **Allocation Solver** | distribution + corrélation + état + contraintes → fourchette de taille | quart-Kelly × décotes | CVaR, risk parity, optimisation sous contraintes, Bayes hiérarchique |
| **Trigger Evaluator** | fait extrait × proposition pré-enregistrée → booléen | matching sur `invalidation_triggers` | NLI, extraction structurée |
| **Exposure Aggregator** | positions → expositions par driver | tagging manuel des facteurs | factorisation statistique (PCA/risk model) |
| **Calibration Scorer** | prévisions probabilistes + résolutions → score | à construire | **Brier**, log-score, courbes de fiabilité |
| **Attention Allocator** | flux d'information → ce qui mérite lecture | digest + gating mécanique | tout ranking supervisé par le taux signal→décision |

**Règle de couche 2** : un solveur se remplace en une session, sans réécrire une seule
ligne de la couche 1. Si son remplacement oblige à toucher un axiome, c'est que
l'axiome était en réalité une politique déguisée.

## COUCHE 3 — POLITIQUES (contingentes ; datées ; révisables par écrit)

Tout nombre vit ici. Une politique porte OBLIGATOIREMENT : sa **date**, son **auteur**,
sa **justification**, sa **condition de révision**, et **l'axiome qu'elle instancie**.

Exemples actuels : cap facteur dominant · caps par poids d'évidence · plafond venture
et budget de poche · paliers de drawdown (gel / tribunal / backstop) · niveaux de
decision-triggers par ligne · gates de prix de la watchlist · seuils de la condition
d'exception (c') · cadence des revues.

**Aucune politique n'est universelle.** Elles dépendent de l'horizon, des apports, du
patrimoine et de la tolérance du porteur — d'où l'urgence de la « couche vie », sans
laquelle toutes les politiques actuelles sont des placeholders plausibles.

---

## LE TEST D'ADMISSION — SIX TRIBUNAUX

Toute règle candidate doit survivre aux six. Cinq viennent du gérant (01/08) ; le
sixième répond à la faiblesse pré-enregistrée « sur-ingénierie ».

1. **Vérité** — réduit-elle réellement l'incertitude, ou a-t-elle seulement l'air
   intelligente ?
2. **Dérivabilité** — découle-t-elle d'un axiome par un solveur nommé ? (« 3 % parce
   que 3 % » = FAIL ; « sortie de quart-Kelly décotée » = PASS)
3. **Implémentabilité** — s'exprime-t-elle sans « je pense que » ? Un booléen ou un
   seuil observable, sinon FAIL.
4. **Auditabilité** — dans cinq ans, peut-on reconstruire pourquoi la décision a été
   prise, avec les données de l'époque ?
5. **Généralisation** — tiendrait-elle pour acheter une entreprise entière ? Sinon
   elle est probablement trop spécifique.
6. **Parcimonie (coût cognitif)** — le coût d'attention qu'elle impose est-il
   inférieur à l'erreur qu'elle évite ? Une règle juste mais jamais appliquée est une
   règle fausse. En cas d'égalité : **on supprime**.

---

## LE CHANTIER STRUCTURANT — MOTEUR BAYÉSIEN ET CALIBRATION

**Problème résolu par ce chantier** : l'origine des probabilités (faiblesse n°1 du
handoff). Renommer « conviction » en « probabilité postérieure » ne suffit pas — une
thèse n'est pas un événement binaire. Il faut trois briques :

1. **Proposition résoluble** : chaque thèse porte ≥1 énoncé falsifiable AVEC une date
   de résolution (« marge brute > X % sur 2 trimestres d'ici le T3 2027 »), distinct
   du variant narratif.
2. **Probabilité énoncée** à l'ouverture, puis **mise à jour à chaque évidence datée**
   — jamais par saut narratif, toujours prior + évidence → postérieur, avec la trace.
3. **Calibration Scorer** : Brier (ou log-score) sur toutes les propositions résolues,
   **du gérant comme du système** — y compris les overrides. On ne juge plus le
   résultat isolé, on juge la **calibration**.

Conséquence forte : au bout de N résolutions, la courbe de fiabilité **débiaise `p`**,
qui cesse d'être une intuition pour devenir une estimation corrigée par le track
record. C'est la fermeture de la boucle A7 → A2 → Allocation Solver.

**Attente honnête** : calibration exploitable vers N ≈ 100-200 propositions résolues,
soit 3-5 ans au rythme actuel. Ce n'est pas une raison de retarder — c'est une raison
de commencer à énoncer les probabilités **aujourd'hui**, puisque seules les
prévisions pré-enregistrées seront scorables.

---

## MIGRATION DES DOCUMENTS EXISTANTS

| Document | Couche | Action |
|---|---|---|
| `QUALITY_BAR` | 1 (axiomes A1/A2) | à relire, ne garder que l'invariant |
| `NORTH_STAR_QUALITE` | 3 (politique de sélection) + critères ⊂ 1 | séparer critères universels / gates chiffrées |
| `RISK_FRAMEWORK` | 2 (fonction de sizing) + 3 (tous les caps) | isoler la fonction des nombres |
| `LESSONS` (L1-L34) | 1 pour les doctrines épistémiques, 2 pour l'ingénierie | annoter chaque L# de sa couche |
| `decision_logs` | 3 (jurisprudence datée) | inchangé — c'est la mémoire |
| `GLOSSARY` | transversal | y déplacer : poids d'évidence, decision-trigger, allocation solver |

**Renommages de couche 1 (vocabulaire)** : « stop » → **decision-trigger** (le stop
n'est qu'un cas particulier : franchissement de niveau) · « conviction » → **poids
d'évidence** (mesurable) + **probabilité postérieure** (résoluble) · « Kelly » →
**Allocation Solver** (Kelly n'est qu'une implémentation).

---

## CE QUI RESTE NON RÉSOLU (à attaquer dans cet ordre)

1. **Couche vie absente** — toutes les politiques (couche 3) sont non calibrées tant
   qu'horizon, apports, besoins datés et part du patrimoine ne sont pas enregistrés.
   Rien d'autre ne peut être scellé avant.
2. **Propositions résolubles non écrites** — sans elles, pas de Brier, donc pas de
   débiaisage de `p`. Chantier n°1 de la couche 2.
3. **N minuscule** — aucune conclusion statistique n'est disponible avant des années.
   Toute revendication d'edge serait du bruit.
4. **Aucun benchmark** — la performance n'est comparée à rien. Un système auditable
   qui ne se compare à rien peut se raconter n'importe quelle histoire.
5. **Le tribunal 6 n'a jamais été appliqué rétroactivement** — combien des règles
   existantes survivraient au test de parcimonie ? Probablement pas toutes.
