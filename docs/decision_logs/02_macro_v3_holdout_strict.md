# Decision Log #02 — Macro composite V3 holdout strict (task #67)

**Date** : 02 juin 2026
**Owner** : Olivier Legendre
**Trigger** : Task #67 — V3 tuné in-sample 01/06 (task #42), affirmation commit `7a43189` « 7/8 OOS validé » jamais code-validée. L9 + L11 exigent verdict OOS rigoureux **AVANT** tout wire prod du sizing macro→phase.
**Outcome** : V3 **reste exploratoire** — pas de wire Phase A. HOLDOUT strict non concluant.

---

## Le contexte / Le bug / La friction

V3 livré commit `7a43189` (29/05) avec relabel L11 (2019-06 P1→P2) et 3 transformations structurelles (BTC_drawdown180, FedBalance_yoy, MfgIP_yoy seuil −5%).

Le commit message revendiquait « 7/8 dates non-anchor + 5/5 fenêtres soutenues » comme validation OOS — mais le **code de validation OOS n'existait pas** dans le script `scripts/backtest_macro_composite.py`. Le verdict reposait sur des mesures manuelles non reproductibles.

L9 dit : pas de wire prod sur un modèle non backtesté. L11 dit : le backtest doit reposer sur des anchors empiriquement vérifiés, pas labellisés au feeling.

---

## La cause racine / L'analyse

Investigation en couches :

**Surface** : Affirmation « 7/8 OOS » dans le commit message. Pas reproductible automatiquement.

**Cause technique** : Le `OOS_DATES` était défini dans le script mais aucune fonction `report_oos_strict()` ne l'utilisait. Seul `report_anchors()` tournait.

**Cause méthodologique** : Risque tautologique signalé par memory `feedback_in_sample_tuning_validation` — « si l'agent introduit N dof contre M anchors, X/M validés est tautologique ».

**Cause structurelle** : L'absence de séparation tune/holdout est le pattern classique de surfit. Le **HOLDOUT strict** (dates jamais utilisées pour tune ni labellisation post-hoc) est le seul vrai test.

---

## La décision

### Implémentation (commit à suivre)
1. **`report_oos_strict()`** ajouté au script : mesure phase V3 sur 2 datasets disjoints (OOS_DATES historiques + HOLDOUT_DATES nouvelles).
2. **HOLDOUT_DATES = 4 nouvelles dates** jamais utilisées pour tune/labellisation antérieure :
   - `2020-09-23` Stress post-COVID (P3 attendu)
   - `2022-09-26` UK gilts + GBP crash (P3 attendu)
   - `2025-02-25` Calme pré-tariff (P1 attendu)
   - `2017-08-10` NK Guam threat singleton (P1 attendu)
3. **Verdict logic** : HOLDOUT pass ≥ 3/4 + OOS ≥ 4/6 → V3 wirable. Sinon demote à exploratoire.
4. **Snapshot CSV** : `docs/backtests/debt_composite_2017_2026_v3_holdout_02_06.csv` (reproductible).

### Résultat empirique vague 1 (02/06 matin, 4 HOLDOUT)

| Dataset | Pass | Total |
|---|---|---|
| ANCHORS (in-sample) | **8/8** | tautologique |
| OOS_DATES (commit 7a43189) | **5/6** | 1 fail = Delta variant 2021-07-19 (V3 dit P3, label P2 fenêtre — singleton) |
| HOLDOUT_DATES (vague 1) | **2/4** | 2 fails sur dates « calme » 2017-08-10 et 2025-02-25 |

### Résultat empirique vague 2 (02/06 après-midi, 8 HOLDOUT)

HOLDOUT enrichi avec 4 dates additionnelles à régime CLAIR (Goldilocks 2017, sell-off oct 2018, COVID circuit breakers, Q1 2024 sticky CPI).

| HOLDOUT date | Label | V3 phase | V3 score | Verdict |
|---|---|---|---|---|
| 2020-09-23 stress post-COVID | P3 | P3 | 79.8 | ✓ |
| 2022-09-26 UK gilts | P3 | P3 | 83.0 | ✓ |
| 2025-02-25 calme pré-tariff | P1 | **P2** | 26.8 | ✗ |
| 2017-08-10 NK threat | P1 | **P2** | 36.0 | ✗ |
| 2017-12-15 Goldilocks (VIX 9.5) | P1 | **P2** | 36.0 | ✗ |
| 2018-10-29 sell-off oct (VIX 27) | P3 | **P2** | 53.0 | ✗ |
| 2020-03-12 COVID circuit breakers | P4 | P4 | 142.0 | ✓ |
| 2024-04-15 Q1 2024 sticky CPI | P2 | P2 | 32.0 | ✓ |

**Synthèse : HOLDOUT 4/8** (50%) < seuil 75%. **V3 DEMOTE à exploratoire** confirmé.

### Diagnostic structurel (pattern observé, pas du bruit)

**Biais centriste P2 systématique** :
1. **3/3 dates labelées P1 fail toutes** → V3 répond systématiquement P2, jamais P1. Le score minimum observé sur ces dates « calmes » est 26-36, alors que la frontière P1/P2 est probablement ~25. Goldilocks 2017 avec VIX 9.5 record low et S&P ATH calme → V3 score 36 (= score le plus bas pour P2). **La formule ne génère jamais de P1**.
2. **1/1 sell-off net P3 fail** (oct 2018) → V3 dit P2 (score 53). Sell-off -10% S&P en 30j + VIX 27 + Fed hawkish + tech massacre = P3 sans ambiguïté. V3 sous-estime le stress.

**Origine probable** :
- **Frontière P1/P2 trop basse** : la combinaison BTC_drawdown180 + FedBalance_yoy injecte un floor de stress structurel qui empêche P1 même en régime calme.
- **Frontière P2/P3 trop haute** : V3 demande trop d'indicateurs co-firing pour passer P2→P3 (manque d'expression de la vélocité du sell-off).

**Conclusion** : V3 n'est pas borderline juste sur quelques labels contestables — V3 est **structurellement biaisée vers P2** (centre de gravité). Le pattern est trop systématique pour relabel post-hoc.

---

## INVALIDANTS EX-ANTE (premortem)

| # | Observable | Seuil de révision | Horizon mesure |
|---|---|---|---|
| 1 | HOLDOUT ajouté avec 4 dates additionnelles plus robustes (régime clair P1/P3/P4 unambigous) | pass ≥ 6/8 sur 8 holdout total | 09/06/2026 (avant J-day) |
| 2 | Sanity-check empirique 2017-08-10 + 2025-02-25 via FRED réels (VIX, courbe, IPMAN à ces dates) | label P1 confirmé par 3+ indicateurs | 09/06/2026 |
| 3 | V3 wire Phase A déclenché sans verdict HOLDOUT clos | toute trace de promotion sans verdict ≥ 75% | continu |

**Engagement** : si HOLDOUT enrichi reste < 6/8 ou si la sanity-check des 2 fails confirme P1, V3 reste exploratoire et on tente V4 (changement structurel formule, pas tweaks de seuils).

---

## Métriques de succès

| Métrique | Cible | Date d'évaluation |
|---|---|---|
| HOLDOUT enrichi (8 dates min) pass rate | ≥ 6/8 | 09/06/2026 |
| Tous fails HOLDOUT documentés avec sanity-check FRED | 100% | 09/06/2026 |
| Sizing Phase A wire sur frise visible dashboard | si verdict OK | post-09/06 |

---

## Outcome (à remplir post-horizon 09/06)

[À remplir après enrichissement HOLDOUT + sanity-check 2 fails.]

**Verdict** : EXPLORATOIRE — pas de wire Phase A. V4 nécessaire (changement structurel, pas tweaks de seuils).

**Pistes V4 prioritaires** (à explorer post J-day, pas en pré-batch) :
1. **Retirer BTC_drawdown180 du composite** : il pollue le P1 en imposant un floor de stress structurel même en régime calme (BTC est souvent en drawdown même sans stress macro).
2. **Repenser FedBalance_yoy** : YoY négatif en QT permanent depuis 2022 → injecte un biais P2. Considérer un seuil de QT (>= -20% YoY → flag) plutôt qu'un input continu.
3. **Boost frontière P2→P3** : ajouter un indicateur de vélocité (S&P drawdown 30j, MOVE 30j vs moyenne) pour capter les sell-offs nets type oct 2018 que V3 manque.
4. **Frontière P1/P2 ajustée empiriquement** : viser que ~30% des dates 2017-2026 tombent en P1 (au lieu de 0% actuel).

---

## Méta-réflexion

- **Information disponible** : 9 ans données FRED + yfinance, commit message revendiquant 7/8 OOS.
- **Information manquante qu'on aurait pu obtenir AVANT** : sanity-check empirique des 8 anchors + 6 OOS_DATES via lectures FRED individuelles, AVANT de runner le composite. L11 le dit.
- **Biais identifiés en rétro** : motivated reasoning sur la validation OOS du commit 7a43189 (le verdict était posé sans code reproductible). Pattern récurrent — voir L11 origine task #42.
- **Décision optimale ex-post** : ne pas attendre task #67 pour exiger le `report_oos_strict()` automatisé. Aurait dû être bloqué à task #42.
- **Verdict process** : AMÉLIORABLE — le filet est posé maintenant (script reproductible) mais l'arrivée a 14 jours après le V3 tune.

---

## Notes / Références

- Commit `7a43189` : V3 tune (revendication OOS non code-validée).
- Commit `1507439` : LESSON L11 + script reproductible (mais sans report_oos).
- LESSONS L9 (pas de wire sans backtest) + L11 (anchors empiriquement vérifiés).
- Memory `feedback_in_sample_tuning_validation` (origine task #42 01/06).
- CSV snapshot : `docs/backtests/debt_composite_2017_2026_v3_holdout_02_06.csv`.
- Memory `session_roadmap_j_day` : #67 listé comme bloquant avant J-day 10/06.
