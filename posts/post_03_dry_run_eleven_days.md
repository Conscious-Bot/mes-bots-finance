# Post #03 — version bilingue

*Français d'abord, English below. Mêmes choix : la preuve avant l'annonce ; zéro pitch ; « je ne suis pas développeur » assumé.*

---
---

## 🇫🇷 Onze jours avant le moment de vérité, je sais déjà

*Pourquoi vérifier ce qu'on va publier — avant de le publier.*

---

J'ai un système qui prédit des mouvements de marché. Il a enregistré 40 prédictions qui se résolvent toutes le 10 juin 2026. C'était censé être mon premier vrai point Brier — la mesure de calibration qui devait dire si mes convictions valent quelque chose.

Onze jours avant ce moment, j'ai simulé la résolution. Pas pour la commiter — juste pour la voir.

Voici le résultat :

```
40 prédictions
  correct    :  8 (20 %)
  incorrect  : 13 (32 %)
  neutral    : 19 (48 %)
  
Brier moyen : 0,295
Baseline trivial (prior 0,5 constant) : 0,250
Accuracy bull/bear : 8/21 = 38 %
```

Le système prédit avec une confiance de 0,63. Il a raison 38 % du temps. **Surconfiant, mal calibré, et empiriquement pire qu'un prior à pile-ou-face**.

Si je publie ce chiffre tel quel le 10 juin, c'est l'opposé d'un track record. C'est la preuve documentée que mon système ne sait pas prédire.

---

Je ne suis pas développeur. L'IA a écrit la quasi-totalité de ce code. Le 10 juin n'a pas changé : le moment de vérité reste calendrier-dur. Ce qui change, c'est que je l'ai vu venir.

Quelques semaines avant, j'avais déjà diagnostiqué la cause : un plafond codé en dur dans la formule de probabilité, des sources de crédibilité figées à 0,50 par défaut, un filtre qui ne laissait passer que les opinions à scoring élevé. Conclusion analytique : *« le batch 10 juin produira un mono-bucket de probabilités à 0,63, ça ne vaudra rien comme calibration »*.

Mais analyser un défaut et le voir réalisé sont deux choses différentes. Le dry-run J-11 transforme la prédiction théorique en mesure. Le diagnostic devient un fait.

C'est inconfortable. C'est aussi exactement ce qu'un système prétendant à la calibration doit faire — y compris contre lui-même. Le pire serait de découvrir le 10 juin un Brier honteux et de le maquiller, ou de ne pas le publier, ou de pivoter le narratif au dernier moment. La pré-mesure rend ces trois sorties impossibles.

---

Ce qui reste à dire le 10 juin n'est plus *« voici mon track record »*. C'est : *« voici la mesure d'un système V1 mauvais, que j'ai vu venir, que j'ai déjà remplacé par un V2 sur cohortes futures, et que je publie quand même parce qu'un système de calibration qui cache ses mauvais chiffres n'est pas un système de calibration. »*

Le V2 produit déjà des probabilités étalées sur trois buckets, sait descendre sous 0,50 (bearish), force le `watch` quand l'évidence ne justifie pas un appel directionnel falsifiable. Les premiers tests synthétiques montrent un plafond cassé à 0,77 sur évidence forte, un plancher cohérent autour de 0,40 sur évidence inverse, un taux de refus de scoring (`watch`) de 75 % qui reflète honnêtement la qualité moyenne du pipeline d'entrée. Mais les 40 prédictions du 10 juin ont été figées sous V1. On ne ré-écrit pas un track record après coup.

---

Le système n'a pas seulement un mauvais Brier qui arrive. Il a un mauvais Brier qui arrive **et qu'il sait déjà**. Cette deuxième propriété est celle qui doit voyager. Le premier chiffre est honteux ; le second est l'actif.

Onze jours, c'est assez pour écrire les conditions de publication avant de connaître le résultat — pour pré-engager honnêteté plutôt qu'avoir à choisir à chaud. C'est ce qu'un système de calibration honnête fait par construction. Si vous découvrez votre propre échec en même temps que votre audience, vous avez perdu la partie sur laquelle vous prétendiez gagner.

0,63 avait l'air parfait il y a six semaines. 0,295 en sera la preuve dans onze jours. Entre les deux, j'ai eu le temps de vérifier. Le reste est tactique.

---
---

## 🇬🇧 Eleven Days Before Truth, I Already Know

*Why you check what you're about to publish — before you publish it.*

---

I have a system that forecasts market moves. It logged 40 predictions, all resolving on June 10, 2026. That was supposed to be my first real Brier point — the calibration measure that would say whether my convictions are worth anything.

Eleven days before, I simulated the resolution. Not to commit it — just to see it.

Result:

```
40 predictions
  correct    :  8 (20%)
  incorrect  : 13 (32%)
  neutral    : 19 (48%)
  
Mean Brier : 0.295
Trivial baseline (constant 0.5 prior) : 0.250
Bull/bear accuracy : 8/21 = 38%
```

The system predicts with 0.63 confidence. It's right 38% of the time. **Overconfident, miscalibrated, and empirically worse than a coin-flip prior.**

If I publish that number as-is on June 10, it's the opposite of a track record. It's documented proof that my system can't predict.

---

I'm not a developer. AI wrote almost all of this code. June 10 hasn't moved: it's a calendar-hard deadline. What's changed is that I saw it coming.

A few weeks earlier, I'd diagnosed the cause: a hard-coded cap in the probability formula, source credibilities stuck at 0.50 default, a filter that only let high-score opinion signals through. Analytical conclusion: *"the June 10 batch will produce a mono-bucket of probabilities around 0.63, it won't be worth anything as calibration."*

But diagnosing a defect and seeing it realized are different things. The J-11 dry-run turns a theoretical prediction into a measurement. The diagnosis becomes a fact.

It's uncomfortable. It's also exactly what a system claiming to calibrate must do — including against itself. The worst outcome would be discovering a shameful Brier on June 10 and either dressing it up, not publishing it, or pivoting the narrative at the last minute. Pre-measuring makes all three of those impossible.

---

What's left to say on June 10 is no longer *"here's my track record."* It's: *"here's the measurement of a bad V1 system that I saw coming, that I've already replaced with V2 on future cohorts, and that I'm publishing anyway because a calibration system that hides its bad numbers isn't a calibration system."*

V2 already produces probabilities spread across three buckets, can descend below 0.50 (bearish), forces `watch` when evidence doesn't justify a falsifiable directional call. Synthetic tests show a ceiling broken to 0.77 on strong evidence, a coherent floor around 0.40 on inverse evidence, a refusal rate (`watch`) of 75% that honestly reflects the average quality of the input pipeline. But the 40 predictions for June 10 were frozen under V1. You don't rewrite a track record after the fact.

---

The system doesn't just have a bad Brier coming. It has a bad Brier coming **and already knows it**. That second property is the one that has to travel. The first number is shameful; the second is the asset.

Eleven days is enough to write the publication conditions before knowing the result — to pre-commit honesty rather than choose it under pressure. That's what an honest calibration system does by construction. If you find out about your own failure at the same time as your audience, you've lost the game you claimed to be playing.

0.63 looked perfect six weeks ago. 0.295 will be the proof in eleven days. Between them, I had time to check. The rest is tactical.
