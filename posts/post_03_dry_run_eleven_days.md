# Post #03 — version bilingue

*Français d'abord, English below. Mêmes choix : la preuve avant l'annonce ; zéro pitch ; « je ne suis pas développeur » assumé.*

---
---

## 🇫🇷 Le moment de vérité que j'ai annoncé n'existait pas

*Comment un dry-run pré-engagé a survécu à un constat plus inconfortable que l'échec lui-même.*

---

J'ai un système qui prédit des mouvements de marché. Il y a onze jours, je l'ai annoncé : 40 prédictions résolvent le 10 juin 2026. C'était censé être mon premier point Brier — la mesure de calibration qui devait dire si mes convictions valent quelque chose. J'avais simulé la résolution en dry-run J-11. Le résultat était mauvais (Brier ~0,295) et je m'étais pré-engagé à le publier honnêtement plutôt que le maquiller.

Onze jours plus tard, en relisant la base de données à J-3, j'ai dû corriger une chose plus structurelle que le mauvais chiffre.

**Le batch de 40 prédictions résolvant le 10 juin n'existait pas.**

Ce que j'ai en réalité : 173 prédictions V1, étalées sur target_dates allant du 27 mai au 28 juillet. 35 sont déjà résolues. **0 ne résoudront le 10 juin.** Le dry-run avait modélisé une cohorte hypothétique — comme si toutes les V1 antérieures convergeaient sur une seule date. Aucune ne le fait.

Donc le 10 juin n'est pas le moment de vérité que j'avais annoncé. C'est une date symbolique sur laquelle j'avais ancré un narratif qui n'avait pas de support dans la donnée elle-même.

---

Voici la vraie mesure, sur les 35 V1 effectivement résolues entre le 27 mai et le 5 juin :

```
35 prédictions V1 résolues
  correct    :  9 (26 %)
  incorrect  : 16 (46 %)
  neutral    : 10 (29 %)

Brier moyen : 0,316 (sur 25 scored)
Baseline trivial (prior 0,5 constant) : 0,250
Accuracy bull/bear : 9/25 = 36 %
```

C'est **pire** que le dry-run prévoyait. 0,316 au lieu de 0,295. Le diagnostic structurel (mono-bucket à 0,63, surconfiance, hard-cap dans la formule) tient — mais le système, mesuré, est encore moins bon que la simulation J-11 ne le disait.

---

Le narratif que je m'apprêtais à publier le 10 juin disait : *« voici un mauvais Brier, je l'ai vu venir, je le publie quand même. »* Il faut maintenant ajouter une couche : **j'ai annoncé un moment de vérité qui n'avait pas la matérialité que je lui prêtais.** La date était calendaire-dure ; la cohorte était une fiction de dry-run.

C'est plus inconfortable que le mauvais Brier. Un mauvais chiffre, ça dit *« mon système ne sait pas prédire »*. Une cohorte fantôme, ça dit *« j'ai construit un récit autour d'une date qui n'avait pas le support de la donnée — y compris en pré-engagement »*.

Le pré-engagement honnête ne suffit pas. Il faut aussi vérifier que la chose qu'on pré-engage **existe dans la donnée**. Sinon on construit de l'honnêteté autour du vide.

---

Ce qui survit du dry-run J-11 :

- Le diagnostic structurel V1 (mono-bucket, hard-cap, surconfiance) est validé — et mesuré pire que prévu.
- La doctrine *« mauvais Brier publié honnêtement > maquillage »* tient.
- La doctrine *« vérifier avant de publier »* tient — mais elle s'est appliquée à elle-même : la vérification J-3 a invalidé l'hypothèse de batch.
- V2 est en place sur cohortes futures (`signal_scorer_v2`, base-rate-first, trois buckets, refusal `watch` 75 %). La première mesure V2 viendra plus tard, étalée sur l'été comme la cohorte le permet.

Ce qui ne survit pas :

- L'idée que le 10 juin était un événement de calibration mesurable.
- L'idée qu'on pouvait pré-mesurer un batch qui n'existait pas en tant que batch.

---

Le 10 juin reste calendaire. Le job automatique enverra "*aucune prédiction V1 résolue ce jour. Archive V1 close. V2 pas encore démarré → headline canonique à venir.*" C'est cohérent. Pas de cérémonie publique, parce que la cérémonie qui était prévue n'avait pas de matériel.

**0,316 est la mesure réelle sur la cohorte réelle.** Pas 0,295 sur une cohorte hypothétique. Le système est mauvais ; il est mesurable ; il est en cours de remplacement. La calibration honnête comporte de reconnaître quand on s'est aussi raconté une histoire à soi-même — y compris une histoire d'honnêteté.

---

Si vous avez vu passer le premier post pré-engagement il y a onze jours, ce post-ci est l'amende honorable : pas sur le Brier (qui est encore plus mauvais que prévu), mais sur la mise en scène d'un moment de vérité qui n'avait pas la matérialité que je lui donnais. Onze jours, c'était assez pour dire la chose ; trois jours de plus auront été nécessaires pour la mesurer correctement.

Le système n'a pas seulement un mauvais Brier mesurable. Il a un mauvais Brier mesurable **et il a survécu au constat que sa propre mise en scène était partiellement creuse**. C'est cette deuxième propriété — la capacité à ravaler une promesse mal calibrée *sur sa propre calibration* — qui voyage.

---
---

## 🇬🇧 The Moment of Truth I Announced Didn't Exist

*How a pre-committed dry-run survived a finding more uncomfortable than the failure itself.*

---

I have a system that forecasts market moves. Eleven days ago, I announced it: 40 predictions resolve on June 10, 2026. That was supposed to be my first Brier point — the calibration measure that would say whether my convictions are worth anything. I'd simulated the resolution in a J-11 dry-run. The result was bad (Brier ~0.295) and I'd pre-committed to publishing it honestly rather than dressing it up.

Eleven days later, re-reading the database at J-3, I had to correct something more structural than the bad number.

**The batch of 40 predictions resolving on June 10 did not exist.**

What I actually have: 173 V1 predictions, target_dates spread from May 27 to July 28. 35 already resolved. **0 will resolve on June 10.** The dry-run had modeled a hypothetical cohort — as if all prior V1s converged on one date. None do.

So June 10 isn't the moment of truth I announced. It's a symbolic date around which I anchored a narrative that had no support in the data itself.

---

Here's the real measurement, on the 35 V1s effectively resolved between May 27 and June 5:

```
35 V1 predictions resolved
  correct    :  9 (26%)
  incorrect  : 16 (46%)
  neutral    : 10 (29%)

Mean Brier : 0.316 (over 25 scored)
Trivial baseline (constant 0.5 prior) : 0.250
Bull/bear accuracy : 9/25 = 36%
```

**Worse** than the dry-run predicted. 0.316 instead of 0.295. The structural diagnosis (mono-bucket at 0.63, overconfidence, hard-cap in the formula) holds — but the system, when measured, is worse than the J-11 simulation said.

---

The narrative I was about to publish on June 10 said: *"here's a bad Brier, I saw it coming, I'm publishing it anyway."* Now there's an additional layer: **I announced a moment of truth that didn't have the materiality I was attributing to it.** The date was calendar-hard; the cohort was a dry-run fiction.

That's more uncomfortable than the bad Brier. A bad number says *"my system can't predict."* A phantom cohort says *"I built a story around a date that the data didn't back — including in pre-commitment."*

Honest pre-commitment isn't enough. You also have to verify that the thing you're pre-committing to **exists in the data**. Otherwise you're building honesty around nothing.

---

What survives from the J-11 dry-run:

- The V1 structural diagnosis (mono-bucket, hard-cap, overconfidence) is validated — and measured worse than predicted.
- The doctrine *"bad Brier published honestly > dressed-up"* holds.
- The doctrine *"verify before publishing"* holds — but it applied to itself: the J-3 verification invalidated the batch hypothesis.
- V2 is in place on future cohorts (`signal_scorer_v2`, base-rate-first, three buckets, 75% `watch` refusal). The first V2 measurement will come later, spread across summer as the cohort allows.

What doesn't survive:

- The idea that June 10 was a measurable calibration event.
- The idea that you can pre-measure a batch that didn't exist as a batch.

---

June 10 stays calendar. The automatic job will send "*no V1 predictions resolved today. V1 archive closed. V2 not yet started → canonical headline forthcoming.*" That's consistent. No public ceremony, because the ceremony that was planned had no material.

**0.316 is the real measurement on the real cohort.** Not 0.295 on a hypothetical one. The system is bad; it's measurable; it's being replaced. Honest calibration includes recognizing when you told yourself a story too — including a story about honesty.

---

If you saw the pre-commitment post eleven days ago, this one is the honest correction: not on the Brier (which is worse than predicted), but on the staging of a moment of truth that didn't have the materiality I was attributing to it. Eleven days was enough to say the thing; three more days were necessary to measure it correctly.

The system doesn't just have a measurable bad Brier. It has a measurable bad Brier **and it survived noticing that its own staging was partially hollow**. That second property — the capacity to swallow a miscalibrated promise *about your own calibration* — is what travels.
