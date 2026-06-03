# Contrat de présentation : Fraîcheur & Mouvement

**Status** : Spec actée 2026-06-03, **build post-J-day**. Ne déplace pas les items du 10/06 (les deux configs healthchecks + reading contract, la conversation). Vient après.

**Related** : provenance posée → [[task #101]] ; contrat de mode dégradé (stale-marking réutilisé) → `dashboard/restitution.py` ([[task #94 phase 4]]) ; aggregator-per-number → [[task #102]].

## La loi

Le diff, pas le flux. Le mouvement encode un changement, jamais une stimulation. Statique par défaut ; le mouvement est l'exception qui porte une info et se résout au repos. Une donnée est fraîche quand c'est possible, et jamais périmée en silence.

## Le linchpin : le snapshot « dernière vue »

Tout pivote là-dessus. Persiste l'état affiché à chaque ouverture (petite row DB / fichier + timestamp). À l'ouverture suivante, diff `current` vs `dernière-vue`, puis écrase. **Le diff pilote et ce qui s'anime et le cadre « depuis ta dernière visite »**. Source unique du diff.

## Mécanique de mouvement

- **Anime le diff une fois (~300–400ms), puis repos.** Les chiffres changés comptent jusqu'à leur nouvelle valeur ; les inchangés sont statiques d'emblée.
- **Déclenchement sur changement de valeur réel, jamais sur timer.** Aucune boucle de refresh visible.
- **Le mouvement termine.** Pas d'état animé persistant. Repos = défaut.
- **Motion = fait, comme la couleur.** Sens/ampleur de la transition encodent le delta, pas l'excitation. Pas de pulse, pas de clignotement, pas de canal « excitation ».

## Mécanique de fraîcheur

- **Refresh-on-view** : recalcule les chiffres volatils à l'ouverture, pas sur un timer aveugle.
- **As-of stamp** sur chaque chiffre/groupe : « as of HH:MM ».
- **Stale-marking** : au-delà d'un seuil de péremption (ou si le fetch a échoué), le chiffre est marqué stale, jamais affiché comme courant. Réutilise le marquage du contrat de mode dégradé (`dashboard/restitution.py`).
- **TTL ciblé** : `_PX_TTL` ~5 min en heures de marché là où la fraîcheur change une décision ; large ailleurs.

## Cadre « depuis ta dernière visite »

Le dashboard ouvre sur un récap en tête : « N choses ont bougé depuis [dernière visite, HH:MM] ». Engageant par l'info, te libère une fois lu.

## Invariants (à tester)

1. **Rien ne s'anime sur timer.** Test : sans changement de valeur sous-jacente, deux rendus successifs produisent zéro animation.
2. **Tout mouvement se résout au repos (< 500ms).** Test : aucun état animé persistant après transition.
3. **Pas de mouvement ⇒ rien n'a changé** (et réciproquement). Le mouvement ne ment pas sur le changement.
4. **Tout chiffre porte un as-of ; tout chiffre périmé est visiblement stale**, jamais affiché courant.
5. **Motion encode le delta, pas la sévérité.** Aucun canal d'excitation.

## Où ça vit / où ça ne vit pas

- **Vit** : le dashboard (diff animé à l'ouverture + as-of + stale-marking).
- **Ne vit pas** : aucun flux continu, aucun ticker, aucune animation sur timer, aucune couleur/pulse d'engagement. C'est la ligne anti-Robinhood, garantie structurellement par l'invariant n°1.
- L'**engagement réel** n'est pas dans cette couche — il est dans le brief du matin (utilité) et l'intervention au moment de la décision (Surface 2). Cette couche rend le dashboard vivant et honnête, pas addictif.

## Premium

Par le craft : typo, tabular-nums, espacement, l'axe signature, transitions douces mais rares. **Stripe/Linear, pas Robinhood.**

## Build mapping + scope

- S'appuie sur la provenance déjà posée (as-of, [[task #101]]) et le contrat de mode dégradé (stale-marking réutilisé, `dashboard/restitution.py`).
- **Pas un moteur de refresh** : un snapshot + un diff + une transition CSS. Léger.
- Dépend de l'uptime pour avoir de la donnée fraîche à diffuser — le bot vivant fait 80%.
- **Post-J-day polish.** Ne déplace pas les items du 10 (les deux configs + la conversation) ; ça vient après.

## Précedence / contexte

Cette couche répond à la question "rendre le dashboard plus vivant SANS basculer en dopamine-engine". Le diagnostic : "vivant d'une façon qui te relâche, au lieu de te scotcher". L'engagement qui compte ne vit pas sur le dashboard — il vit dans le brief du matin (rituel d'utilité) et l'intervention Surface 2 (le miroir au moment de la décision). Le dashboard, lui, est l'instrument de mesure ; il doit être vivant comme un cockpit, pas comme un casino.

L'invariant n°1 (« rien ne s'anime sur timer ») est le verrou structurel qui empêche de glisser vers Robinhood : pas un choix d'esthétique, un test mécanique. Si un rendu sans changement de valeur produit une animation, le code viole le contrat — testable, falsifiable.
