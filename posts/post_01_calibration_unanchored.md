# Post #01 — version bilingue

*Français d'abord, English below. Sept itérations, sept couches, chaque conclusion en avance d'un cran sur la preuve.*

---
---

## 🇫🇷 Comment mon scorer m'a menti, sept couches plus bas

*Un audit qui refusait d'avoir raison trop tôt.*

---

Onze jours avant la première vraie résolution de batch — 40 prédictions dues le 10 juin — j'ai audité les probabilités stockées. Les 40 valaient exactement **0,608, 0,626, 0,628 ou 0,658**. Quatre valeurs uniques. Toutes coincées dans une bande de 5 points. Aucune sous 0,50, aucune au-dessus de 0,72.

Un forecaster dont les probabilités tiennent dans 5 points ne produit pas du jugement probabiliste. Il produit une constante déguisée. Le Brier calculé là-dessus ne teste rien.

**Couche 1.** La cause : une formule `estimate_probability()` capée à [0,50 ; 0,72], plus 64 sources sur 68 bloquées à `credibility=0,50` par défaut parce que la recalibration mensuelle exigeait 10 résolutions par source et j'en avais 6 au total. Bootstrap mort. Tentation : *« la maturité des données va régler ça. Pivot du plan : publier le raisonnement, pas la calibration. »* Faux. Le temps ne casse pas un mono-bucket. Dans quatre mois j'aurais juste plus de 0,63.

**Couche 2.** Réécriture par prompt. Trois étapes explicites au LLM : énoncer le base rate sans regarder le signal (proche 0,50 — *pas* de 0,6 par confort) ; lister l'évidence et la magnitude de l'écart ; justifier en une phrase pourquoi ce n'est ni 0,50 ni 0,90. Si rien ne tient, `direction="watch"` et la prédiction sort du ledger. Premier test sur 8 signaux : range [0,44 ; 0,54], watch rate 62 %. Mieux. Tentation : intégrer.

**Couche 3.** Pushback : *« tu as vérifié le bas. Le haut, tu ne l'as pas vu. »* Je construis une échelle synthétique de 4 niveaux d'évidence sur NVDA. Le cas le plus fort sort `prob=0,520 watch`. Bug catastrophique apparent — sauf que je lis l'`anti_anchoring_reason` : *« la source est explicitement synthetic_test, donc… »*. J'avais injecté `source_name` dans le prompt. Le LLM downgradait sa lecture parce qu'il ne reconnaissait pas la source. C'est exactement le bug que mon architecture corrige côté credibility downstream — appliqué dans le prompt que j'avais écrit deux heures plus tôt. Je retire le champ. Re-test : `0,770 bullish strong`. Le plafond marchait. Je ne lui avais pas donné d'inputs propres.

**Couche 4.** Re-test des 8 réels post-fix : watch rate tombe à 12 %. Beau chiffre. Pushback : *« 62 % était peut-être un artefact. 12 % n'est pas vérifié non plus. »* Trois signaux d'évidence faible logués comme bullish 0,54 ou bearish 0,43. La spec disait *« si rien ne soutient une direction falsifiable, watch »*. Faible ≈ narrative vague ≈ non-falsifiable. Enforcement durci : `evidence ∈ (none, weak) → watch`. Watch rate remonte à 75 %, défendable cette fois.

**Couche 5.** Cohorte directionnelle restante : tous bearish à `0,38–0,42`. Techniquement passé, sémantiquement cassé. Bearish 0,38 veut dire *« je suis 38 % confiant que mon call bearish est correct »*. Ce qui veut dire que je suis 62 % confiant que bullish est correct. Pourquoi je logue bearish ? Le LLM confondait `P(call correct)` avec `P(price up)`. Le resolver scorait en mode Brier. Mon ledger allait évaluer des valeurs définitionnellement incohérentes — garbage silencieux. Fix : sémantique explicite dans le prompt, et `prob < 0,55 → watch`. On ne commit pas si on n'est pas plus sûr que pile-ou-face.

**Couche 6.** Cohorte refixée : encore mono-bucket [0,60 ; 0,62]. Le scorer convergeait sur ~0,60 pour tous les signaux faibles. Conclusion tentante : *« il faut diversifier le sourcing. »* Pushback plus net : *« avant d'acheter du nouveau, vérifie que tes sources fortes atteignent le scorer. »* Cinq minutes de SQL : `filings_8k_log` 43 lignes, `insider_snapshots` 378 lignes. **421 lignes de données primaires** ingérées par du code qui tourne, dans des tables parallèles qui ne touchent jamais le pipeline de scoring. J'avais EDGAR. Je n'avais juste pas branché EDGAR.

**Couche 7.** Je passe 3 vraies 8-K à V2. Toutes sortent `prob=0,500 watch ev=none`. Verbatim sur NVDA Q1 (un *earnings*) : *« boilerplate cover page only, no actual earnings data »*. L'URL stockée pointait vers la couverture du filing. Le contenu réel — earnings tables, press release — vivait dans des exhibits attachés. J'écris l'extracteur. Re-test : NVDA → **0,750 bullish strong** ✅. Je code le wire forward, j'écris trois tests unit. Le troisième fail — je découvre que mes deux premiers tests **polluaient la prod**. Mon `monkeypatch` ciblait `_DB_PATH` mais `storage.db()` utilise `DB_PATH` (sans underscore). Sans le fail du troisième test, j'aurais shippé un harnais qui crée des signaux fantômes en prod à chaque CI run.

---

Sept itérations. Sept couches. À chaque *« ah, j'ai trouvé »*, vérifier d'abord a fait apparaître le vrai bug une couche plus bas. Cap formule → prompt → contamination source → seuil de commit → sémantique → wiring → extraction → tests qui polluent prod.

**La leçon : la conclusion est toujours en avance d'un cran sur la preuve.** Même un test qui PASSE peut cacher un bug. Le seul filet, c'est la couche que tu n'as pas encore vérifiée.

Reste à faire : tourner le pipeline 30 jours avec V2 wiré, voir si la cohorte directionnelle diversifie quand de vraies 8-K material arrivent. Je ne suis pas développeur — je traque mon propre outil comme je traquerais une thèse fragile. C'est exactement ce que le système est censé faire.

---
---

## 🇬🇧 How my forecaster lied to me, seven layers deep

*An audit that wouldn't agree to be right too early.*

---

Eleven days before my first real batch resolution — 40 predictions due June 10 — I audited the stored probabilities. All 40 had values of exactly **0.608, 0.626, 0.628, or 0.658**. Four unique values. All packed into a 5-point band. None below 0.50, none above 0.72.

A forecaster whose probabilities fit inside 5 points isn't doing probabilistic forecasting. It's producing a constant in disguise. The Brier score on that measures nothing.

**Layer 1.** The cause: an `estimate_probability()` formula capped at [0.50, 0.72], plus 64 of 68 sources stuck at default `credibility=0.50` because monthly recalibration required 10 resolutions per source and I had 6 in the entire database. Bootstrap deadlocked. The tempting conclusion: *"data maturity will fix this. Pivot the publication plan: publish reasoning, not calibration."* Wrong. Time doesn't break a mono-bucket. In four months I'd just have more 0.63s.

**Layer 2.** Prompt rewrite. Three explicit steps for the LLM: state the base rate ignoring the signal (near 0.50 — *not* 0.6 *pour le confort*); list the evidence and the magnitude of the deviation; justify in one sentence why the probability is neither 0.50 nor 0.90. If nothing holds, `direction="watch"` and the prediction never enters the ledger. First test on 8 signals: range [0.44, 0.54], watch rate 62%. Better. Tempting to ship.

**Layer 3.** Pushback: *"you verified the floor. You haven't seen the ceiling."* I build a synthetic 4-level evidence scale on NVDA. The strongest case returns `prob=0.520 watch`. Looks broken — until I read the `anti_anchoring_reason`: *"the source is explicitly synthetic_test, so…"*. I'd injected `source_name` into the prompt. The LLM was downgrading its own evidence reading because it didn't recognize the source. The exact bug my architecture was designed to fix by applying credibility downstream — committed inside the prompt I'd written two hours earlier. Strip the field. Re-run: `0.770 bullish strong`. The ceiling worked. I just hadn't fed it clean inputs.

**Layer 4.** Re-test the 8 real signals post-fix: watch rate drops to 12%. Looks great. Pushback: *"62% might have been the artifact. 12% isn't verified either."* Three weak-evidence signals were logged as bullish 0.54 or bearish 0.43. The spec said *"no falsifiable evidence → watch"*. Weak ≈ vague narrative ≈ not falsifiable. Harder enforcement: `evidence ∈ (none, weak) → watch`. Watch rate climbs back to 75% — and this time I have a principled reason to call it healthy.

**Layer 5.** Remaining directional cohort: all bearish at `0.38–0.42`. Technically passing, semantically broken. A bearish 0.38 means *"I'm 38% confident the bearish call is correct"* — which means I'm 62% confident bullish is correct. Why am I logging bearish? The LLM was conflating `P(call correct)` with `P(price up)`. My resolver scored Brier-style. The ledger was about to evaluate definitionally incoherent values — silent garbage, the worst kind. Fix: explicit semantics in the prompt, plus `prob < 0.55 → watch`. You don't commit if you're not more confident than a coin flip.

**Layer 6.** Re-fixed cohort: still mono-bucket [0.60, 0.62]. The scorer was converging on ~0.60 for every weak signal. Tempting conclusion: *"diversify the sourcing."* Sharper pushback: *"before buying new sources, verify your strong ones reach the scorer."* Five minutes of SQL: `filings_8k_log` 43 rows, `insider_snapshots` 378 rows. **421 rows of primary data** ingested by code that runs daily, sitting in parallel tables that never touch the scoring pipeline. I had EDGAR. I just hadn't wired EDGAR.

**Layer 7.** I pass 3 real 8-K through V2. All return `prob=0.500 watch ev=none`. Verbatim on an NVDA earnings filing: *"boilerplate cover page only, no actual earnings data"*. The stored URL pointed to the filing's cover. The actual content — earnings tables, press release — lived in attached exhibits. I write the extractor. Re-test: NVDA → **0.750 bullish strong** ✅. I code the forward wire, write three unit tests. The third one fails — and I discover that my first two tests had been **polluting the production database**. My `monkeypatch` targeted `_DB_PATH` but `storage.db()` uses `DB_PATH` (no underscore). Without the third test failing, I'd have shipped a test harness that silently created phantom signals in prod on every CI run.

---

Seven iterations. Seven layers. Every *"ah, I found it"*, verifying first surfaced the real bug one layer deeper. Formula cap → prompt → source contamination → commit threshold → semantics → wiring → extraction → tests that pollute prod.

**The lesson: the conclusion is always one step ahead of the proof.** Even a test that PASSES can hide a bug. The only safety net is the layer you haven't checked yet.

Still open: run the pipeline for 30 days with V2 wired, see if the directional cohort actually diversifies when real material 8-K start flowing through. I'm not a developer — I track my own tool the way I'd track a fragile thesis. Which is exactly what the system is supposed to do.
