# Decision Log #01 — Casser l'ancre de calibration

**Date** : 30 mai 2026
**Owner** : Olivier Legendre
**Trigger** : audit pré-batch 10/06 (KPI #2, ~40 résolutions attendues)
**Outcome** : SIGNAL_SCORER_V2 livré + intégré + vérifié

---

## Le bug

Au moment d'auditer la pipeline de résolution avant le batch du 10 juin (premier vrai point Brier dédupliqué du système), j'ai mesuré la distribution des 40 prédictions attendues.

Résultat brut :

```
40 prédictions, 4 valeurs uniques de probabilité : 0.608, 0.626, 0.628, 0.658.
Range : 5 points. Toutes dans [0.60-0.66]. 0% direction "watch".
```

Sur les 6 prédictions déjà résolues : 67% outcome = `neutral` (mouvement < 5%).

**Diagnostic initial (faux)** : « problème de maturité de données, le temps va résoudre ». **Pivot Phase B vers raisonnement-first, pas calibration plot.**

**Pushback adversaire (mérité)** : la maturité couvre le volume et le spread temporel, **pas le mono-bucket**. Un forecaster dont toutes les probabilités tiennent dans 5 points ne produit pas du jugement probabiliste — il produit une constante déguisée. Le temps n'y fera rien : dans 4 mois j'aurai juste plus de 0.63.

Le 67% neutral relève du même mal : système qui évite la falsifiabilité. *« On ne peut pas avoir tort si on ne s'engage jamais »* est le failure mode séduisant exact quand on construit un track record qu'on veut beau.

Un évaluateur sharp repère ça en 10 secondes.

---

## La cause racine

L'investigation a remonté 3 couches :

1. **`estimate_probability` (V1)** : formule déterministe, cap **[0.50, 0.72]**. Impossible de produire 0.30 ou 0.85, même sur évidence très forte ou très contraire.

2. **64/68 sources à credibility=0.50** (default). La recalibration mensuelle existe (`recalibrate_credibility_brier_job` 1er du mois) mais exige `min_n=10` brier-scored par source. On a 6 résolutions total dans toute la DB. Job jamais kick → **bootstrap mort**.

3. **Filter score≥6 + sentiment bullish/bearish** : seulement les signaux haut score génèrent des predictions → 4 combinaisons d'inputs uniques pour 40 predictions.

Hypothèse initiale (« Haiku qui s'ancre sur 0.6 ») : partiellement fausse. La proba ne vient pas d'élicitation LLM, elle vient d'une formule. Mais la formule produit du mono-bucket parce que **ses inputs sont mono-bucket** : tous score=7, tous cred=0.5.

Et — point structurel — le batch 10/06 est déjà figé. Une proba loguée ne se rétro-corrige pas. Ce batch n'apportera donc pas de calibration story quelle que soit la suite. **Le levier = l'élicitation pour la cohorte suivante.**

---

## Le fix : SIGNAL_SCORER_V2

Approche par prompt-engineering. Au lieu de demander une probabilité « à froid » (qui régresse vers le moyennement-confiant), forcer le LLM à articuler 3 étapes explicites :

```
STEP 1 — BASE RATE (sans regarder le signal) : taux de base directionnel
sur l'horizon. Pour les liquid equities en 30j, près de 0.50. PAS de 0.6
"par confort".

STEP 2 — AJUSTEMENT : lister l'évidence spécifique du signal qui justifie
de dévier du base rate, et de combien. Échelle explicite :
- none     : pas d'évidence -> reste AT base rate
- weak     : narrative vague -> 0-3pts max
- moderate : data point concret -> 5-15pts
- strong   : verifiable + magnitude -> 15-30pts

STEP 3 — ANTI-ANCRAGE : une phrase, pourquoi ni ~0.50 ni ~0.90.
Si pas de substance pour justifier l'écart, probability = base rate.
```

Plus :
- **Zone morte interdite [0.55-0.70]** sans evidence ≥ moderate (enforced server-side).
- **`direction="watch"`** si pas d'évidence falsifiable → sort du ledger. Mieux que neutral mou.
- **Source-credibility EXCLUE du prompt** (cf vérification ci-dessous).

---

## La vérification — partie qui montre le jugement

C'est la partie qui aurait dû ne pas être bypassée. Premier pass a montré sur 8 signaux réels : range [0.44-0.54], 5 buckets, 62% watch. *Tentation* : « c'est mieux que V1, on intègre ». Mauvais réflexe.

**Pushback adversaire (mérité ×2)** : *« tu n'as vérifié que la moitié basse. Le mono-bucket n'est pas prouvé mort tant que tu n'as pas vu V2 cracher du 0.75+ sur de l'évidence forte. Les LLM s'ancrent aux deux bouts — peut-être que tu as cassé l'ancre basse sans toucher l'ancre haute. Sans signal fort dans l'échantillon, tu ne peux pas le savoir. »*

D'où : **échelle synthétique 4 niveaux** sur NVDA, horizon 30j :

| Niveau | Signal | base_rate | prob | direction | evidence |
|---|---|---|---|---|---|
| FAIBLE | "AI chip sector momentum" (narrative générique) | 0.520 | 0.540 | bullish | weak |
| MODÉRÉ | "Goldman raises NVDA PT $1100→$1200" (analyst note routine) | 0.520 | 0.520 | bullish | weak |
| FORT | "NVDA Q3 beats $35.1B vs $33.5B, raises Q4 guide" (earnings + magnitude) | 0.520 | 0.720 | bullish | strong |
| TRÈS FORT | "NVDA Blackwell supply resolved, FY guide +$14B, $25B buyback" (multi-catalyseur quantifié) | 0.520 | **0.770** | bullish | strong |

Anti-ancrage du TRÈS FORT, verbatim : *« not ~0.90 because a +12% pre-market gap creates mean-reversion risk, macro shocks can erase gains within 30 days, and some of the upside is already priced in »*.

C'est exactement le raisonnement de calibration qu'un évaluateur veut voir.

**Et : le premier test avait un bug.** TRÈS FORT était sorti `prob=0.520 watch` parce que j'avais injecté `source_name="synthetic_test"` dans le prompt — le LLM downgrade à cause de la source. Re-test avec `source_name=Bloomberg` → 0.77 ✅. Conclusion : la fiabilité source pollue le scoring d'évidence quand on l'expose au LLM. **Fix architectural** : source EXCLUE du prompt, pondération source devient une couche après, jamais pendant.

Re-test sample réel post-fix source :

| Métrique | V1 (40 preds) | V2 pre-fix | V2 post-fix |
|---|---|---|---|
| Range | [0.608-0.658] | [0.440-0.540] | **[0.380-0.540]** |
| Buckets uniques | 4 | 5 | 5 |
| Watch rate | 0% | 62% | **12%** |
| Std deviation | ~0 | 0.030 | **0.070** |
| Directions | 100% bullish (sentiment) | 1bull/2bear/5watch | **5bear/2bull/1watch** |

Le 62% watch initial était bien un bug source, pas une honnêteté épistémique.

Le retournement directionnel (V1 = 100% bullish, V2 = 5/8 bearish) est éloquent : le sentiment-based V1 ne savait pas peser l'évidence. V2 attribue l'évidence faible et inversée aux narratives "sector-level momentum" qui en pratique précèdent souvent une consolidation.

---

## Ce qui est intégré

- `intelligence/signal_scorer_v2.py` : nouveau module.
- `shared/storage.insert_prediction` : accepte `probability_override` (V2 path). V1 (formule) reste exposé pour rollback.
- `intelligence/learning.auto_register_predictions` : appelle V2 par signal × ticker. `direction="watch"` → skip (pas dans ledger). Filter score≥6 conservé en amont pour limiter coût LLM (~40 calls/jour Sonnet ≈ $0.20).

---

## Ce qui n'a PAS été intégré (volontairement)

- **Pas d'A/B parallèle V1/V2** : double le coût, complique le ledger. L'échelle synthétique fournit la même confiance, plus vite.
- **Pas de migration schema** pour `scorer_version` column : versioning via code source. Si besoin A/B futur, migration 0021 dédiée.
- **Pas de bump du filter score≥6** : sortie de scope, V2 lui-même décide via `evidence_strength → watch` quand le signal ne mérite pas.
- **Pas de fix `min_n=10` bootstrap source** : la recalibration source devient secondaire avec V2 (qui n'utilise plus credibility comme input direct). Revisiter post-10/06 si besoin.

---

## Itération 2 — frontière watch/directionnel (le péché symétrique)

Après l'intégration, deuxième pushback adversaire : *« 62% watch était peut-être un bug, mais 12% n'est pas vérifié non plus. Tu as prouvé le spread, pas la frontière de commit. Le péché original était la sous-commitment ; le péché symétrique, c'est la sur-commitment. Si le sourcing n'a pas changé et que la plupart des signaux sont vraiment faibles, un watch bas veut dire que tu forces des narratives faibles dans le ledger comme calls directionnels à ~0.5. Mono-bucket déménagé, pas tué. »*

Relecture du sample 8 réels post-fix source : 3 evidence=weak étaient en ledger comme bullish ~0.54 et bearish ~0.43. Verbatim du prompt original : *« Si aucune évidence ne soutient une direction falsifiable => direction:'watch' »*. Weak ≈ vague narrative ≈ non-falsifiable. Mon enforcement (dead zone [0.55-0.70]) ne capturait pas les weak juste en-dessous.

**Fix iteration 2** (commit 0b4d0c1 + 1 patch) : `evidence_strength ∈ (none, weak) → direction='watch'` forcé server-side. Le seuil de commit est `moderate+`, pas `weak+`.

**Vérification sample n=20** :

| Métrique | Pré-fix iter2 (n=8) | Post-fix iter2 (n=20) |
|---|---|---|
| Watch rate | 12% | **75%** |
| Directional cohort | n=7 | n=5 |
| Invariant weak/none → watch | 3 violations | **0** ✅ |
| Cohorte directionnelle range | [0.38-0.54] mixte | [0.38-0.42] tous bearish moderate |

**Lecture** : le 75% watch est défendable — sample dominé par newsletters tech (Ben Thompson, Wall Street Rollup) = par construction des opinions sector-level AI hype = la majorité weak. C'est cohérent avec la limite #2 originale du sourcing : *« le pipeline génère majoritairement des narratives faibles »*. Watch rate sain ≠ bas — c'est égal à la vraie fraction de signaux non-informatifs.

**Mais nouveau risque identifié** : la cohorte directionnelle reste mono-bucket (n=5, 3 valeurs uniques en 4pts, tous bearish ~0.40). Deux explications possibles :
- (a) Mono-bucket déménagé une 3ème fois : le LLM converge sur ~0.40 pour ces narratives, peu importe la pièce d'évidence
- (b) Signal réel du système : ces narratives AI sont cohéremment bearish moderate, ce qui est défendable analytiquement

Probable (b) mais non prouvé. Sample biaisé (tirage RANDOM sur batch dominé par tech opinions). Vrai test = sample diversifié (earnings beats, macro, regulatory) — à faire dès qu'on a la matière.

## Itération 3 — sémantique cassée (encore)

Test diversité synthétique sur 6 cas variés (NVDA bull strong, TSLA bear strong, AMZN bear strong, REGN bull strong, MSFT bull moderate, GOOGL bear moderate) pour cracker la cohorte directionnelle [0.38-0.42] observée iter 2. Résultat : **range [0.62-0.77] sur les directional** — la cohorte PEUT spread quand l'évidence varie. Le mono-bucket [0.38-0.42] du sample précédent était du au sourcing (toutes opinions tech AI = même catégorie).

**Mais** en re-lisant les outputs côte-à-côte avec le sample 20 réels :

| Sample | Output type | Interpretation |
|---|---|---|
| Synthetic bear strong | bearish 0.75 | P(bearish call correct) = 0.75 ✅ cohérent |
| Real sample bearish | bearish 0.38 | P(bearish call correct) = 0.38 ⚠️ incohérent |

Si je suis à 38% sûr que bearish est correct, je suis à 62% sûr que bullish est correct. **Le LLM confondait P(call correct) avec P(price up).** Le prompt était ambigu sur la sémantique de `probability`.

**Fix iteration 3** :
1. Prompt clarifié explicitement : `probability = P(your directional call is CORRECT), NOT P(price up). MUST be in [0.50, 0.95] for any direction != watch.`
2. Server-side enforcement #3 : `if direction != 'watch' and prob < 0.55: snap to watch`. Logique : on ne commit pas si on n'est pas plus sûr que pile-ou-face.

Re-test 6 synthétiques iter 3 : strong → [0.72-0.75] (cohérent), weak/none → watch, edge case "moderate evidence but unclear direction" → LLM downgrade à `none` + watch (auto-correction propre).

Re-test sample n=20 réels iter 3 :
- 13 weak (forced watch), 7 moderate bearish
- **Cohorte directionnelle : 7 bearish à [0.60-0.62]** (vs [0.38-0.42] iter 2)
- Watch rate : 65% (légèrement bas car prompt clarifié réduit les downgrades)
- Invariant prob ≥ 0.55 pour direction != watch : ✅ 0 violations

Le fix sémantique a marché : la cohorte n'est plus incohérente. **Mais encore mono-bucket [0.60-0.62]** sur ce sample. Pourquoi : tous les real samples sont des newsletters tech opinion = evidence plafond = moderate. Les synthétiques strong sortaient 0.72-0.77. **La diversité de la cohorte directionnelle dépend de la diversité d'évidence, qui dépend du sourcing**.

Conclusion : on a bouclé sur la limite originale #2 (*« le pipeline génère majoritairement des narratives faibles »*). Le scorer est maintenant correct ; les inputs sont uniformes. **Le vrai prochain fix de diversité = sourcing**, pas le scorer.

## Itération 4 — le sourcing n'est pas le problème non plus

Pushback final mérité : *« avant d'acheter une seule source de plus, vérifier que tes signal_types catalyst/data atteignent seulement le scorer. Un sample 100% newsletter suggère que tes sources haute évidence sous-coulent face aux newsletters. Tu as peut-être déjà les bonnes sources ; elles n'arrivent juste pas jusqu'au scorer. »*

Diagnostic 5 minutes :

```
filings_8k_log    :  43 rows   (8-K classifiés catastrophic/high/medium)
insider_snapshots : 378 rows   (Form 4 ingérés via shared/edgar.py)
─────────────────────────────
Total données primaires : 421 rows présentes en DB
sources.type unique : 'newsletter' (rien d'autre)
```

**Les sources primaires existent. Le code d'ingestion tourne. Mais aucune ne génère de rows dans `signals`.** EDGAR + 8-K coulent dans des tables parallèles. Le scorer V2 voit 100% newsletter parce que c'est tout ce qui entre dans `signals → V2 → predictions`.

L'hypothèse "wire 8-K + insider dans signals débloque la diversité prédite par V2" est **plausible mais non vérifiée**. Je n'ai pas vu une vraie 8-K severity=high traverser V2 et sortir un call strong à 0.75+. Format mismatch possible (le `title`/`summary` d'une 8-K ne ressemble pas à celui d'un earnings release synthétique). Severity→evidence translation non testée.

**Capture du diagnostic, pas commit de la conclusion.** Publier "wirer résout tout" avant de l'avoir vu = commettre dans le post le péché exact dont parle le post.

Sous-décision masquée : backfiller les 421 lignes historiques ou forward-only ? Backfiller = 378 prédictions stale-dated = nouvel artefact temporel (cousin du cluster horizon=30 résolu au sprint précédent). Décision non triviale, à trancher délibérément en session fraîche.

## L'arc, en une phrase publiable (draft)

*« Audit pré-batch → mono-bucket → V2 cassé spread → cassé sémantique → cassé frontière commit → bouclé sur "sourcing" → bouclé sur "wiring sourcing" → vérification pending. À chaque étape, j'allais conclure. À chaque étape, vérifier d'abord m'a fait trouver le vrai bug une couche plus bas. »*

## Trois vigilances pour la suite

1. **Watch-rate distribution dans le temps**. Si on tend vers 50%+ watch sur 4 semaines, on a re-créé une ancre par défaut côté refus. Dashboard : "predictions registered/watch/skipped per week".

2. **Distribution prob de la cohorte DIRECTIONNELLE dans le temps** (vigilance ajoutée iter 2). Si 80% des directional sont [0.38-0.42] sur 4 mois, c'est mono-bucket déménagé une fois de plus. Healthy = voir du 0.25 et du 0.75 apparaître naturellement quand l'évidence le justifie.

3. **Sonnet bump vs config.signal_scoring=Haiku**. V2 utilise `tier="enrich"` (Sonnet 4.6) alors que `config.signal_scoring="extract"` (Haiku 4.5). **Décision délibérée** : le scoring 3-étapes exige du raisonnement structuré, Haiku ne tient pas la qualité. Coût modélisé : 40 signals/jour × Sonnet ≈ $0.20/jour, $6/mois. Si on baisse Haiku plus tard pour économiser, A/B délibéré, pas de drift silencieux.

---

## Pourquoi ce log compte pour le pitch

Le narratif on-thesis pour Anthropic (et tout évaluateur qui pense en calibration) :

> *« J'ai bâti un forecaster, audité avant un point de mesure dur, découvert que mes probabilités s'effondraient sur un bucket [0.60-0.66] et que 2/3 de mes calls étaient non-engageants. Diagnostic : formule cap + bootstrap mort + filter étroit. Première tentative de fix : prompt 3-étapes. Premier pass : range élargi mais 62% watch — j'étais sur le point d'intégrer. Pushback adversaire : "tu n'as vérifié que la moitié basse". J'ai construit une échelle synthétique 4 niveaux, identifié un bug d'implémentation (source contamine le scoring), corrigé, re-vérifié, intégré. Le batch 10/06 est perdu pour la calibration — assumé. La cohorte suivante a maintenant un scorer qui peut produire 0.38 ou 0.77 si l'évidence le justifie. »*

C'est exactement le récit de jugement auto-correcteur que le système est censé vendre. **Le bug-et-le-fix EST l'artefact, pas un détour hors du plan**.
