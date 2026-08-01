# PRESAGE — HANDOFF MÉTHODE (v1, 01/08/2026)

> Document autoportant destiné à une revue critique externe. Il décrit **comment on
> procède**, pas ce qu'on détient. Les faiblesses connues sont pré-enregistrées (§13) :
> elles sont le vrai objet de la revue.

---

## 1. Objet, échelle, contraintes

Book actions personnel d'un investisseur particulier (~48 k€, ~22 lignes, horizon
« à vie »), géré comme une institution mais **sans les moyens d'une institution** :
un décideur, pas d'équipe, pas de données payantes, pas de levier, pas de dérivés.
Système logiciel maison (Python/SQLite, VM Hetzner + poste Mac) qui journalise,
surveille et rend des comptes. Contraintes de style assumées : vérité > déférence,
premiers principes, second ordre, appeler la médiocrité y compris celle du système.

**Ce que le système est** : un instrument de discipline et de mémoire.
**Ce qu'il n'est pas** : un générateur d'alpha. Aucun modèle n'y pilote de décision.

## 2. Le principe porteur

Aucun nombre ne doit être plus confiant que son évidence. Décliné :
- **fail-closed** : donnée manquante ou périmée → `None` + état honnête, jamais une
  valeur plausible fabriquée (jamais « dernière valeur connue » pour un gel/dégel) ;
- **triple de tout datum** : (valeur, asof, source) ;
- **pre-registration** : toute claim (thèse, trigger, cible, seuil) est écrite et
  datée AVANT l'événement qui la jugera ;
- **état honnête** : « je ne sais pas / stale / edge non prouvé » est une sortie
  valide et fréquente. Un rapport court est préféré à un rapport complet inventé.

## 3. Architecture documentaire (4 piliers + navigation)

| Doc | Rôle | Question à laquelle il répond |
|---|---|---|
| `QUALITY_BAR` | base non négociable | qu'est-ce qu'un fait acceptable ? |
| `NORTH_STAR_QUALITE` | sélection | qu'a-t-on le droit d'acheter ? (7 critères, watchlist gated) |
| `RISK_FRAMEWORK` | taille et survie | combien, et jusqu'où peut-on perdre ? |
| `decision_logs/*` | jurisprudence | qu'a-t-on décidé, quand, pourquoi, jugé comment ? |
| `LESSONS.md` (L1-L34) | doctrines transversales | quelle erreur ne doit plus se répéter ? |
| `CANONICAL_MAP` | navigation + topologie | où va ma nouvelle fonctionnalité / donnée ? |
| `GLOSSARY` | vocabulaire figé | comment ça s'appelle ? (source unique) |

Règle : **une seule source par notion** (L1). Toute reformulation ailleurs est une
dette, pas une commodité.

## 4. Cycle de décision (le cœur)

Toute décision passe par deux questions, dans cet ordre, jamais fusionnées :

- **Q1 — la thèse est-elle intacte ?** Jugée UNIQUEMENT contre les
  `invalidation_triggers` **pré-enregistrés** de cette thèse. Un trigger a fired ou
  non. L'opinion du jour, le cours, le sentiment ne sont pas des inputs.
- **Q2 — le poids est-il correct ?** Poids réel vs cap dérivé (conviction, facteur,
  devise, poche). Rightsize, jamais exit par Q2.

**Le prix n'est jamais un input direct.** Un stop est un *point de décision forcé*
(exécuter OU écrire une révision datée sous 24 h), jamais un ordre automatique, jamais
un limbo. Une thèse (variant + falsifieurs + cible + stop) est écrite **avant** l'ordre.

Chaque thèse porte aussi : un **typage** (compounder | trade de cycle | venture |
ballast), un **tag plateau** (vit du NIVEAU d'activité vs de son ACCÉLÉRATION), un
**facteur** de rattachement.

## 5. Règles d'entrée

**§XI — preuve de monétisation** (jugée sur le capex MARGINAL, pas le business legacy) :
- FINANCEMENT : A autofinancé · B dette/dilution/vendor financing (drapeau rouge,
  acceptable si adossé à une preuve contractée type project finance take-or-pay) ;
- PREUVE : 1 contracté (RPO, take-or-pay, backlog auditable) · 2 vendu (revenu
  externe croissant) · 3 claim-only (« ROIC interne supérieur ») = **FAIL** ;
- entrée/bump interdits si B ou 3, sauf typage venture explicite.

**NORTH_STAR — 7 critères** pour le cœur long terme : irremplaçabilité structurelle
(≥10 ans pour substituer) · pricing power prouvé **à travers un downturn** ·
économie du réinvestissement (ROIC >> WACC ET piste longue) · le temps travaille pour
elle · anti-fragilité aux forces séculaires · allocation du capital prouvée sur une
décennie · **falsifiabilité** (thèse auditable livrée AVEC son falsifieur).
Chaque nom de la watchlist porte une **gate de prix chiffrée** — la qualité est connue
de tous, le seul edge est le prix.

**Condition d'exception (c')** — pour tolérer un FAIL §XI au-delà de la taille venture :
la valeur des activités déjà commerciales (revenus externes, marge brute positive,
hors R&D des programmes futurs) couvre ≥25 % de la capitalisation, ET au moins la
moitié de cette couverture provient d'actifs dont la valorisation **ne dépend pas du
régime en question** (anti-circularité).

## 6. Sizing (l'état de l'art du système, et son point faible)

Doctrine : **la taille dérive de la distribution des résultats, pas de la catégorie.**

```
TAILLE = min( quart_Kelly(distribution) × d_observabilité × d_corrélation,
              plafond_dur 3 % (venture),
              budget_poche restant (venture + illiquide ≤ 5 % du book) )

quart_Kelly    : f* = p/l − q/b, puis × 0,25 (erreur d'estimation — surparier ruine,
                 sous-parier coûte peu)
d_observabilité: 1,0 public+milestones vérifiables · 0,6 partiel · 0,3 opaque
d_corrélation  : (1 − ρ) vs le facteur dominant (Kelly suppose l'indépendance ;
                 les paris corrélés se dimensionnent en CLUSTER)
règle d'arrêt  : f* ≤ 0 → pas de position
```
La fonction **rend une fourchette, pas un chiffre** ; le portefeuille choisit bas,
milieu ou haut selon sa prudence. Pour le cœur (hors venture), caps par conviction
compressés tant que N décisions < 100 : c5 ≤7 % · c4 ≤5,5 % · c3 ≤4 % · c2 = 0.

⚠ **Faiblesse ouverte, non résolue (voir §13)** : l'origine des entrées (p, gain,
perte) reste une estimation informée, non dérivée. Kelly est brutalement sensible à
p (25 % → 0,9 % ; 35 % → 2,8 %). Piste en cours : faire dériver p d'une grille de
milestones scorés (exécution, moat, visibilité, gouvernance, risque de valorisation),
et remplacer le couple gain/perte par un triptyque bear/base/bull → espérance.

## 7. Le risque, en 4 couches

1. **Ligne** : thèse signée avant l'ordre · stop structurel (point de décision) ·
   risque € par ligne ≈ poids × distance stop ≤ ~1 % du book.
2. **Facteur** (un facteur = un DRIVER de demande, pas un secteur GICS) : cap sur le
   facteur dominant, **à cliquet descendant** — il baisse par apports et migration,
   **jamais par vente forcée**, sauf breach par appréciation persistant 4 semaines
   (alors : trim-to-cap, jamais sous le cap — anti lock-in). Caps additionnels :
   sleeve accélération, devise, venture+illiquide, ballast minimum.
3. **Book** : échelle de drawdown **mécanique** depuis le HWM — R1 gel des achats ·
   R2 tribunal complet forcé sous 7 j · R3 backstop (valeur plancher, 2 closes) →
   dé-risque à ~50 % avec ordre de coupe pré-défini, zéro re-délibération. Hystérésis
   au dégel. Journal append-only.
4. **Vie** (fondation, actuellement VIDE) : horizon, apports, besoins datés, part du
   patrimoine. Sans elle, tous les nombres ci-dessus sont des placeholders plausibles.

**Tail assumé et nommé** (Taïwan) : le seul scénario qui *gappe* sous le backstop sans
passer par les paliers. Décision explicite : non hedgé (pas d'options), mitigé
uniquement par ballast contracté + cash + zéro levier. Nommer un trou vaut mieux
qu'un hedge de façade.

Lecture directrice (Griffin) : partir de la **perte tolérable** et en déduire
l'exposition, plutôt que l'inverse.

## 8. Ce qu'on refuse explicitement (décisions, pas oublis)

Levier : jamais · options/hedges : non (coût + complexité + skill de timing) ·
stops auto-exec broker : non (décision forcée > automatisme aveugle) · régime-guessing :
non (les limites réagissent à des observables : DD, poids, closes) · fiscal : exclu de
toute considération d'investissement (décision du gérant) · recommandations d'un LLM :
jamais autoritatives.

## 9. Les overrides (le mécanisme le plus important)

Le système **n'interdit pas** au gérant de contredire ses règles. Il exige que la
contradiction soit **écrite, datée, motivée, avec contrefactuels armés** et résolution
à +30/60/90 j. Trois sorties possibles face à une règle qui gêne :
1. honorer la règle ; 2. **override nommé** (la règle tient, l'exception est loggée) ;
3. **amendement de doctrine** (la règle change pour tous les cas futurs, avec
   conditions cumulatives et clause anti-érosion : une seule exception active à la fois).
**Interdit : la contradiction silencieuse.** C'est le seul résultat que le système
existe pour empêcher.

Le juge n'est ni le gérant ni le système : c'est le **resolver** (track record daté)
qui dira à +30/60/90 j si les overrides battent les règles. Si oui, les règles
s'amendent **par écrit** — jamais par érosion.

## 10. Ingénierie (les doctrines qui coûtent cher quand on les oublie)

- **verify-before-patch** : lire la vraie source/donnée avant tout patch, jamais
  deviner ; `assert count==1` avant tout remplacement ; gates chaînées (lint + import
  + reload) après chaque patch.
- **L33 — preuve, pas confiance** : une tâche d'agent n'est DONE que sur vérification
  **déterministe et indépendante du déclarant**. « L'agent dit que c'est fait » n'est
  pas un stopping condition ; « le SELECT retourne 14 lignes » en est un.
- **L34 — un écrivain déclaré par store** : écrire des données *correctes* au *mauvais
  nœud* est un incident même réussi. Topologie des écritures dessinée une fois
  (source de vérité, réplique read-only, forensics) ; rôles imposés par le harness
  (garde `ROLE=replica`), jamais par la vigilance.
- **L27 — cohérence mécanique > vigilance** : un rail qu'on doit se rappeler d'appliquer
  n'existe pas.
- **L17 — déclaratif vs live state** : configs versionnées en YAML + validation ;
  état vivant en table append-only ; jamais mélanger.
- **L15/L16** : fail-closed sur le scoring ; aucun seuil fabriqué (tout tuning date
  ses splits train/val/oos AVANT le tuning).
- Monitors : pattern canonique unique (journal append-only + classify pur +
  check_all_transitions + 7 tests dont le test anti-double-instrumentation).
- Rituel de clôture systématique (état de session + backlog + commit) : cinq minutes
  qui économisent trente minutes de ré-onboarding.

## 11. Pipeline d'information (digest)

Ingestion horaire → scoring → digest quotidien (radar terse) + synthèse hebdomadaire
(essai narratif). Garde-fous : **interdiction d'ordres de trade** par le LLM (prompt
durci + filet mécanique post-rendu qui flagge sans censurer) · sections déterministes
(catalysts datés, réactions de prix post-événement) calculées sans LLM · contexte book
généré depuis la base à chaque run (jamais écrit à la main) · questions ouvertes du
gérant en YAML, vers lesquelles les signaux sont routés.

Correctif majeur en cours (après audit de 3 éditions) : **« urgent » devient mécanique,
plus électif** — un signal n'atteint ce rang que si un fait extrait touche un trigger
pré-enregistré, ou qu'un niveau est franchi, ou qu'un catalyst est à <48 h.
« 0 urgent » est un résultat normal. Plus : clustering par claim (N sources répétant
un même fait = 1 facteur, pas N), date du fait extraite (≠ date de publication),
niveau de vérifiabilité (primaire/secondaire/opinion), enum de biais fermée.

**Hiérarchie de tri des sources** (règle personnelle) : chiffres + mécanisme +
falsifiable = ça mérite un marqueur. Adjectifs + certitude + « cette fois c'est
différent » (dans un sens ou dans l'autre) = scroll.

## 12. Boucle d'apprentissage

Biais **mécanisés**, pas seulement nommés : `lock_in` (vendre les gagnants trop tôt)
détecté par hook post-vente avec résolution différée ; `fomo_greed` (ne pas réduire
quand la discipline le disait) sur canaux dédiés. Toute leçon attrapée deux fois
devient une doctrine L# numérotée, avec grep target — jamais un commentaire dispersé.
Les décisions du gérant sont scorées par le resolver au même titre que celles du
système.

## 13. FAIBLESSES CONNUES — pré-enregistrées pour la revue

1. **Origine des probabilités** (§6) : Kelly reçoit des entrées estimées, pas dérivées.
   L'arbitraire a été déplacé, pas éliminé. **Le point le plus vif aujourd'hui.**
2. **Couche vie vide** : horizon, apports, besoins, part du patrimoine inconnus →
   caps, backstop, paliers et plafonds venture sont plausibles mais non calibrés.
3. **N trop petit** : quelques dizaines de décisions résolues. Le resolver n'a AUCUNE
   puissance statistique. Tout « edge » revendiqué serait du bruit.
4. **Aucun benchmark** : la performance n'est comparée à rien (ni indice, ni panier
   naïf). Risque majeur de se raconter une histoire favorable.
5. **Concentration factorielle ~65 %** assumée sur un seul driver, avec un cap qui ne
   descend que lentement (par apports). Le book reste, structurellement, un pari.
6. **Sur-ingénierie possible** : ~20 documents de doctrine et un pipeline complet pour
   un book de taille modeste. Le rapport coût cognitif / capital géré doit être
   attaqué — la réponse « ça se transpose quand le capital grandit » est peut-être
   une rationalisation.
7. **Doctrines écrites après les incidents** : biais du survivant sur le corpus L#
   (on grave ce qui a fait mal, pas ce qui pourrait faire mal).
8. **Dette technique connue** : cure de conversion de devises sur d'anciens trades ;
   ledger historiquement écrit au mauvais nœud (corrigé, mais preuve encore due) ;
   monitors de facteur et d'échelle DD spécifiés mais non implémentés.
9. **Le digest produit encore des erreurs d'analyse** (causalité inversée, échos
   comptés comme convergence) — corrigées par audit humain, pas par le système.
10. **Asymétrie effort/décision** : énormément de doctrine produite pour un nombre de
    décisions faible. Le risque est un système qui devient sa propre fin.

## 14. Ce que j'aimerais qu'un critique attaque en priorité

- La faiblesse n°1 : peut-on dériver `p` d'une grille de milestones sans reconstruire
  l'arbitraire à l'étage du dessus ?
- La n°4 : quel benchmark honnête pour un book concentré, à horizon long, avec apports ?
- La n°6 : ce système est-il proportionné ? Que faudrait-il **supprimer** ?
- Le cycle Q1/Q2 : est-il réellement robuste, ou déplace-t-il simplement le jugement
  vers la rédaction des triggers (qui sont eux-mêmes écrits par le décideur) ?
- Les overrides : un mécanisme qui autorise la contradiction écrite est-il une
  soupape saine, ou une porte d'érosion à combustion lente ?
