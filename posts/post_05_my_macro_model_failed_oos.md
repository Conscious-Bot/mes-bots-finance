# Post #05 — Mon modèle macro a échoué hors échantillon. Voici pourquoi je le publie.

*Français d'abord, English below.*

---

## 🇫🇷 Quand l'edge prédictif explose et que ce n'est pas une catastrophe

*Le verdict honnête d'un backtest qui devait valider un modèle wirable en production — et qui l'a démoli.*

---

### Le contexte court

PRESAGE est un outil d'intelligence de portefeuille self-hosted. Une de ses briques est un **composite macro V3** : 13 indicateurs (VIX, courbe 10s-2s, BTC drawdown 180j, FedBalance YoY, MfgIP, etc.) agrégés en un score 0-200 qui détermine une **phase** (P1 stable / P2 stress / P3 alerte / P4 crise). L'idée : le sizing des positions s'ajuste à la phase. Phase 4 = -50% de cible exposition. Phase 1 = exposition pleine.

V3 avait été livré le 29 mai avec une affirmation : « validé OOS 7/8 dates non-anchor ». Le commit message le disait. Mais le code de validation OOS **n'existait pas** dans le repo. C'était une mesure manuelle, non reproductible.

Hier, 2 juin, j'ai écrit le validator. Et j'ai ajouté 4 dates HOLDOUT vierges, jamais utilisées pour le tuning :

- 2017-12-15 : Goldilocks 2017, VIX 9.5 record low → label P1
- 2018-10-29 : sell-off octobre 2018, S&P −10%/mois, VIX 27 → label P3
- 2020-03-12 : circuit breakers COVID, VIX 75 → label P4
- 2024-04-15 : Q1 2024 sticky CPI, USDJPY 154 → label P2

### Le verdict

**HOLDOUT 4/8 (50%)**, en dessous du seuil 75% que je m'étais fixé pour autoriser le wire en production.

Les 4 fails :
- Les 3 dates labelées P1 (calmes) → V3 dit systématiquement **P2**, jamais P1
- Le sell-off d'octobre 2018 (P3 indéniable) → V3 dit **P2**

Le pattern n'est pas du bruit, c'est **structurel** : V3 a un biais centriste P2. Le composite ne génère jamais de P1 (Goldilocks 2017 avec VIX 9.5 → P2 chez V3, score 36) et sous-estime certains stress nets.

Diagnostic probable :
- BTC_drawdown180 injecte un floor de stress structurel (BTC est souvent en drawdown même sans stress macro)
- FedBalance_yoy reste négatif en QT permanent depuis 2022 → biais P2 mécanique
- La frontière P2→P3 est trop haute (manque d'indicateur de vélocité)

### Pourquoi je publie ça

Trois raisons.

**1. Honnêteté forcée.** Un commit message qui dit « validé 7/8 » sans code reproductible derrière, c'est du *resulting* (Annie Duke). On juge la décision par le résultat affiché, pas par le processus. J'avais écrit ça moi-même il y a 4 jours. C'est exactement ce que je critique chez les autres. Publier le verdict empirique, c'est le seul moyen de ne pas pouvoir tricher avec soi-même à la prochaine itération.

**2. Le wedge n'est pas là où je l'avais mis.** PRESAGE a deux piliers : (a) **calibration prédictive** — peut-on assigner des probabilités correctes aux scénarios macro ? (b) **discipline comportementale** — peut-on mécaniser un miroir qui attrape l'investisseur en train de vendre ses winners trop tôt ?

Le V3 fail attaque le pilier (a). Mais le pilier (b) ne dépend pas de (a). Le détecteur de biais lock_in (livré il y a deux jours) attrape un vendeur de winner que le composite macro dise P1, P2, P3 ou P4. La discipline marche indépendamment de la prédiction.

Donc V3 qui casse = une raison de plus d'**enterrer le récit alpha prédictif** et de m'appuyer entièrement sur la discipline mesurable. C'est plus facile à défendre, c'est plus défensible empiriquement, et c'est ce que je faisais déjà — sans le savoir clairement.

**3. La prescription des 3 stress-tests.** J'ai fait trois exercices de critique adversariale du projet ces dernières semaines (un audit code, un audit esthétique, un stress test incubateur/investisseur/user). Ils convergent tous sur la même prescription : **users réels + track record public, pas plus de build interne**. Produire de l'analyse est le geste confortable. Sortir du contenu honnête est le geste inconfortable. Ce post est le geste inconfortable.

### Et V4 ?

V4 = refaire un modèle qui vient d'échouer OOS. C'est l'endroit à plus faible valeur où dépenser du temps maintenant. Post-wedge au mieux, c'est-à-dire jamais probablement.

### Ce qui suit

10 juin : J-day. 5 prédictions probabilistes résolues à J+28 = premier vrai Brier mesurable. Ça je publie aussi, quel que soit le verdict.

10 juillet (J+30) : les premiers `bias_events` lock_in/fomo_greed résolus avec leur delta signed EUR. Je publie le tableau brut.

Si vous voulez recevoir les prochains posts, ils seront sur **presage.pro/track** (à venir) ou en RSS quand le hosting sera prêt. Pour l'instant, c'est en repo public ouvert : [github.com/...]

---

## 🇬🇧 When the predictive edge collapses and it's not a disaster

*The honest verdict of a backtest that was supposed to validate a model wirable to production — and tore it down.*

---

### Short context

PRESAGE is a self-hosted portfolio intelligence tool. One of its bricks is a **macro composite V3**: 13 indicators (VIX, 10s-2s curve, BTC 180d drawdown, FedBalance YoY, MfgIP, etc.) aggregated into a 0-200 score that determines a **phase** (P1 stable / P2 stress / P3 alert / P4 crisis). The idea: position sizing adjusts to the phase.

V3 had shipped May 29 with a claim: "validated OOS 7/8 non-anchor dates." The commit message said so. But the OOS validation code **didn't exist** in the repo. It was a manual, non-reproducible measurement.

Yesterday, June 2, I wrote the validator. I added 4 virgin HOLDOUT dates, never used for tuning:

- 2017-12-15: Goldilocks 2017, VIX 9.5 record low → label P1
- 2018-10-29: October 2018 sell-off, S&P −10%/month, VIX 27 → label P3
- 2020-03-12: COVID circuit breakers, VIX 75 → label P4
- 2024-04-15: Q1 2024 sticky CPI, USDJPY 154 → label P2

### Verdict

**HOLDOUT 4/8 (50%)**, below the 75% threshold I'd set as the wire-to-production gate.

The 4 fails:
- All 3 P1 dates (calm) → V3 systematically says **P2**, never P1
- October 2018 sell-off (unambiguous P3) → V3 says **P2**

The pattern isn't noise, it's **structural**: V3 has a centrist P2 bias. The composite never generates P1 (Goldilocks 2017 with VIX 9.5 → P2 at V3, score 36) and underestimates net stresses.

Probable diagnosis:
- BTC_drawdown180 injects a structural stress floor (BTC is often in drawdown even without macro stress)
- FedBalance_yoy stays negative under permanent QT since 2022 → mechanical P2 bias
- P2→P3 boundary too high (missing velocity indicator)

### Why I publish this

Three reasons.

**1. Forced honesty.** A commit message that says "validated 7/8" without reproducible code behind it is *resulting* (Annie Duke). You judge the decision by the displayed result, not by the process. I wrote that myself 4 days ago. It's exactly what I criticize in others. Publishing the empirical verdict is the only way to make cheating impossible for next iteration.

**2. The wedge isn't where I'd put it.** PRESAGE has two pillars: (a) **predictive calibration** — can we assign correct probabilities to macro scenarios? (b) **behavioral discipline** — can we mechanize a mirror that catches the investor selling winners too early?

V3 fail attacks pillar (a). But pillar (b) doesn't depend on (a). The lock_in bias detector (shipped two days ago) catches a winner-seller regardless of whether the macro composite says P1, P2, P3 or P4. Discipline works independently of prediction.

So V3 breaking = one more reason to **bury the predictive alpha narrative** and lean entirely on measurable discipline. Easier to defend, more empirically defensible, and that's what I was doing already — without knowing it clearly.

**3. The prescription of 3 stress-tests.** I ran three adversarial critique exercises of the project recently (code audit, aesthetic audit, incubator/investor/user stress test). They all converge on the same prescription: **real users + public track record, no more internal build**. Producing analysis is the comfortable move. Publishing honest content is the uncomfortable move. This post is the uncomfortable move.

### What about V4?

V4 = redoing a model that just failed OOS. Lowest-value place to spend time right now. Post-wedge at best — probably never.

### What's next

June 10: J-day. 5 probabilistic predictions resolved at J+28 = first real measurable Brier. I publish that too, regardless of verdict.

July 10 (J+30): first `bias_events` lock_in/fomo_greed resolved with signed delta EUR. I publish the raw table.

If you want to receive future posts, they'll be at **presage.pro/track** (coming) or via RSS when hosting is ready. For now, it's an open public repo: [github.com/...]
