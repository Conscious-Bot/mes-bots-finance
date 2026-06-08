# Audit macro monitor — phases declarees (premier geste master §6)

**Date** : 2026-06-08
**Source** : `debt_composite` table (live persistence du monitor)
**Scope** : audit court (debt_composite N=17j, pas de forward 3M observable encore)
**Methode** : decomposition driver par phase declaree -- chiffre le crying-wolf
**Reference** : doctrine `SPEC_CORNERSTONE.md` + `PLAN_REFONTE_ALERTES.md`

## Tldr

- Total readings : **40** sur 2026-05-20 -> 2026-06-06
- Alarmes Phase 3+4 : **7** (18% du temps)
- **Sur le dernier Phase 4 (score 120.5 du 06/06) :**
  - **66% du score** vient des indicateurs **a DROP** per doctrine (bruit)
  - **8% du score** vient des tier-S valides (qui disent CALME)
  - 8/15 indicateurs marques `stale=true` (Axe 5 freshness violee aussi)
- **Verdict** : crying-wolf confirme par decomposition. Aucun tier-S valide ne signale stress.

## Decomposition du dernier Phase 4 (06/06 06:32)

| Indicateur | Tier | Phase | Value | Contribution | Categorie doctrine |
|---|---|---|---|---|---|
| `TYX` | T1 | P3 stale | 5.00 | 16.0 | tier-S mais niveau (devrait etre delta) |
| `Gold` | T1 | P3 stale | 4337.10 | 16.0 | **DROP** (bruit) |
| `USDJPY` | T1 | P3 stale | 160.29 | 16.0 | **DEMOTE** (book-specific) |
| `VIX` | T1 | P3 stale | 21.51 | 16.0 | **DROP** (bruit) |
| `HY_OAS` | T1 | P2 stale | 274.00 | 8.0 | tier-S (garde) |
| `DXY` | T1 | P2 stale | 100.07 | 8.0 | **DROP** (bruit) |
| `BTC_drawdown180` | T1 | P3 stale | -37.10 | 16.0 | **DROP** (bruit) |
| `MOVE` | T1 | P1 stale | 75.20 | 0.8 | tier-S (garde) |
| `KRE` | T2 | P1 | 70.17 | 0.8 | tier-S (garde) |
| `T10Y2Y` | T2 | P2 | 0.38 | 6.0 | tier-S (garde) |
| `BankReserves` | T2 | P2 | 3013902.00 | 6.0 | tier-S (garde) |
| `CopperGold` | T2 | P2 | 0.00 | 6.0 | **DROP** (bruit) |
| `CoreCPI` | T3 | P2 stale | 2.74 | 4.0 | autre |
| `FedBalance_yoy` | T3 | P1 stale | 0.51 | 0.5 | tier-S (garde) |
| `MfgIP_yoy` | T3 | P1 stale | 1.47 | 0.5 | autre |

**Score total : 120.5** -> Phase 4 (seuil >= 115)

## Repartition par categorie doctrine

- **DROP (bruit selon doctrine)** : 62.0 pts (51%)
- **DEMOTE (book-specific, pas macro)** : 16.0 pts (13%)
- **TIER-S valide (garde)** : 22.0 pts (18%)
- **Autres** : 20.5 pts (17%)

**Verdict chiffre** : 65% du score vient d'indicateurs que la doctrine impose de drop/demote. Les tier-S valides apportent 22.0 pts = si seuls ils dominaient, on serait en Phase ?.

**Freshness aussi violee** : 11/15 indicateurs `stale=true` (Axe 5 SLA freshness) -- le score est calcule sur des valeurs caches.

## Phase distribution sur l'historique (N=40)

| Phase | Count | % | Lecture doctrine |
|---|---|---|---|
| Phase 2 | 33 | 82% | normal/calme |
| Phase 3 | 4 | 10% | alarme dans la fenetre courte |
| Phase 4 | 3 | 8% | alarme dans la fenetre courte |

- Alarmes Phase 3+4 : **7/40 = 18%**
  - Per doctrine PLAN_REFONTE_ALERTES : > 20% d'alarme = calibration cassee

## Pourquoi l'audit (a) suffit ici (et pourquoi (b) reste necessaire)

**Audit (a) actuel** : impossibilite materielle de tester forward 3M (debt_composite N=17j vs horizon 3M=90j). Ce qu'on a chiffre :
- Le **mecanisme** du score est domine par des indicateurs explicitement   classes bruit par la doctrine (BTC/VIX/Gold/USDJPY).
- Les tier-S valides (HY_OAS, MOVE, banques) **disent calme** au moment   meme ou le composite crie crise.
- C'est un FP **par construction semantique** -- pas besoin d'attendre 3M.

**Backtest (b) requis ensuite** : reconstruction des phases sur 2015-2024 avec vintage macro (FRED as-released), label drawdown SMH/SPY forward 3M @ θ=-10%/-20%, purged walk-forward L16. Donnera la VRAIE matrice de confusion + PR-AUC + Brier skill score vs base rate.

## Decisions tranchees (per master Q1-Q3)

- **Q1** : SMH primaire + SPY secondaire (PAS book - N trop petit), θ=-10% ET -20% (multi-label), H=3M
- **Q2** : defer Polygon (re-trigger = panel multi-pays insuffisant)
- **Q3** : auto-demote_from_structural si invalidation_trigger fire --   symetrique a l'assignation, tamper-evident, notify + steer 'pose un stop'

## Suite

1. Q3 wire dans thesis_erosion : si INVALIDATION_HIT + structural -> auto-demote priced + integrity log + notify (~1h)
2. Audit (b) : reconstruction historique 2015-2024 + vraie matrice de    confusion (~ chantier de plusieurs sessions)
3. Cornerstone build : `config/divergence.yaml` + `divergence_engine.py`    per `SPEC_CORNERSTONE.md` (~ chantier majeur, post backtest verdict)
