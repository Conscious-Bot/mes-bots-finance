# Guide de session — Zero-to-Book (30 min côté cobaye)

> Rôle : concierge + chercheur. JAMAIS vendeur ni développeur.
> Interdits absolus en séance : défendre, corriger, pitcher, expliquer avant
> la réponse, « attends je vais te montrer ». Toute envie de défendre = une
> ligne au friction log à la place.

## Avant la session (concierge, ~1 h, hors de sa vue)

0. Arborescence par cobaye — `original/` est IMMUTABLE (la vérité de
   l'expérience ; portfolio.csv n'en est que la représentation normalisée —
   c'est contre l'original que tout futur parser sera testé) :
   ```
   beta/<prenom>/
   ├── original/          ← le fichier reçu, tel quel, JAMAIS modifié
   ├── portfolio.csv      ← normalisation concierge
   ├── theses.json        ← après interview confirmée
   ├── book.html          ← la restitution
   └── friction_log.md    ← copié depuis templates/, chronométré
   ```
1. Recevoir le portefeuille (CSV/XLSX/screenshot). Noter le format EXACT reçu
   et l'heure (T0). Chronométrer CHAQUE étape ensuite (grille du friction log).
2. `python3 docs/beta/tools/build_book.py --csv beta/<prenom>/portfolio.csv --out beta/<prenom>/`
   → reconstruction : positions, poids, expositions croisées.
3. Préparer 1 à 2 observations de reconstruction (facteur commun, concentration)
   — elles serviront de test K/I/S/A, pas de démonstration.

## Déroulé (30 min)

**0-3 min — cadrage, une phrase, pas plus** :
« Je vais te montrer ce que l'outil a compris de ton portefeuille, puis te
poser des questions sur tes positions. Il n'y a pas de bonne réponse. »

**3-8 min — reconstruction montrée** : les positions reconnues, les poids,
PUIS l'observation croisée (« X % de ton portefeuille dépend du facteur Y »).
→ noter la réaction telle quelle et la classer K/I/S/A. Ne rien commenter.

**8-28 min — interview, position par position (les plus grosses d'abord)** :
- « Pourquoi tiens-tu cette ligne ? » — laisser parler, ne pas guider.
- « Qu'est-ce qui te ferait changer d'avis ? »
- **(a) Restitution fidèle** : « Si je comprends bien : tu la détiens parce
  que X, tu penses que Y, invalidé par Z — c'est bien ça ? » → CONFIRM /
  EDIT / REJECT (compter).
- **(b) Structuration** : seulement après (a) confirmé, reformuler en thèse +
  falsifieurs candidats → nouveau C/E/R.
- Stops : UNE question (« tu utilises des stops ? ») — l'absence est normale.
- Relances neutres uniquement : « dis-m'en plus », « comment tu ferais, toi ? »,
  « qu'est-ce qui te gêne là-dedans ? ».
- Perception introuvable → la carte dira INDÉFINI. Ne pas la remplir pour lui.

**28-30 min — clôture SANS débrief** :
« Je te livre ton book ce soir. On se reparle dans 2-3 jours. »
→ Les 5 questions du débrief attendent J+2 (jamais à chaud).

## Après la session (concierge)

1. Compléter les thèses confirmées dans `beta/<prenom>/theses.json`.
2. Regénérer : même commande → `book.html`. Vérifier CHAQUE chiffre
   (le garde M1 refuse les incohérences, mais relire quand même).
3. Livrer le HTML avec le disclaimer (inclus par l'outil). Rien d'autre.
4. À J+1 : remplir `friction_log.md` à froid.
5. À J+2/J+4 : débrief différé, ordre strict, « paierais-tu » en dernier.

## Test 20 secondes (à caser au moment de la remise, ou avec un tiers)

Montrer une carte SANS explication : « Dois-tu agir ? Pourquoi possèdes-tu
cette ligne ? Qu'est-ce qui te ferait changer d'avis ? » — chronométrer,
noter les questions spontanées (« c'est quoi +N masqués ? », « quand est-ce
que ça se met à jour ? » ← le signal le plus important).
