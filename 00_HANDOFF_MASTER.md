# 00 — Handoff maître (point d'entrée Claude Code)

> Lis CECI en premier. C'est la distillation d'une session stratégique longue (audit → pivot provabilité → cornerstone cycle×consensus → calibration). Il te donne le contexte, l'ordre de lecture des docs, les décisions verrouillées, la séquence de build, et le contrat de travail. Ne code rien avant d'avoir lu §1-§3 et fait les vérifs §7.

## 1. L'arc en bref — ce qu'on a établi, et pourquoi

1. **Audit** du repo → constat : code propre (ruff, secrets, tests) mais **doctrine architecturale fictive** (invariant single-gateway violé : 48 fichiers `import sqlite3`, 19 `yfinance` hors `prices.py`) et **moteur de calibration qui tourne sur N=35** (84% prédictions non résolues — pas un resolver cassé, juste un système jeune sur horizons 30j).
2. **Pivot central** : l'asset n'est pas « mieux investir » — c'est le **jugement calibré prouvable**. On cesse d'optimiser la *précision du point* (fausse précision sur petit-N) pour rendre hyper-précis le **substrat** (pondération gagnée, sources, fraîcheur, calibration) et **honnêtement coarse** la sortie.
3. **Provabilité** : pré-enregistrement tamper-evident des prédictions (commit-reveal, ancrage OTS externe — un hash chain local ne contraint pas l'opérateur solo).
4. **L'indicateur star = cycle × consensus.** Pas deux indicateurs : **un seul moteur** mesurant la **divergence croyance ↔ réalité livrable**, conscient de sa **phase réflexive**, qui **gouverne le comportement** au lieu de prédire. C'est la racine de la plupart des problèmes de traders (behavior gap) et des deux biais d'Olivier (lock-in, FOMO).
5. **Le tool crie au loup** partout (le macro monitor dit « CRISE 4/4 » piloté par BTC/VIX pendant que les vrais gauges — spreads HY, MOVE, banques — sont calmes). Cause : seuils non-gagnés + indicateurs qui mesurent un *état persistant* pas un *delta*. Cure : le droit d'alarmer se gagne ; vigilance *concentrée* (hair-trigger high-skill, silence sur le bruit) ; **probabilité + trajectoire** au lieu de rouge/jaune/vert.

Fil rouge non-négociable : **fail-closed** (jamais un nombre plus confiant que son évidence), **poids gagnés jamais tapés**, **honnêteté brutale sur le peu qu'on sait**.

## 2. La pile documentaire (ordre de lecture)

| # | Doc | Rôle |
|---|---|---|
| 1 | `QUALITY_BAR.md` | base : M1 (triple valeur/as-of/source), M2 (claim pré-enregistrée), M3 (sizing edge), fail-closed |
| 2 | `CALIBRATION_DOCTRINE.md` | **sous le capot** : poids = skill×orthogonalité×fiabilité-source×stabilité, shrink petit-N, battre l'équipondéré |
| 3 | `PLAN_REFONTE_ALERTES.md` | le droit d'alarmer ; vigilance concentrée ; proba+trajectoire vs R/J/V |
| 4 | `SPEC_CORNERSTONE.md` | **le moteur** divergence-réflexivité (cycle/consensus/crisis gauge = projections) |
| 4b | `SPEC_CONSENSUS_FRAGILITE.md` | projection **micro** (consensus N-riche, calibration réelle) + lentille de fragilité |
| 5 | `METHODE_CALIBRATION_CORNERSTONE.md` | la validation au cordeau (macro N-starved) : labels, purged walk-forward, ECE, matrice de confusion |
| 6 | `HANDOFF_CYCLE_CALIBRATOR.md` | application : l'horloge de cycle |
| 7 | `OPERATIONAL_READINESS.md` | `base_health.py` : rendre la base opérationnelle = un run vert |
| — | `AUDIT_TECHNIQUE.md`, `AMELIORATIONS_ET_IDEES.md`, `VISION_PRO.md`, `SCALE_VISION.md`, `IDEAS_BACKLOG.md` | contexte / stratégie / backlog |

## 3. Décisions verrouillées (ne pas re-litiguer)

- **`position_type` = 3 types d'exit mutuellement exclusifs** : `structural` / `priced` / `tactical`. PAS 6 (mélangeaient des axes). `mega_cap`/`commodity`/`satellite` = tags orthogonaux. Assignation `structural` = **justifiée + pré-enregistrée** (anti-rationalisation).
- **Cron érosion** = event-driven (nouveau signal matériel) + plancher hebdo. Pas daily pur.
- **Position-card** = **page dédiée deep-linkable** (`?ticker=…`), pas modal (les alertes doivent router vers la surface de décision).
- **Crisis gauge** : drop BTC-drawdown (stock-only + bruit) et VIX-primary (symptôme) ; les tier-S (spreads, MOVE, banques, courbe, liquidité) dominent.
- **Sortie** : probabilité calibrée + trajectoire ; jamais rouge/jaune/vert comme info primaire.
- **Inputs disjoints** macro vs micro (zéro champ partagé → pas de double-comptage).
- **Steer** = deux sorties distinctes : `exit_policy` (type×verdict) ET `size_action` (weight vs cap). Jamais fusionnées.

## 4. Questions ouvertes pour Olivier (avant build)

- Cibles du label drawdown (son book / SPY / SMH ? seuils −10/−20% ? horizon ?).
- Source de feed prix : assumer near-live+staleness, ou payer (Polygon/Tiingo) ?
- `demote_from_structural` tracé (si une thèse structurelle casse) : voulu ou pas ?

## 5. Séquence de build unifiée (par dépendance)

```
A. FONDATION DONNÉE (débloque tout — QUALITY_BAR axe 3/5)
   1. Migration positions : tuer eur_value-dans-notes → colonnes typées + price_history/fx_history append-only
   2. prices.get() retourne le triple (val, asof, source) ; gate CI : yfinance hors prices.py = build rouge
   3. base_health.py (le scoreboard ; suit les rouges)

B. PROVABILITÉ (commit-reveal)
   4. bootstrap intégrité prédictions + hook insert_prediction (storage.py:850) + ancrage OTS

C. CORNERSTONE (l'étoile)
   5. config/divergence.yaml : inputs signés-théorie, prior-tiers, temporal_splits
   6. divergence_engine.py : primitive D/Φ/F, fail-closed, bande, inputs disjoints macro/micro
   7. CALIBRATION : matrice de confusion du monitor ACTUEL (le diagnostic chiffré) → puis backtest
      niveau→P(outcome), purged walk-forward, isotonic, ECE, baselines à battre (single-best-indicator)
   8. crisis gauge redessinée (proba+trajectoire+drivers, défaut calme)
   9. consensus thermomètre (projection micro) → lentille de fragilité (interaction)
   10. self-scoring : chaque lecture pré-enregistre une implication via insert_prediction (methodology_version)

D. AIGUILLAGE
   11. moteur d'érosion de thèse (signals depuis opened_at vs drivers/invalidation) — persistance Couche 1
   12. position_steer.py (exit_policy + size_action distincts) → position-card page deep-linkable
```

## 6. Le premier geste (mesurable, falsifiable)

**Rejoue le monitor macro actuel sur l'historique et sors sa matrice de confusion** : combien de fois « CRISE » crié vs combien de crises réelles. Ça transforme « je crois qu'on crie au loup » en un **taux de faux positifs chiffré** = le baseline que la refonte doit battre. Tout le reste s'ancre là-dessus.

## 7. Contrat de travail (verify-before-patch — non négociable)

- **Vérifie le vrai code avant de patcher.** Seams à confirmer : structure `sources` (credibility/half_life), `source_attribution_brier.py`, `calibration.yaml` temporal_splits, funnel `insert_prediction` (storage.py:866), le macro monitor existant (où BTC/VIX pilotent le score), `consensus_thermometer` en cours.
- **Safe-fail** : `assert s.count(old)==1` avant tout replace. Backup DB avant migration.
- **Gates chaînées** : ruff + import + tests après chaque patch.
- **Fail-closed partout** ; **aucun `weight = <float>` littéral** (gate CI) ; **N = épisodes, pas jours** ; **purged walk-forward, jamais k-fold**.
- **Posture crise** : on calibre pour **falsifier le bruit**, pas certifier la prescience (events trop rares).
- **Walking skeleton > squelette pur** (L24) : pour toute abstraction neuve, exiger UN vrai input (fixture deterministe) qui traverse interface → engine AVANT d'investir dans la masse. Le tracer-bullet découvre les formules wrong au moment le moins cher. Si la réponse à "quel est mon tracer-bullet ?" est "des mocks", la doctrine n'est pas respectée — c'est l'erreur fondatrice du cornerstone C6 (formule `D = pricée − livrable` corrigée par découverte tracer-bullet en `D = aggregate global` — cf SPEC_CORNERSTONE §1 erratum).

## 8. Ligne de lancement

> Lis `00_HANDOFF_MASTER.md` en entier, puis la pile §2 dans l'ordre. Ne code rien avant : (a) avoir fait les vérifs de seams §7, (b) avoir produit le **premier geste §6** (matrice de confusion du monitor actuel). Rapporte ce diagnostic chiffré + les seams trouvés AVANT d'attaquer la séquence §5. Respecte les décisions verrouillées §3 et les questions ouvertes §4 (demande à Olivier, ne tranche pas seul).
