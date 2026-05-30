# Post #02 — version bilingue

*Français d'abord, English below. Mêmes choix que post_01 : la scène centrale est le moment où la donnée contredit le commentaire ; zéro pitch ; « je ne suis pas développeur » assumé.*

---
---

## 🇫🇷 Je n'avais pas un bug, j'avais cru un commentaire

*Six mois de confiance dans un dashboard, démontés par une ligne de SQL.*

---

Il y a neuf jours, mon dashboard m'a affiché un prix d'achat de **0,76 $** pour SK hynix. Le prix réel : **1 216 $**. Une erreur de 1 600×, assise tranquillement en production, contaminant mon P&L depuis plus d'une semaine.

Je l'ai attrapée par accident. Le brief du matin disait SK hynix « +167 195 % ». J'aurais dû la voir le jour même. Je ne l'ai pas vue parce que les autres lignes du portefeuille affichaient des chiffres sains, alors mon œil a glissé sur l'anomalie comme sur un glitch d'affichage.

Le fix a pris six minutes à écrire. L'audit qui a révélé *pourquoi* le bug existait a pris six heures. Cette asymétrie est le vrai sujet du post.

---

Je ne suis pas développeur. L'IA a écrit la quasi-totalité de ce code. Quatre handlers d'affichage différents voulaient convertir un prix d'achat stocké vers du USD. Tous les quatre faisaient :

```python
avg_cost_usd = avg_cost * fx_native_to_USD
```

Pour SK hynix, ça donnait `1 043 × 0,000727 = 0,76 $`. Logique — *si* `avg_cost` était stocké en devise native, ce que disait le commentaire en haut du fichier :

> *`avg_cost` est en devise native (JPY pour les `.T`, KRW pour les `.KS`, EUR pour les `.PA`, USD sinon).*

Sauf que `avg_cost` n'a **jamais** été stocké en native. Le script d'import du courtier, écrit une semaine plus tôt par moi sur d'autres hypothèses, le stockait en EUR. Le commentaire était de l'**aspirationnel** : une intention de design qui n'a jamais atterri dans le code de production.

Six mois de confiance compoundée dans un dashboard, sapée par un commentaire qui mentait.

---

Quand je me suis mis à corriger, le réflexe évident a été de retourner les quatre handlers : changer le multiplicateur, livrer le patch. Mais je n'étais pas certain dans quel sens flipper. Les commentaires disaient « native ». Le brief du matin disait l'inverse. Les autres parties du code utilisaient des conventions incohérentes. Quelle était la vraie convention de la base de données ?

L'évidence textuelle était contradictoire. J'ai dérivé la vérité depuis la donnée.

Une seule requête : pour chacune de mes 21 positions actives, diviser `avg_cost` par le prix live en EUR. Si `avg_cost` était stocké en native, les ratios devaient se regrouper autour des taux de change (0,005 pour JPY, 0,0006 pour KRW, 1,17 pour USD). Si `avg_cost` était stocké en EUR, *tous les ratios, toutes devises confondues, devaient être autour de 1,0*.

Sortie empirique :

| Ticker | Native | avg_cost | live_EUR | ratio |
|---|---|---|---|---|
| 000660.KS | KRW | 1 043 | 1 028 | 1,014 |
| 4063.T | JPY | 38,52 | 37,35 | 1,031 |
| ASML.AS | EUR | 1 309 | 1 249 | 1,048 |
| AMD | USD | 386 | 355 | 1,087 |
| ... | | | | |
| **Range 21 positions** | mixte | varié | varié | **[0,937 ; 1,147]** |

Tous les 21 ratios autour de 1,0, quelle que soit la devise native. **EUR canonique confirmé, définitivement.** Si le stockage était native, KRW aurait sorti un ratio à 169 200 %, JPY à 18 293 %. Au lieu de ça, cluster serré autour de 1,0.

La donnée a tranché la question que les commentaires ne pouvaient pas trancher.

---

J'ai codifié la trouvaille comme ADR 005 dans le projet, puis ajouté la Leçon 15 à mon CONVENTIONS.md — le fichier que je relis au début de chaque session :

> **Leçon 15 — La vérification empirique s'applique au-delà du SQL.**
>
> Les conventions de stockage affirmées dans les commentaires sont la documentation d'une *intention au moment de l'écriture* ; le stockage réel EST ce qu'il EST. Pour auditer une affirmation système, dériver la vérité depuis la **donnée**, pas depuis le **texte**.

La leçon complète inclut le pattern de l'outillage — l'audit cross-currency par ratio, généralisé. Prochaine fois que je lis un commentaire affirmant une convention, j'ai un script de 10 lignes prêt pour vérifier au lieu de croire.

---

Le bug existait parce que j'avais fait confiance à mon propre commentaire passé. C'est une forme d'auto-déférence : *moi d'il y a deux semaines a probablement raison*. Les commentaires sont du texte humain affirmant un état du système ; le système est un état du système. Quand les deux divergent, c'est la donnée qui gagne, et c'est toujours la donnée qui devrait gagner.

L'auto-déférence se compound mal sur six mois. Le prochain bug silencieux dans ce système sera attrapé pareil — par accident, à un moment où j'aurai eu le réflexe de vérifier au lieu de croire. La seule chose qui change maintenant, c'est que j'ai un script de 10 lignes prêt et l'habitude de le lancer.

Le bug n'est pas l'histoire. L'histoire, c'est six mois de confiance dans un commentaire que personne n'aurait pensé à vérifier.

---
---

## 🇬🇧 I Didn't Have a Bug. I Believed a Comment.

*Six months of confidence in a dashboard, dismantled by one line of SQL.*

---

Nine days ago, my dashboard told me I had paid **$0.76 per share** for SK hynix. The actual price: **$1,216**. A 1,600× error, sitting quietly in production, contaminating my P&L for over a week.

I caught it by accident. The morning brief showed SK hynix at "+167,195%." I should have caught it the same day. I didn't, because the rest of my portfolio displayed sane numbers, so my eye slid past the anomaly as a display glitch.

The fix took six minutes to write. The audit that revealed *why* the bug existed took six hours. That asymmetry is the actual point of this post.

---

I'm not a developer. AI wrote almost all of this code. Four different display handlers wanted to convert a stored purchase price into USD. All four did:

```python
avg_cost_usd = avg_cost * fx_native_to_USD
```

For SK hynix, that became `1,043 × 0.000727 = $0.76`. Logical — *if* `avg_cost` was stored in native currency, which is what the comment at the top of the file said:

> *`avg_cost` is stored in **native currency** (JPY for `.T` tickers, KRW for `.KS`, EUR for `.PA`, USD otherwise).*

Except `avg_cost` was **never** stored in native. The broker import script, written by me a week earlier under different assumptions, stored it in EUR. The comment was **aspirational** — a design intent that never landed in production code.

Six months of compounded confidence in a dashboard, undermined by a comment that lied.

---

When I sat down to fix it, the obvious move was to flip the four handlers: change the multiplier, ship the patch. But I wasn't sure which way to flip. The comments said "native." The morning brief disagreed. Other parts of the code used inconsistent conventions. Which one was the actual convention of the database?

The textual evidence was contradictory. So I derived truth from data instead.

One query: for each of my 21 active positions, divide the stored `avg_cost` by the current live price in EUR. If `avg_cost` was native-stored, the ratios should cluster around fx rates (0.005 for JPY, 0.0006 for KRW, 1.17 for USD). If `avg_cost` was EUR-stored, *all ratios across all currencies should cluster around 1.0*.

Empirical output:

| Ticker | Native | avg_cost | live_EUR | ratio |
|---|---|---|---|---|
| 000660.KS | KRW | 1,043 | 1,028 | 1.014 |
| 4063.T | JPY | 38.52 | 37.35 | 1.031 |
| ASML.AS | EUR | 1,309 | 1,249 | 1.048 |
| AMD | USD | 386 | 355 | 1.087 |
| ... | | | | |
| **Range across 21 positions** | mixed | varied | varied | **[0.937, 1.147]** |

All 21 ratios near 1.0, regardless of native currency. **EUR canonical confirmed, definitively.** Had storage been native, KRW would have shown 169,200%, JPY 18,293%. Instead, tight cluster around 1.0.

The data settled what the comments couldn't.

---

I codified the finding as ADR 005 in the project, then added Lesson 15 to my CONVENTIONS.md — the file I read at the start of every session:

> **Lesson 15 — Empirical verification applies beyond SQL.**
>
> Storage convention claims in comments are documentation of *intent at time of writing*; the actual storage IS what storage IS. To audit a system claim, derive truth from **data**, not from **text**.

The full lesson includes the tooling pattern — the cross-currency ratio audit, generalized. Next time I read a comment asserting a convention, I have a 10-line script ready to verify rather than trust.

---

The bug existed because I had trusted my own past comment. That's a form of self-deference: *me-from-two-weeks-ago probably knew what they were doing*. Comments are human text asserting a state of the system; the system is the actual state. When the two diverge, data wins, and data should always win.

Self-deference compounds badly over six months. The next silent bug in this system will be caught the same way — by accident, in a moment when I happened to verify instead of believe. The only thing that changes now is that I have the 10-line script ready and the habit of running it.

The bug isn't the story. The story is six months of confidence in a comment nobody would have thought to check.
