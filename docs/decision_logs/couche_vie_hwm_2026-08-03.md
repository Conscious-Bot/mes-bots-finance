# Couche vie scellée + HWM arbitré + verdict digue — 03/08/2026

Session Cowork. Quatre items de la Famille 1 tranchés. Ce log est la source des
verbatims ; les valeurs vivent dans `config/policy.yaml` (A3), jamais ici.

---

## 1. Couche vie — déclarations d'Olivier (verbatims)

| champ | déclaration | valeur gravée |
|---|---|---|
| seuil de désengagement | « i think at -18k i wont watch » → « 30K » → « disons donc 35k ça me paraît mieux » | **35 000 €** (niveau affiché) |
| apport mensuel | « apport mensuel 500 euros » | **500 €** |
| plancher de cash | « très peu je préfère lump sum ce que j'ai » | **0 €** + tension déclarée |
| besoin daté | « acheter un appart à Séoul j'ai besoin de 150 k ou de m'en rapprocher le plus vite possible » | **150 000 €**, devise non tranchée |
| horizon | « encore 1 an avant de re-réfléchir à une nouvelle allocation » | **revue 2027-08** ; horizon DÉRIVÉ 5-10 ans (7 central, PROPOSE) |

**Traçabilité de l'ancrage (à garder, c'est une leçon)** : la séquence 18k → 30K
→ 35k s'est produite en trois messages, chaque révision APRÈS une information
nouvelle de ma part. Le premier chiffre (18k) répondait à un delta que j'avais
moi-même affiché — ancrage pur. La question a été reposée dés-ancrée (« quel
NIVEAU affiché ? ») avant d'accepter une valeur. D'où le cliquet gravé :
révision vers le haut libre, vers le bas = écrit daté + 7 jours, interdit en
drawdown.

**Conséquence structurelle** : le seuil de désengagement (où Olivier cesse de
REGARDER) et le backstop (où le système AGIT) sont désormais deux nombres
distincts, et le backstop DOIT être au-dessus — un mécanisme qui se déclenche
là où plus personne ne regarde ne se déclenche pas. R3 : 30 000 → **37 000 €**
(point mort = capital net injecté 36 968 € au 03/08, arrondi). Dérivé, pas
préféré. Révision en drawdown assumée : sens conservateur uniquement.

**Reste MISSING** : `book_share_of_networth` — jamais déclaré.
**Reste NON TRANCHÉ** : la devise de l'objectif Séoul (EUR vs KRW). Le book
n'a qu'une ligne en KRW ; si le won s'apprécie, la cible s'éloigne seule.

## 2. HWM — arbitré : **59 224 € au 22/06/2026** (reconstruction canonique)

Deux sources, balayage QUOTIDIEN comparé sur juin :

| méthode | pic | date | DD au 03/08 (book 49 075 €) |
|---|---|---|---|
| **reconstruction** ledger+prix (`compute_book_performance(asof)`) | **59 224 €** | 22/06 | **−17,1 %** |
| `portfolio_snapshots` (cron mort depuis le 29/07) | 60 258 € | 22/06 | −18,6 % |

La reconstruction est canonique : recalculée depuis le ledger (A8, rien de
dérivé stocké), réconciliée à ±0,0001 €, alors que la table snapshot a des
trous (valeurs figées 13-14/06, arrêt au 29/07). Écart de 1 034 € au pic =
timing intraday du snapshot (21h00 UTC). Même date de pic, même verdict —
la divergence est cosmétique, pas structurelle.

## 3. VERDICT — digue 1 FRANCHIE

DD = −17,1 % (méthode canonique) contre seuil R1 à −15 %. Franchie aussi sous
la méthode snapshot (−18,6 %). **Sans ambiguïté, par les deux méthodes.**
Conséquences telles qu'écrites : gel achats actif, gates de mercredi/vendredi
suspendues, protocole revue.

**Divergence à résoudre** : book annoncé ≈47 000 € (session terminal) vs
**49 075 €** calculé ici aux prix du 03/08 17:28. ~2 000 € d'écart, sans
incidence sur le verdict (les deux sont largement au-delà de −15 %), mais
deux sessions qui citent deux valeurs du même book = L1 violé quelque part.
À trancher par `compute_book_performance` des deux côtés.

## 4. Item 3 — trim +1 716 € : ABSENT du ledger

Dernières transactions = 4 ACHATS du 30/07 12:41 (SPCX ×2, MU, AMZN). Aucune
vente depuis. Donc : proposé non exécuté, OU exécuté côté VM et non syncé
(sync VM→Mac morte — indistinguable depuis le Mac, et cette indistinction est
exactement le défaut pointé par le conseil). **La destination (bloc 4 / XDEW)
ne se décide qu'après avoir tranché l'état.** Pas d'entrée journal tant que le
fait n'est pas établi.

## 5. Item 4 — capteur crowding : deux « ok reco », une correction

- **z-robuste (médiane/MAD)** : OK — validé par la leçon du jour (le R² sur
  niveaux classait au 60ᵉ percentile d'une marche aléatoire ce que je croyais
  être une « régularité anormale »).
- **conjonction stricte LEVEL ET TURN** : OK.
- **fenêtre LEVEL 2 ans : CORRIGÉE → 5 ans** (tout l'historique). Motif :
  4 épisodes de DD ≥15 % en 5,2 ans sur le panier semi — une fenêtre de 2 ans
  n'en capture qu'un ou deux, et un percentile sur 1-2 observations reproduit
  le défaut L16 (cf. seuil Chine SNPS écrit 5 jours après matérialisation).
  Le 20-40j de décélération (TURN) est conservé tel quel.

## 6. Règle de financement gravée (compagne de `cash_floor_eur: 0`)

Capital existant (~49 k) = conviction, lump sum, on n'y touche pas.
**Apport mensuel (500 €) = ballast, DCA, automatique.** Les deux cessent de se
disputer le même euro ; le ballast se construit sans une seule vente (~12 %/an
du book). Produits de trim → bloc 4, à activer quand l'item 3 est tranché.
