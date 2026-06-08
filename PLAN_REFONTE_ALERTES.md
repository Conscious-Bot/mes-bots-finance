# Refonte des alertes — de l'alarmisme à la vigilance calibrée

> Synthèse-plan. Objectif : tuer le crying-wolf **sans** glisser dans la complaisance (préférence asymétrique : vigilance > complaisance). Et remplacer le rouge/jaune/vert (trop grossier) par une représentation précise. Cook with care.

## 1. Le constat (acté)

La majorité des indicateurs crient au loup. Deux racines :
- **Seuils non-gagnés** : « rouge si asym < 1× », « P3 si VIX > 20 », « LATE si… » = nombres ronds / intuition, jamais validés contre « ce niveau a-t-il *réellement* précédé le mauvais outcome ? ». Statistiquement : précision basse, faux-positifs élevés.
- **État, pas delta** : « LATE » est vrai depuis un an → toujours rouge → **information nulle**. Le signal n'est jamais l'état persistant, c'est le *changement*.

Le coût, et c'est pourquoi c'est *le* problème central : **chaque fausse alarme t'entraîne à ignorer toutes les alarmes.** Le BTC qui crie crise empoisonne la crédibilité du spread HY bien calibré à côté. Le crying-wolf est négatif, pas neutre.

## 2. La résolution de TA tension (le cœur — vigilance ET non-alarmisme)

Tu crains qu'« arrêter de crier au loup » = « devenir complaisant ». **Faux, parce que ce sont deux axes différents :**

- **Vigilance = recall** (sensibilité : attraper les vraies dégradations). Tu veux ça HAUT.
- **Crying-wolf = faux positifs** venant du **bruit** et de **l'état persistant** (précision basse). Tu veux ça BAS.

Le crying-wolf ne vient PAS d'un excès de recall — il vient d'une **précision basse sur des variables sans skill** (BTC, VIX-niveau, LATE-constant). Donc la cure n'est pas « moins d'alarmes » (ça, ce serait la complaisance) — c'est :

> **Être PLUS sensible, sur MOINS de variables, mais les BONNES.** Concentrer la vigilance sur le signal skill-validé ; la retirer du bruit.

Honoré par l'**asymétrie de perte** (manquer une crise coûte >> une fausse alarme) :
- **Sur les gauges high-skill** (spreads qui s'élargissent, MOVE qui monte, crowding qui accélère, asymétrie qui se comprime) → **hair-trigger, biais vers le recall**. C'est *là* qu'on durcit la vigilance, qu'on accepte quelques faux positifs. C'est ton « légèrement durcir ».
- **Sur le bruit** (BTC drawdown, VIX-niveau, RSI-comme-stress, état persistant) → **zéro alarme**. Aucune vigilance perdue (ils n'en apportaient aucune), seulement de la crédibilité regagnée.

Résultat : tu deviens **plus vigilant sur ce qui compte et silencieux sur ce qui ne compte pas.** Les deux à la fois. La vigilance se *concentre*, elle ne baisse pas.

## 3. Le droit d'alarmer (la règle transversale)

> Un indicateur n'a le droit de signaler que si **(a)** son niveau est calibré pour prédire l'outcome **au-dessus du taux de base**, ET **(b)** il se déclenche sur le **delta/la surprise**, pas l'état persistant.

Conséquences dures :
- **Défaut = calme.** Le signalement est *rare par construction*.
- **Test de santé** : si >~20% des lignes/indicateurs signalent simultanément → ce n'est pas le monde en crise, c'est **la calibration cassée**. (Aujourd'hui : « CRISE » avec spreads/MOVE/banques calmes = faux positif manifeste.)
- **États persistants** (cycle LATE sur 85% du book) → promus en **contexte book-level**, retirés des lignes. Un constant n'est pas une alarme.

## 4. Tuer le rouge/jaune/vert (trop grossier — tu as raison)

Pourquoi R/Y/G échoue : 3 buckets discrets → perd la magnitude et la trajectoire ; implique une *certitude* (« c'est ROUGE ») là où il faut une probabilité ; pèse pareil un signal high-skill et un noise. Remplacement :

**Composite → une PROBABILITÉ CALIBRÉE + une TRAJECTOIRE, pas une couleur.**
- Ex. « **P(régime de stress, 3M) = 28% ↑ (de 19%)** ». Continu, calibré (ECE→0, 28% veut dire 28%), porte le delta, et **respecte ton asymétrie** : tu poses TON seuil d'action selon ta perte (vigilant → agis à 25%, pas à 60%). 28% n'est pas « panique », c'est « élevé, surveille » — l'inverse du crying-wolf.

**Par indicateur → une jauge fine, pas un point coloré :**
- Position sur sa **propre distribution calibrée** (percentile / z mappé à l'outcome forward) — « 30Y au 78e pct, où le drawdown forward médian était −X% ».
- **Flèche de delta** (direction + vitesse) — le truc qui compte.
- **Poids visuel = skill × fraîcheur** — un signal high-skill frais domine visuellement un noise stale.

La couleur, si elle reste, n'encode plus l'état mais **l'asymétrie de conséquence** (un signal à downside catastrophique reste visible même à niveau modéré = vigilance) — secondaire, jamais l'information primaire.

## 5. Le plan, concrètement

1. **Sélection** — *drop* le bruit (BTC drawdown, VIX-primary, RSI-as-stress) ; *garder* les high-skill (spread HY, MOVE, stress bancaire, courbe, impulsion crédit/liquidité, crowding-delta, compression d'asymétrie) ; *dégrader* le book-specific (USD/JPY → risque *book*, pas crise *macro*).
2. **Skill-weighting** (cf `CALIBRATION_DOCTRINE`) — poids gagné, jamais tapé ; shrink vers prior à petit-N ; doit battre l'équipondéré OOS.
3. **Séparer les échelles de temps** — ne pas fusionner un BTC quotidien et un bilan Fed trimestriel dans un score instantané (exploite tes tags M&L / BANK / SLOW).
4. **Delta-not-state** — chaque indicateur signale sur le *changement* ; les états persistants → contexte book-level.
5. **Calibrer contre l'outcome** — mapper chaque niveau à `P(outcome | niveau)` sur l'historique ; **mesurer l'ECE du monitor**.
6. **Représentation** — composite = probabilité calibrée + trajectoire ; par-indicateur = jauge percentile + delta + poids-skill ; défaut calme.
7. **Le gouverneur** (MACRO IMPACT ON BOOK : hedge Japon 23%, semis 64%…) **reste** — c'est la bonne partie, l'actionnable. Son urgence se recalibre automatiquement sur la nouvelle lecture honnête.

## 6. La méthode (le *comment*, pas juste le quoi)

- **Backtest par indicateur** : `P(drawdown | niveau)` sur l'historique, **splits temporels L16**, zéro look-ahead.
- **Choisir le seuil au point d'asymétrie de perte** : sur les high-skill, optimiser le recall (manquer coûte plus) ; sur le reste, exiger une précision élevée avant de laisser signaler.
- **ECE du composite → 0** ; bande coverage-calibrée (cf doctrine).
- **Rareté testée** : « >20% en alarme » est un test qui échoue le build.

## 7. Le test ultime (le verdict de calibration)

Rejoue le monitor sur l'historique et construis sa **matrice de confusion** : combien de fois a-t-il crié crise ? combien de crises réelles ont suivi ? combien manquées ?
- Beaucoup d'alarmes, peu de crises → crying-wolf (l'état actuel).
- L'asymétrie qu'on veut : **peu de faux négatifs** (on rate rarement une vraie), **faux positifs tolérés seulement sur les high-skill** (jamais sur le bruit).
- Aujourd'hui, « CRISE phase 4/4 » avec spreads à 274bp et MOVE à 75 = un faux positif que la matrice exposerait immédiatement. **C'est ça, le point de départ mesurable.**

> En une phrase : on ne baisse pas la garde, on **la concentre** — hair-trigger sur peu de signaux à fort skill, silence total sur le bruit, signalement sur le *delta* calibré contre l'outcome réel, et une **probabilité + trajectoire** au lieu d'un feu tricolore. Plus vigilant *et* plus crédible, parce que le rouge redevient rare et *mérité*.
