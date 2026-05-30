# Post #01 — version bilingue

*Français d'abord, English below. Mêmes choix : le fail d'iter 5 reste la scène centrale, zéro pitch, zéro position, le « je ne suis pas développeur » assumé.*

---
---

## 🇫🇷 Six fois j'ai cru avoir fini

*Ce que m'a appris un prévisionniste qui mentait — et que rien ne signalait.*

---

J'ai construit un système qui prévoit des mouvements de marché. Un jour, j'ai regardé ses prédictions de plus près : toutes les probabilités étaient coincées entre 0,61 et 0,66.

Ça ressemblait à un prévisionniste qui fonctionne. Ça n'en était pas un. C'était une constante déguisée en prévisionniste — quoi qu'il « voie », il répondait « environ 63 % de chances ». Une prédiction à 0,63 sur tout ne prédit rien.

Et rien ne l'avait signalé. Les tests étaient verts. Aucune erreur. Le système tournait, produisait des chiffres bien formés, et ces chiffres étaient creux.

Je ne suis pas développeur. L'IA a écrit la quasi-totalité de ce code. C'est précisément le sujet : construire est devenu bon marché. Quelqu'un sans bagage technique peut aujourd'hui assembler un système sérieux en quelques jours. Mais ce système vous mentira avec aplomb, d'une façon qui passe tous les contrôles au vert — et la compétence rare, celle que l'IA ne vous donne pas, c'est d'attraper le mensonge.

Voici l'histoire d'un mensonge attrapé. Il m'a fallu six tentatives. À chacune, j'ai cru avoir fini.

**Un.** Le 0,63 venait d'un plafond codé en dur et d'un prompt qui poussait le modèle vers le « probable mais incertain » par défaut. Je l'ai réécrit : pars du taux de base, justifie chaque écart, refuse de t'ancrer. Les probabilités se sont enfin étalées — vers le bas, jusqu'au bearish. J'ai failli conclure là.

Sauf que je n'avais vérifié que la moitié basse. Le haut, je l'*assumais* : « ça devrait monter à 0,75 sur de l'évidence forte ». *Devrait.* J'ai fabriqué une échelle de signaux synthétiques pour le vérifier — et le test a fait tomber un tout autre bug : le modèle dégradait les sources qu'il ne reconnaissait pas. Autrement dit, il pénalisait systématiquement mes sources de niche, exactement celles qui font ma différence.

**Deux, trois.** Le taux de signaux que le système refusait de noter semblait sain à 12 %. Sauf que ce 12 % était lui-même un artefact : le système forçait des signaux faibles dans le registre comme des quasi pile-ou-face. La cause était une confusion sémantique — entre « probabilité que mon appel soit juste » et « probabilité que le prix monte ». Corrigé, le taux s'est posé là où l'évidence le justifiait vraiment.

**Quatre.** Le scoreur était maintenant correct. Mais chaque entrée était une newsletter d'opinion tech — de l'évidence modérée, par nature. J'allais conclure qu'il me fallait acheter de meilleures sources.

En vérifiant d'abord, j'ai trouvé 421 lignes de l'évidence forte que je cherchais — dépôts de résultats, achats d'initiés — déjà dans ma base de données, ingérées par du code qui tournait, dans des tables qui n'étaient jamais reliées au scoreur. Je n'avais pas besoin de nouvelles sources. Je n'avais jamais branché celles que j'avais.

**Cinq.** J'ai voulu le vérifier sur une vraie donnée. Le test a échoué : l'extracteur récupérait la page de garde du dépôt, pas son contenu. (C'est l'itération que je garde la plus visible. Un test qui échoue et force une vraie correction vaut plus que dix « ça a marché ».)

**Six.** J'ai écrit l'extracteur. Un vrai dépôt de résultats est passé par toute la chaîne et a produit un appel directionnel à 0,750, calibré, sur évidence forte. Vu. Plus « devrait ». *Vu.*

---

Chacun de ces bugs était de la même espèce : silencieux, plausible, validé par tous les contrôles au vert, et en train de corrompre tranquillement la seule chose que le système existe pour produire — un historique crédible. Aucun n'a levé d'erreur. Une probabilité constante. Un seuil caché. Des données primaires qui coulent à côté du pipeline. Une URL qui pointe vers une couverture.

Les défaillances dangereuses des systèmes construits avec l'IA ne sont pas des crashs bruyants. Ce sont des mensonges bien formés et confiants. Le travail n'est pas d'écrire le code — l'IA le fait. Le travail, c'est de fabriquer les contrôles falsifiables qui rendent les mensonges silencieux *bruyants*, et d'avoir la discipline de les lancer même quand on est certain d'avoir fini.

Six fois j'en étais certain. Six fois je ne l'étais pas.

Le système n'est toujours pas terminé. Mais il a maintenant quelque chose qu'il n'avait pas : l'habitude, instrumentée, de se méfier de lui-même.

Le 0,63 avait l'air parfait. C'est là tout le danger.

---
---

## 🇬🇧 Six Times I Thought I Was Done

*What a forecaster that lied to me taught me — and that nothing flagged.*

---

I built a system that forecasts market moves. One day I looked closely at its predictions: every probability was wedged between 0.61 and 0.66.

It looked like a working forecaster. It wasn't. It was a constant wearing a forecaster's costume — whatever it "saw," it answered "about 63% likely." A model that predicts 0.63 on everything predicts nothing.

And nothing had flagged it. Tests green. No errors. The system ran, produced well-formed numbers, and the numbers were hollow.

I'm not a developer. AI wrote almost all of this code. That's exactly the point: building has become cheap. Someone with no technical background can now assemble a serious system in a few days. But that system will lie to you with total confidence, in ways that pass every green check — and the rare skill, the one AI doesn't hand you, is catching the lie.

Here's the story of one lie, caught. It took six tries. Each time, I thought I was done.

**One.** The 0.63 came from a hard-coded cap and a prompt that nudged the model toward "likely but uncertain" by default. I rewrote it: start from the base rate, justify every deviation, refuse to anchor. The probabilities finally spread out — downward, into bearish territory. I almost called it there.

Except I'd only verified the bottom half. The top half I was *assuming*: "it should reach 0.75 on strong evidence." *Should.* I built a synthetic ladder to check instead — and the test knocked loose an entirely different bug: the model was downgrading sources it didn't recognize. Which meant it was systematically penalizing my niche sources — the exact ones that are my edge.

**Two, three.** The share of signals the system refused to score looked healthy at 12%. Except that 12% was itself an artifact: the system was forcing weak signals into the ledger as near coin-flips. The cause was a semantic mix-up — between "probability my call is right" and "probability the price goes up." Fixed, the rate settled where the evidence actually warranted.

**Four.** The scorer was now correct. But every input was a tech-opinion newsletter — moderate evidence, by nature. I was about to conclude I needed to buy better sources.

Verifying first, I found 421 rows of the strong evidence I was looking for — earnings filings, insider buys — already sitting in my database, ingested by code that was running, in tables that were never wired to the scorer. I didn't need new sources. I'd never connected the ones I had.

**Five.** I went to verify it on real data. The test failed: the extractor was pulling the filing's cover page, not its content. (This is the iteration I keep most visible. A test that fails and forces a real fix is worth more than ten "it worked.")

**Six.** I wrote the extractor. A real earnings filing went through the whole chain and produced a calibrated, high-confidence directional call at 0.750, on strong evidence. Seen. Not "should." *Seen.*

---

Every one of those bugs was the same species: silent, plausible, signed off by every green check, and quietly corrupting the one thing the system exists to produce — a credible track record. Not one threw an error. A constant probability. A hidden threshold. Primary data flowing beside the pipeline. A URL pointing at a cover page.

The dangerous failures in AI-built systems aren't loud crashes. They're confident, well-formed lies. The work isn't writing the code — AI does that. The work is manufacturing the falsifiable checks that turn the silent lies *loud*, and having the discipline to run them even when you're sure you're done.

Six times I was sure. Six times I wasn't.

The system still isn't finished. But it now has something it didn't: the instrumented habit of distrusting itself.

0.63 looked perfect. That's the whole danger.
