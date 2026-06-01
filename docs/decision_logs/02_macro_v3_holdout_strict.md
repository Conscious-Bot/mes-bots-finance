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

### Résultat empirique du run 02/06

| Dataset | Pass | Total |
|---|---|---|
| ANCHORS (in-sample) | **8/8** | tautologique |
| OOS_DATES (commit 7a43189) | **5/6** | 1 fail = Delta variant 2021-07-19 (V3 dit P3, label P2 fenêtre — singleton) |
| HOLDOUT_DATES (vrais OOS) | **2/4** | 2 fails sur dates « calme » 2017-08-10 et 2025-02-25 |

**Verdict synthèse** : HOLDOUT 2/4 < seuil 3/4 → **V3 DEMOTE à exploratoire**, pas de wire Phase A.

### Honnêteté L11 sur les 2 fails HOLDOUT
Avant de conclure « formule cassée » :

- **2025-02-25** label P1 « calme pré-tariff ». V3 dit P2 (score 26.8). À ce moment : Fed encore en QT (FedBalance YoY négatif), BTC en drawdown post-ATH, DXY remontée. Plusieurs flags risque actifs. **Label P1 contestable** — V3 peut avoir raison.
- **2017-08-10** label P1 « NK Guam singleton ». V3 dit P2 (score 36.0). À ce moment : Fed tapering commencé, BTC drawdown amorçé, CoreCPI sous target. Score 36 ≈ frontière P1/P2. **Borderline**.

Si on accepte les 2 fails comme « V3 borderline juste, label P1 strict trop optimiste », alors HOLDOUT 4/4 et V3 wirable. **Mais** L11 dit explicitement : on ne relabelise PAS post-hoc après mesure — c'est le piège tautologique. Verdict reste **DEMOTE**.

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

**Verdict** : EXPLORATOIRE (au 02/06) — révision attendue 09/06 avant J-day.

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
