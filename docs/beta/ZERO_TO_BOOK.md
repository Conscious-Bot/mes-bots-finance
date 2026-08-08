# PRESAGE Zero-to-Book — protocole expérimental DÉFINITIF (S0 v2, 08/08/2026)

> DEUX paris séparés, gates chaînés. RIEN n'est construit : pipeline manuel
> (Cowork = proposal engine), chaque friction notée. GO P-BETA / NO BUILD.
>
> TROIS paris nommés (taxonomie FIGÉE 08/08 soir — plus aucune mutation après
> le premier cobaye) :
> **P-BETA-1 (valeur du book)** — « un investisseur tiers voit son portefeuille
> transformé en thèses+falsifieurs+cards et le juge utile. » 3 cobayes,
> échéance 15/09. Critère : ≥2/3 demandent SPONTANÉMENT la version vivante.
> Secondaires (loggées, pas gates) : partie du book jugée utile ; « comment
> ferais-tu sans ? » (le concurrent réel — souvent Notion+ChatGPT+cerveau).
> **P-BETA-2 (friction d'ingestion)** — « un investisseur transmet son
> portefeuille sans comprendre la mécanique interne ni assistance technique. »
> Commence au PREMIER fichier réel. On ne spécule plus sur les formats :
> CSV propre = parser trivial · PDF = extraction · screenshot = vision ·
> colonnes ambiguës = mapping — chaque cas OBSERVÉ, jamais imaginé.
> **P-BETA-3 (living-book pull — DÉCISION FINALE 09/08)** — « A demande
> SPONTANÉMENT un lieu persistant ou une mise à jour ("ça se met à jour ?",
> "où je retrouve ça ?"). » 30 jours post-remise, la demande datée au friction
> log. Si 1 gagne et 3 perd : excellent analyste d'onboarding, pas un produit
> récurrent.
> **TRACE des deux tribunaux du 09/08** (pour l'honnêteté du registre) :
> (a) matin — pari « portail/usage » signé (5e oscillation close par
> signature) ; (b) même jour — RENVERSÉ par le gérant : « je signe le pari
> sans portail […] aucun fait utilisateur ne justifie son existence. On ne
> revient plus sur cette décision avant le premier débrief d'A. »
> Verdict : le fichier statique EST l'instrument de mesure du pull (son
> obsolescence fait parler le cobaye — offrir le portail d'emblée détruirait
> le signal). Le portail est une HYPOTHÈSE PRÊTE, non déployée :
> beta_access_v0.md, statut READY ≠ WARRANTED — déclenchement par observation
> utilisateur uniquement, jamais par l'envie de rendre PRESAGE « plus réel ».
> Plafond ≤1 j/sem RÉTABLI. Échec de 1 : le chantier meurt ou se requalifie.
>
> **Mode opératoire : asynchrone-invisible AVEC interaction humaine courte.**
> Le cobaye envoie son fichier (lien/adresse), le book revient en ≤24 h — il ne
> voit pas si derrière il y a 1 s de code ou 3 h d'humain, et c'est le test.
> MAIS l'interview courte reste (écrite ou appel) : on valide « j'accepte
> d'envoyer et de répondre à quelques questions », pas encore « je veux du
> 100 % automatique » — la seconde question n'existe qu'après preuve de la première.
>
> **FVM décomposé** : FVM-1 = reconstruction correcte (mécanique : positions,
> poids, devises — aucune taxonomie) · FVM-2 = observation non formulée par le
> cobaye (concierge, et son coût est UNE MÉTRIQUE : minutes humaines/user/
> observation — baseline 1er cobaye, trajectoire sur 3 = la spec d'industrialisation).
>
> **Fixtures** : chaque fichier reçu est archivé hors git (`beta/fixtures/<X>/` :
> input original → normalisation attendue → ambiguïtés → cas d'échec). Les trois
> exports réels SONT la spécification technique de tout futur parser — jamais
> l'inverse.

## Les 3 cobayes — profils VOLONTAIREMENT différents

| | profil | ce qu'il teste |
|---|---|---|
| A | investisseur structuré | profondeur/qualité de l'extraction |
| B | autonome mais peu structuré | friction d'onboarding, sait-il répondre à « changer d'avis ? » |
| C | expérimenté avec son propre système (Excel/Notion/ChatGPT) | substitution — le plus précieux : « je pourrais le faire moi-même » = le vrai problème ; « ça me fait gagner 3 h/sem » = le vrai signal |

## Le parcours (côté cobaye : 30 min, une seule session)

1. **« Donne-moi ton portefeuille. »** CSV, XLSX, ou screenshot broker.
   Aucun autre document requis. — *friction log : format reçu, lignes ratées.*
2. **Reconstruction (PRESAGE, hors de sa vue, ~1 h manuelle)** : tickers résolus,
   devises, PRU, poids, expositions croisées (facteur commun, concentration).
   Sortie intermédiaire : « J'ai reconnu N positions, X % du book sur le
   facteur Y ». **La réaction est CLASSÉE, pas juste notée** :
   `Known` (« oui, évidemment ») = zéro · `Interesting` · `Surprising`
   (« je n'avais jamais réalisé que ces 3 positions reposaient sur la même
   hypothèse ») · `Actionable`. Une observation correcte n'est pas une
   observation intéressante — seuls S et A comptent comme moment de valeur.
3. **Interview (20 min, conversation, pas questionnaire)** — uniquement ce que
   PRESAGE ne peut pas savoir, position par position en partant des plus
   grosses. Séquence STRICTE en deux temps :
   **(a) restitution fidèle d'abord** — « Si je comprends bien : tu la détiens
   parce que X, tu penses que Y, et ton hypothèse serait invalidée par Z » →
   CONFIRM/EDIT/REJECT. On mesure la capacité de PRESAGE à capturer SON
   raisonnement, pas la capacité du LLM à écrire de belles thèses.
   **(b) structuration ensuite** — seulement après confirmation de (a), la
   restitution devient thèse + falsifieurs candidats (nouveau C/E/R).
   JAMAIS d'invention silencieuse : perception manquante = donnée manquante.
   Stop/target : demandés UNE fois — l'absence est normale, « non défini ».
4. **Book construit** : DB SQLite SÉPARÉE par cobaye (`beta/<prenom>.db`,
   même schéma minimal theses/positions — isolation par fichier, zéro
   multi-tenant, zéro fuite possible avec le book Olivier).
5. **Remise : ses Position Cards V3.1** (HTML statique, le render existant —
   pas une nouvelle carte). Chaque carte : DOIS-JE AGIR / POURQUOI CETTE
   POSITION EXISTE / CE QUI ME FERA CHANGER D'AVIS + prochain fait daté
   (earnings récupérés pour SES tickers).
6. **Débriefing (quelques jours après la remise) — 5 questions, ORDRE STRICT,
   « paierais-tu » en dernier** (la question facile arrive quand les vraies
   réponses sont déjà tombées) :
   1. « Qu'est-ce qui t'a été le plus utile ? »
   2. « Qu'est-ce qui t'a paru inutile ou faux ? »
   3. « Comment ferais-tu la même chose sans PRESAGE ? » ← le concurrent réel
   4. « Si PRESAGE continuait à maintenir ce book, qu'aimerais-tu qu'il
      fasse demain ? » ← le produit que LUI veut, pas celui qu'on lui montre
   5. « Est-ce quelque chose pour lequel tu paierais ? »
   La demande SPONTANÉE de version vivante (avant la question 4) est le
   signal P-BETA-1 ; la question 4 nourrit le design de P-BETA-2.

## Garde-fous

- **Réglementaire (bloquant)** : PRESAGE extrait et formalise LE raisonnement
  du cobaye — jamais « PRESAGE recommande ». Formulations : « TON invalidateur »,
  « TA thèse ». Disclaimer écrit sur chaque remise : outil d'organisation de
  la réflexion, pas un conseil en investissement. Aucun cobaye PAYANT avant
  avis juridique (MiFID/AMF : la personnalisation est la ligne).
- **Privacy** : les données cobaye ne touchent JAMAIS data/bot.db ni le repo
  (dossier beta/ gitignoré) ; pas de PII dans les conversations de session
  au-delà du nécessaire.
- **Périmètre moteur intact** : zéro modification du core pour le beta. Si le
  render V3.1 exige un champ absent du book cobaye → la carte affiche son
  état honnête (« non défini »), on n'invente pas, on ne patche pas le moteur.
- **Le plafond** : ≤ 1 jour/semaine, total. Le calendrier d'usage prime.

## Ce qu'on observe (le vrai livrable du beta)

| étape | friction mesurée |
|---|---|
| upload | formats réels, taux de lignes reconnues |
| interview | minutes/position · le cobaye sait-il répondre à « changer d'avis ? » |
| falsifieurs | taux confirm vs edit vs reject des propositions LLM |
| cards | comprend-il en <20 s sans explication ? quelle question pose-t-il ? |
| rétention | demande-t-il la version vivante, et pour QUELLES lignes ? |

Chaque friction répétée ≥2 fois = candidate à l'automatisation (et pas avant).
S1+ (import outillé, interview scriptée, monitoring vivant) n'existent que si
P-BETA gagne.

## Message de recrutement (verbatim — AUCUN pitch supplémentaire)

> « Je teste actuellement un outil qui transforme un portefeuille
> d'investissement et le raisonnement derrière les positions en un book
> structuré de thèses, hypothèses et points d'invalidation. Je cherche
> 3 investisseurs pour une session de ~30 min. Je ne cherche ni feedback
> générique ni bêta-testeur complaisant : je veux voir si l'outil comprend
> réellement comment quelqu'un d'autre investit. Aucun engagement et aucune
> connexion broker nécessaire. »

Le recrutement est lui-même expérimental : qui répond, qui refuse, pourquoi.

## Grille de relecture par cobaye (à J+1, à froid, sans envie de construire)

```
Cobaye X (profil A/B/C)
├── frictions : n (lesquelles, étape)
├── erreurs d'extraction : n (restitution rejetée/éditée)
├── propositions falsifieurs : confirm / edit / reject
├── réactions reconstruction : K / I / S / A
├── demande spontanée de monitoring : oui/non (AVANT la question 4)
└── verbatim marquant : une phrase
```

Pendant la session : chercher « où PRESAGE échoue-t-il à comprendre cette
personne ? » — jamais un compliment. Classer, ne rien réparer. À 2 occurrences
seulement, une hypothèse produit apparaît : observation → hypothèse → pari →
résolution → build.
