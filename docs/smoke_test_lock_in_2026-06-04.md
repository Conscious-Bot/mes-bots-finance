# Smoke-test lock_in_detector — 04/06/2026

**Statut** : smoke-test honnête, N=5 brut / N=2 in-scope. Pas une preuve.
**Doctrine** : cf L13 (LESSONS) + memory `retrospectif_plafonne`.
**Règle figée** : détecteur tel qu'il existait au 04/06 (lock_in_detector.py commit `dc3ee2d`+), pas retuné après regard.

## Genèse

Tentative initiale : backtester sur signature trades user (PLTR, NVDA, SOFI, Marvell, Teradyne historiques). **Bloqué par construction** : ces trades précèdent l'instrument PRESAGE (chat earliest 2026-05-29 ; thesis tracker artefact post-2026-05-16 ; SOFI = 0/6 sells avec PIT thesis ; TER N=6 row finalement triplement contaminée). Cf `retrospectif_plafonne`.

Pivot : utiliser les **sells post-bot avec thesis timestamp antérieur**. Set initial N=6 (ALAB, MU, CCJ, SNOW, TER, VRT), réduit à **N=5** après retrait TER (contamination confirmée).

Labels user posés AVANT regard sur verdicts (Garde 1 + Garde 2 respectées dans l'ordre — sauf clarification ALAB qui a corrigé un mislabelling initial, le bon réflexe : prendre l'explication factuelle "j'ai suivi la règle système first-target" comme dominante).

## Cas et labels (gelés)

| Ticker | conv | PnL% | Target | Label user | Raison user (sans le bot) | Verdict détecteur | Gate fired | Cellule |
|---|---|---|---|---|---|---|---|---|
| ALAB | c3 | +52.5% | +50% | `good_exit` | "système first-target rule, on a passé first target" | no_flag | pnl > halfway (52.5% > 25%) | **TRUE NEGATIVE** ✓ |
| MU | c3 | +27.1% | +50% | `size_rebalance` | "doublon avec SK Hynix + first-target" | no_flag | pnl > halfway | HORS SCOPE (rebalance) |
| CCJ | c5 | +4.0% | +55% | `size_rebalance` | "rebalancing de size ponctuel" | no_flag | 15% floor block | HORS SCOPE (rebalance) |
| SNOW | c3 | +18.6% | +45% | `good_exit` | "thèse conclue / surévaluation à T" | **flag** (bias_event id=5) | pnl ∈ [15%, halfway] | **FALSE POSITIVE** |
| VRT | c2 | −4.1% | +40% | `loss_cut` | sortie de perte, pas un winner | no_flag | not winner | HORS SCOPE (par design) |

## 2×2 effectif (N=2 in-scope : ALAB + SNOW)

|  | label = good_exit | label = lock_in |
|---|---|---|
| detector flag | **1 (SNOW)** | 0 |
| detector no_flag | **1 (ALAB)** | 0 |

- **Précision** = 1/2 = 50% (branche flag uniquement)
- **Recall** = indéfini (0 cas lock_in vrais dans l'échantillon)
- **N=2 trop petit** pour conclure quoi que ce soit sur taux FN/FP en général.

## Findings structurels (gardés)

### Finding #1 — SNOW FP : `thesis_status_change` pas capté au sell

**Mécanique de l'échec** : SNOW a `theses.status='active'` au moment de la vente, mais l'user avait mentalement conclu la thèse (raison déclarée : surévaluation). Le détecteur lit `status='active'` → applique les gates → flag.

**Levier structurel** : forcer un radio button au sell — `concluded | target_hit | invalidated | rebalance | other` — qui update `theses.status` AVANT le commit du sell event. Le détecteur lit alors `status != 'active'` et skip naturellement.

**Tracé** : TODO `#109 Sell-UX radio status_change forcé avant commit`. Post-J-day.

### Finding #2 — Catégorie `size_rebalance` émerge dominante (3/5 sells)

CCJ, MU (+ Lasertec hors-N5) tous motivés par "size / doublon / cluster", pas "target / PnL". Le détecteur n'a pas de garde `cluster_doublon_state` (seulement `overcap_state`). Les trois sont correctement laissés en no_flag, donc pas un faux positif — mais la **catégorie elle-même** mérite logging distinct.

**Levier** : event_type `size_rebalance` avec champ `cluster_doublon_with: <ticker>` à logger au moment de la vente. Pas urgent (pas un échec détecteur), mais utile pour la track-record des décisions de sizing.

**Statut** : pas de TODO créée. À revoir si forward montre que cette catégorie est encore plus dominante.

### Finding #3 — INVALIDÉ : "ALAB FN par target mental sous-déclaré"

**Hypothèse initiale** (fausse) : ALAB vendu à +52.5% sur target logué +50% avec thèse "intacte" → mental target plus haut → détecteur loupe par sous-déclaration de target.

**Correction user** : la vraie raison était "système first-target rule, on a passé first target". Donc ALAB = good_exit discipliné par règle système, pas lock_in. Détecteur correctement no_flag. Pas de levier `thesis_target_revisit` nécessaire.

**Leçon** : "thèse intacte + prise de profit" est ambigu. Demander la **règle qui a tiré la décision** désambiguise.

## Anti-patterns évités (Gardes 1+2)

- ❌ Re-tuner le 15% floor à conviction-conditionnelle pour faire flag CCJ (CCJ s'est révélé hors scope → re-tune n'aurait servi à rien)
- ❌ Concevoir un "campaign detector" avec paramètre de fenêtre libre (= contamination déplacée dans la règle)
- ❌ Reconstruire PIT inputs SOFI/PLTR/NVDA depuis souvenir (= hindsight contamination en blouse blanche)
- ❌ Re-export broker pour combler (b) per-share quand (c) thesis-à-T est de toute façon absent

## Décisions de scope honnêtes

- **Tranche 1 backtest historique** (PLTR/NVDA/SOFI/Marvell) → mort par construction. Documenté.
- **D1 round-trip agrégation** (SOFI +16%, TER +93%) → P&L réalisé EUR sans label détecteur. Pas évalué.
- **D2 per-event PIT** → mort (data fragmentée par tranches).
- **D3 campaign-window** → refusé (paramètre libre = contamination).
- **Campaign detector** → refusé (pas de label pré-enregistré possible, paramètres libres).

## Plafond honnête

- N=2 in-scope = smoke-test, pas inférence statistique.
- 1 levier structurel défendable (#109).
- Le reste se passe **en forward** : chaque nouvelle vente loggée proprement (avec radio button #109 actif) fera grossir le N propre.
- Le track-record lock_in commence à `bias_event id=5` (SNOW, résolution 2026-09-01) — premier point empirique réel. Toute analyse statistique attend N >> 10.

## Pas d'autre chantier issu de ce smoke-test

- Pas de re-tune détecteur.
- Pas de scaffold backtest scalé sur les 45 prédictions (différent appareil, garde-relations claires).
- Pas de feature `thesis_target_revisit`.
- Pas de feature `campaign_detector`.
