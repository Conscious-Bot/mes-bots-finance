# Spec THESIS ALPHA RESOLVER — variant-perception, fx-strippé, régime-strippé (canon 2026-06-11)

> **Le track-record alpha mesure si tu bats le consensus dans la devise native de l'action — pas si tu bats le marché.** Tu poses un pari contre la foule (`your_delta = ta_target − consensus_pt`), le resolver mesure 12 mois plus tard si l'action a effectivement bougé dans ton sens vs ce que le consensus attendait. Le bêta (régime, fx) est strippé par construction. C'est l'instrument qui dit "skill de variant perception" — distinct du Brier signal (return absolu court-terme), distinct du P&L EUR (mélange devise + bêta + skill). Trois couches, trois mètres, jamais agrégées ensemble.

## 0. Décisions tranchées (gravées 11/06)

Cinq décisions structurelles sortent de la session 10-11/06 (clôture Brier J+28 + red-team Olivier sur le découpage régime-confondu). Elles sont le point de départ de toute implémentation — ne pas les re-débattre.

### A. Convert consensus_pt at asof, pas at resolve

`pt_native_asof = pt_usd × fx_asof` figé à la pose. Convertir au resolve ré-injecterait le fx-drift asof→resolve dans l'alpha (mélange skill et timing fx). **Asof fige le mètre.** Le PT capturé est une promesse posée à un instant — c'est cet instant qui détermine la conversion devise.

### B. Freeze PT à asof, pas live update

Le PT consensus capturé à asof ne s'update jamais pour ce datapoint. Si le consensus s'ajuste entre asof et resolve, on garde le PT d'origine. Sinon le resolver mesure "tu as suivi un consensus qui s'est ajusté", pas "tu as battu la foule contre laquelle tu as parié". **Le pari est posé contre une cible figée, pas mouvante.**

### C. Horizon strict 12m — thèses longues = paris annuels séquentiels

Le PT consensus a SON horizon (12m, convention FMP/Bigdata). Tu ne peux pas comparer un move 2-3 ans (supercycle uranium) à une cible 12m — deux timescales = apples-to-oranges silencieux. **L'alpha se résout à 12m strict.** Une thèse longue = des paris annuels 12m séquentiels (re-pose chaque année contre un PT 12m frais). Bonus : 3 datapoints propres au lieu d'un mal-aligné.

Le champ `horizon_months` reste utile pour la **couche MÉCANISME** (M2, invalidation_triggers qui couvrent le 2-3 ans), pas pour étirer l'alpha. **Deux couches, deux horizons.**

### D. Frame natif, fx-strippé — l'alpha mesure stock-picking, pas devise

L'alpha se calcule en **devise native de l'action**, fx-strippé. Pour une action US, l'alpha peut être positif en USD pendant que tu perds en EUR (dollar baissé). C'est attendu : la devise est un **bêta séparé** sur ta thèse-action, pas du skill. **Sinon quelqu'un dira "mais mon P&L est en EUR" et re-mélangera les mètres.**

Conséquence pratique : `pt_native_asof` (converti via fx_asof) et `price_at_resolve_native` (observé directement en native) sont les deux opérandes. Aucun EUR dans la formule alpha. Le P&L EUR vit dans une couche orthogonale.

### E. Séparation stricte des trois couches — jamais agréger ensemble

```
COUCHE 1 — Brier signal (existant)
  - Mètre : return ABSOLU (action monte/baisse vs neutre)
  - Horizon : court (~30j typique)
  - Frame : neutre régime (mais dominé par régime, cf clôture J+28)
  - Source : signaux LLM/news → predictions table

COUCHE 2 — Alpha thèse (ce resolver)
  - Mètre : return RELATIF au consensus, devise native
  - Horizon : 12m strict
  - Frame : fx-strippé, régime-strippé (par construction)
  - Source : décisions humaines de thèse → thesis_predictions table

COUCHE 3 — P&L EUR (book réel)
  - Mètre : monnaie EUR convertie via fx live
  - Horizon : continu
  - Frame : full bêta (régime + fx + sizing + timing)
  - Source : transactions → positions
```

**Aucune agrégation cross-couche.** Mélanger Brier signal et alpha thèse dans un même indicateur = la même classe de mensonge que la gauge 2-référentiels d'hier (mètres incompatibles = signe inversé silencieux). À graver en gras dans toute exposition du resolver.

## 1. Le principe en une phrase

> Tu poses un pari (`your_delta_native_pct = (your_target − pt_native_asof) / price_at_asof`) contre le consensus figé à asof, et 12 mois plus tard le resolver mesure `alpha_realized = (price_at_resolve − pt_native_asof) / price_at_asof`. Si `sign(alpha_realized) == sign(your_delta)`, ton call était directionnellement juste. La magnitude pondère par confiance pour un Brier-type score. Le bêta de marché et le fx sont strippés par construction parce que tout est en native et tout est référencé au même `price_at_asof`.

## 2. Architecture canonique

### 2.1 Helper convert : `convert_consensus_pt_to_native(consensus_ref, native_currency, fx_at_asof) -> dict`

```python
# shared/thesis_alpha.py
def convert_consensus_pt_to_native(
    consensus_ref: dict,      # {pt, median, currency, asof}
    native_currency: str,     # devise du ticker (EUR, USD, JPY, KRW, ...)
    fx_at_asof: float,        # fx (consensus.currency → native_currency) at asof
) -> dict | None:
    """Convert PT consensus → devise native du ticker, FIGÉE à asof.

    Décisions A + D : asof = moment de la pose, native = devise de l'action.

    `native_currency` est obligatoire (pas implicite) pour permettre le check
    A2 no-op : sans connaître la devise du ticker, on ne peut pas savoir si
    la conversion est triviale ou non.

    Returns:
        {pt_native, median_native, fx_at_asof_used, asof, source_currency,
         native_currency} si tout OK.
        None si fail-closed L15 (consensus manquant / PT invalide / fx invalide /
        NaN/Inf en input).

    Invariant A2 : si consensus_ref.currency == native_currency, fx_at_asof
    est forcé à 1.0 silencieusement (override contrat clair) — même si le
    caller passe autre chose. La valeur retournée fx_at_asof_used reflète
    le fx réellement utilisé pour la conversion.
    """
```

### 2.2 Table append-only : `thesis_predictions`

Migration alembic, schéma append-only L26 (jamais UPDATE/DELETE sur une ligne posée, comme `transactions`).

```sql
CREATE TABLE thesis_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Pose (asof) — figé pour toujours
    ticker TEXT NOT NULL,
    asof DATE NOT NULL,                       -- date de pose
    asof_price_native REAL NOT NULL,          -- prix à la pose, devise native
    native_currency TEXT NOT NULL,            -- devise du ticker (EUR, USD, JPY, KRW)
    pt_consensus_raw REAL NOT NULL,           -- PT brut tel que captured (typiquement USD)
    pt_consensus_currency TEXT NOT NULL,      -- devise du PT (USD typiquement)
    pt_native_asof REAL NOT NULL,             -- pt converti en native @ fx_asof (décision A)
    fx_at_asof REAL NOT NULL,                 -- fx utilisé pour la conversion (figé)
    your_target_native REAL NOT NULL,         -- ta cible (full ou partial selon contexte)
    your_delta_native_pct REAL NOT NULL,      -- (your_target - pt_native_asof) / asof_price_native × 100
    confidence REAL,                          -- ta confiance 0-1 (optionnel, pour pondération Brier-type)
    thesis_summary TEXT NOT NULL,             -- 1 ligne narrative du pari (le pourquoi)

    -- Resolution (à 12m de asof) — rempli au resolve, jamais avant
    resolve_due_date DATE NOT NULL,           -- asof + 12 months strict (décision C)
    resolved_at DATETIME,                     -- timestamp de la résolution
    resolve_price_native REAL,                -- prix observé à resolve_due_date
    alpha_realized_pct REAL,                  -- (resolve_price - pt_native_asof) / asof_price_native × 100
    direction_correct INTEGER,                -- 1 si sign(alpha_realized) == sign(your_delta), 0 sinon, NULL si neutre
    magnitude_score REAL,                     -- Brier-type score pondéré (à définir §3)

    -- Audit
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT,                              -- 'sweep_133' / 'manual' / etc.
    notes TEXT,

    UNIQUE(ticker, asof, your_target_native)  -- pas de pose dupliquée
);
```

**INVARIANTS L26** : jamais UPDATE sur (asof, asof_price_native, pt_native_asof, your_target_native, your_delta_native_pct). Le resolver ne peut écrire QUE dans les colonnes resolve_*. Trigger SQL ou Pydantic.

### 2.3 Resolver job : `resolve_due_thesis_predictions()`

Cron daily ou weekly. Pour chaque ligne où `resolve_due_date <= today AND resolved_at IS NULL` :

1. Fetch `resolve_price_native` via `shared.prices.get_price_on_date(ticker, resolve_due_date)`
   - Fail-closed si pas de prix dispo (weekend, halted, delisted) → re-essayer J+1 jusqu'à 5 jours, ensuite log error et abandon
2. Compute `alpha_realized_pct = (resolve_price_native - pt_native_asof) / asof_price_native × 100`
3. Compute `direction_correct` :
   - `sign(alpha_realized) == sign(your_delta_native_pct)` → 1
   - signes opposés → 0
   - `|alpha_realized| < ε` (≈ 1%) → NULL (neutre, exclu agrégation comme Brier signal)
4. Compute `magnitude_score` (cf §3 formule)
5. UPDATE row WITH (resolved_at=now, resolve_price_native, alpha_realized_pct, direction_correct, magnitude_score)

### 2.4 Aggregator honnête : `compute_alpha_track_record()`

```python
# scripts/post_resolution_alpha_report.py
def compute_alpha_track_record(min_n: int = 30) -> dict:
    """Verdict alpha skill, fail-closed L19 si N insuffisant.

    Returns dict avec :
    - n_resolved, n_scored (exclus neutres)
    - hit_rate (% direction_correct=1 sur scorés)
    - mean_alpha (en native_pct moyen, attention : pas comparable cross-ticker)
    - n_effective (ajusté corrélation L22 entre tickers, cluster, période)
    - ci_95_bootstrap (sur le hit_rate ET le magnitude_score)
    - verdict : 'insufficient_n' / 'no_skill_detected' / 'skill_detected' / 'anti_skill_detected'

    Décision E gravée : NE JAMAIS agréger avec Brier signal ou P&L EUR.
    Si caller veut un mélange, refuser et expliquer.
    """
```

**L19 fail-closed** : si `n_effective < min_n` ou si CI 95% englobe la baseline → `verdict = 'insufficient_n'`, pas un nombre fabriqué. Le caller affiche "verdict crédible à venir, N=X/min_n" — jamais une fausse confiance.

## 3. Formule alpha + magnitude_score

### 3.1 Alpha directionnel — deux seuils symétriques

```
your_delta_native_pct  = (your_target_native − pt_native_asof) / asof_price_native × 100
alpha_realized_pct     = (resolve_price_native − pt_native_asof) / asof_price_native × 100

classify_direction (deux ε symétriques, ordre de priorité no_bet > neutral > correct/incorrect) :
  = 'no_bet'    si |your_delta| < ε_delta     (pendant symétrique §6.8 : your_target ≈ consensus = pas de pari)
  = 'neutral'   si |alpha| < ε_neutre          (zone neutre alpha, exclu agrégation)
  = 'correct'   si sign(alpha) == sign(your_delta) ET |alpha| ≥ ε_neutre ET |your_delta| ≥ ε_delta
  = 'incorrect' si signes opposés (mêmes conditions de seuil)

Mapping writer (pièce 3) :
  direction_correct INTEGER :
    'correct'    → 1
    'incorrect'  → 0
    'neutral'    → NULL  (exclu agrégation, mais ligne conservée pour audit)
    'no_bet'     → NULL  (exclu agrégation, distinguable de neutral via colonne notes/flag)
```

**Pourquoi deux ε et pas un seul** : sans ε_delta, une pose `your_target ≈ consensus` (delta minuscule) serait scorée sur le signe fragile d'un alpha large — `+0.1%` delta vs `-0.1%` delta donneraient verdicts opposés sur le même alpha, alors que les deux poses expriment "pas de variant view". C'est le pendant symétrique de §6.8 (pas de PT consensus = pas de pari) appliqué côté pose.

**Diagnostic distinct** :
- `no_bet` fréquent → poses molles (l'humain ne diverge pas vraiment de la foule)
- `neutral` fréquent → régime plat (les actions ne bougent pas à 12m)
- Les deux exclus de l'agrégation mais informatifs séparément.

### 3.2 Magnitude score (Brier-type pondéré confiance)

```
# Si confidence est posée à la pose :
prob_you_assigned = 0.5 + (confidence × 0.5 × sign(your_delta))
                  # ex. confidence=0.8 + delta positif → prob=0.9 que action bat consensus
outcome_realized  = 1 si alpha_realized > +ε_neutre
                  = 0 si alpha_realized < -ε_neutre
                  = NULL sinon (exclu)
magnitude_score   = (prob_you_assigned − outcome_realized) ² si outcome_realized non NULL
                  # standard Brier, mais sur alpha-direction, pas return-direction
                  # baseline no-skill = 0.25 (prob=0.5 sur tout)

# Si confidence absente :
magnitude_score = NULL → contribue à hit_rate mais pas au Brier
```

**Convention ε_neutre** : 1% en native. Adaptable par classe d'actif si nécessaire mais documenté.

## 4. Fail-closed (cas-bord) + axe lifecycle vs axe scoring

### 4.1 Axes orthogonaux — ne PAS mélanger

Deux questions distinctes sur une prédiction résolue :
- **Lifecycle** : le pari a-t-il pu être résolu ? → `resolution_status TEXT IN ('resolved','abandoned')`
- **Scoring** : si résolu, qu'est-ce qui le rend scorable ou non ? → `exclude_reason TEXT IN ('neutral','no_bet')` (NULL si scorable)

Mélanger les deux dans une seule enum = bug 2-référentiels (gauge canonique 09/06). **Banni.**

**Conséquence agrégateur** : filtre sur la chose que tu scores, pas sur les axes de diagnostic.
- Accuracy directionnelle → `WHERE direction_correct IS NOT NULL` (NULL pour neutral, no_bet, abandoned — exclus par construction, peu importe la cause)
- Brier/magnitude → `WHERE magnitude_score IS NOT NULL`
- `resolution_status` et `exclude_reason` sont des diagnostics (pourquoi exclu), pas la porte de scoring

### 4.2 Cas-bord

| Cas | Comportement |
|---|---|
| PT consensus manquant à asof | **Ne pas poser la ligne.** Pas de pari sans benchmark. Log skip 'no_pt_consensus_at_pose'. |
| fx_at_asof indisponible | Idem — fail-closed L15, jamais de fallback fx=1.0 silencieux (cf bug CCJ fx_at_purchase=1.0 du 10/06). |
| `resolve_price_native` indisponible — **fenêtre de grâce active** | Window `[due_date .. due_date + grace_days]` (default 5j calendaire). Tant que `today ≤ due_date + grace_days` ET fenêtre essayée vide → laisser `resolved_at=NULL` → re-pickup naturel par `get_due` au prochain cron quotidien. |
| `resolve_price_native` indisponible — **grâce épuisée** | `today > due_date + grace_days` ET fenêtre `[due..due+grace]` toujours vide → **`mark_thesis_prediction_abandoned`** : `resolved_at=now`, `resolution_status='abandoned'`, prix/alpha/direction/magnitude/exclude_reason tous NULL. Sort du pool `get_due` ET du pool scoring. Log event 'thesis_resolve_abandoned'. |
| Prix retourné non-fini (NaN, ≤0) | Traité comme "prix manquant à cette date" — continue la fenêtre. **Jamais propagé** à compute_alpha. Évite qu'un glitch transitoire yfinance tue un vrai pari. |
| `classify_direction` retourne `None` malgré présence de prix | **Inatteignable** post-validation prix amont (compute_alpha sur prix fini retourne float fini). Si arrive = bug logique. Fail-loud : log error, laisse `resolved_at=NULL`, surface monitor. **Jamais abandon silencieux** (un bug ne tue pas un pari, un manquement de donnée si). |
| Ticker delisted entre asof et resolve | Le ticker delisted retourne `None` partout dans la fenêtre → grâce s'épuise → abandon terminal via le même chemin que prix manquant. Pas de cas spécial nécessaire. |
| Position vendue avant resolve_due_date | **Le pari reste résolu à 12m** — l'alpha mesure la prédiction, pas l'exécution P&L. Ne pas court-circuiter par l'event de vente. |
| Re-pose d'une thèse identique (même target_native) à un asof+1 | Ligne SÉPARÉE (les datapoints sont des paris annuels séquentiels, décision C). |
| Multi-target (partial + full) sur une même thèse | Lignes SÉPARÉES (1 par target_native). Évite la confusion "quel target a battu". |

### 4.3 Fenêtre de grâce bornée — anti-downtime drift

La fenêtre est **toujours `[due_date .. due_date + grace_days]`**, indépendamment de `today`. Conséquence : si le resolver est down 10 jours et reprend à `today = due_date + 10`, il essaie quand même `[due_date .. due_date + grace_days]` (pas `[due_date .. today]`).

**Pourquoi** : prendre un prix à J+7 ou J+10 quand `grace_days=5` violerait le contrat de grâce (on accepte ≤5j de retard sur l'anniversaire 12m, au-delà on n'a plus confiance que c'est le bon point d'observation). La grâce est un seuil de confiance temporelle, pas une fenêtre opportuniste.

**Robustesse downtime** : si `due_date` a un prix dispo, le resolver le récupère quel que soit `today` (cas normal). L'abandon ne déclenche que si la fenêtre `[due..due+grace]` est intégralement vide ET grâce expirée.

## 5. Tests verrouillants

Implémentés dans `tests/test_thesis_alpha_resolver.py` (à créer post-spec) :

- **A1** test_convert_at_asof_freezes_fx : pose à asof avec fx_asof=1.055, fx live=1.10 → pt_native_asof reste basé sur 1.055.
- **A2** test_convert_no_op_when_currencies_match : consensus EUR + ticker EUR → pt_native_asof = pt_consensus_raw, fx_at_asof=1.0.
- **B1** test_pt_consensus_frozen_post_pose : update consensus_ref dans portfolio_rules.yaml après la pose → la ligne thesis_predictions ne bouge pas.
- **C1** test_resolve_at_12m_strict : asof=2026-06-11 → resolve_due_date=2027-06-11 exact.
- **C2** test_long_thesis_requires_yearly_reposes : thèse "supercycle 2-3 ans" doit produire 3 lignes annuelles séquentielles, pas 1 ligne 36m.
- **D1** test_alpha_native_strippe_fx : asof_price=100 USD, resolve_price=110 USD, pt_native_asof=105 → alpha=+5%. Indépendant du fx EUR/USD entre asof et resolve.
- **D2** test_alpha_not_pnl_eur : action US en gain USD pendant que EUR/USD a baissé → alpha positif (le pari skill est juste), P&L EUR séparé (négatif possible). Les deux coexistent honnêtement.
- **E1** test_aggregator_refuses_brier_signal_mix : tenter de combiner alpha avec Brier signal → ValueError("layers must be aggregated separately").
- **E2** test_layers_documented_in_aggregator_output : le verdict dict contient explicitement `layer: "thesis_alpha"` et un `not_compatible_with: ["brier_signal", "pnl_eur"]`.
- **F1** test_fail_closed_when_pt_missing : pose sans PT consensus → no-op, log skip, table inchangée.
- **F2** test_fail_closed_when_fx_missing : pose avec fx_at_asof=None → no-op, log skip.
- **F3** test_aggregator_returns_insufficient_n_below_threshold : n_effective=5 → verdict='insufficient_n', pas de point estimate.
- **G1** test_append_only_resolve_columns_only : tenter UPDATE sur asof_price_native → SQL trigger / Pydantic raise. Seules `resolved_at`, `resolve_price_native`, `alpha_realized_pct`, `direction_correct`, `magnitude_score` sont mutables post-insert.

## 6. Anti-patterns (le chemin à ne pas reprendre)

### 6.1 Convert PT au resolve, pas à asof

Réinjecte le fx-drift asof→resolve dans l'alpha. L'alpha mesure alors un mélange skill stock-picking + skill timing fx. **Banni** : Décision A.

### 6.2 Live-update PT consensus

Mesure "tu as suivi le consensus", pas "tu as battu la foule contre laquelle tu as parié". Le PT consensus est une promesse posée par les analystes à un instant donné — c'est contre cet instant que tu paries. **Banni** : Décision B.

### 6.3 Étirer horizon thèse (3 ans) contre PT 12m

Apples-to-oranges. Le PT consensus mesure 12m, étirer la résolution à 36m mélange deux timescales. **Banni** : Décision C. Une thèse longue = paris annuels séquentiels.

### 6.4 Calculer alpha en EUR

Mélange skill stock-picking et exposition devise. L'alpha cherche à isoler le skill, pas à le polluer. **Banni** : Décision D.

### 6.5 Agréger alpha + Brier signal dans un même indicateur

Mètres incompatibles (relatif vs absolu, 12m vs court, fx-strippé vs régime-confondu). Produit la même classe de mensonge silencieux que la gauge 2-référentiels d'hier. **Banni** : Décision E.

### 6.6 Conclure le skill sur N petit dans un seul régime

Le piège chopé en direct le 10-11/06 sur le Brier signal J+28 : "perma-bear détecté" sur N=53 mono-régime = artefact, pas finding. L'aggregator alpha est verrouillé fail-closed L19 jusqu'à N_effective ≥ 30 ET CI sortant strictement de baseline. **Banni** par construction de l'agrégateur.

### 6.7 Court-circuiter la résolution par l'event de vente

Si tu vends la position avant resolve_due_date, le pari reste résolu à 12m. L'alpha mesure la prédiction directionnelle, pas l'exécution. Court-circuiter masquerait les paris qu'on aurait dû tenir et qui auraient battu le consensus. **Banni** : Fail-closed §4.

### 6.8 Pose sans PT consensus ("ma conviction tout court")

Sans benchmark, pas de variant-perception possible — c'est juste un return absolu. Une pose alpha exige un PT consensus de référence. Si absent, log skip et la décision reste qualitative (registre sweep markdown, pas thesis_predictions). **Banni** : Fail-closed §4.

## 7. Implementation Status

- **Gravé** : 2026-06-11 (canon post-clôture Brier J+28 + red-team séparation régime/biais)
- **Implémentation** : **IMPLEMENTED** (2026-06-11, session unique 7 pièces)
- **Pré-conditions déjà acquises** :
  - `ConsensusRef.currency` obligatoire (e090bb9, 10/06)
  - `portfolio_rules.yaml` tagged `currency: USD` sur 11 lignes
  - Tests verrouillants currency : `test_consensus_ref_currency_required`, `_invalid_rejected`
- **Livré (mapping fichiers réels)** :
  - `shared/thesis_alpha.py` : `convert_consensus_pt_to_native` + `compute_your_delta_native_pct` + `compute_alpha_realized_pct` + `classify_direction` (pure helpers, fail-closed L15 sur inputs invalides)
  - `scripts/alembic/versions/0052_thesis_predictions.py` : table append-only L26 + 3 triggers immutabilité (pose_writeonce, resolve_writeonce, no_delete). Note : numéro 0052 (Python alembic), pas 0051_*.sql.
  - `scripts/alembic/versions/0053_thesis_predictions_add_resolution_status.py` : ADD COLUMN `resolution_status` (axe lifecycle 'resolved'/'abandoned' distinct de `exclude_reason`) + DROP/CREATE trigger 2 étendu.
  - `shared/thesis_predictions_writer.py` (PAS `shared/storage.py`) : `insert_thesis_pose()` (gate no_bet à la pose, décision A 11/06) + `get_due_thesis_predictions()` + `update_thesis_resolve_fields()` (UN UPDATE atomique contrat trigger 2) + `mark_thesis_prediction_abandoned()` (lifecycle terminal §4.2).
  - `bot/jobs/thesis_alpha_resolver.py` : `resolve_due_thesis_predictions(today, grace_days, ε_neutral, ε_delta, fetcher=None)` cron daily. DI fetcher (DI > monkeypatch global). Garde §4.3 fenêtre bornée. Magnitude `outcome=sign(alpha)` (PAS direction_correct). Invariant L27 garanti par construction (`attempted == Σ` via `write_failed` counter).
  - `scripts/aggregator_alpha_track_record.py` (PAS `post_resolution_alpha_report.py`) : `compute_alpha_track_record(cluster_strategy)` — **cluster (block) bootstrap** (resample clusters, pas preds iid) + **baseline taux-de-base `p̄(1−p̄)` sur outcomes `sign(alpha)`** (PAS direction_correct, inversion catastrophique catchée pré-prod) + verdict fail-closed L19 gaté sur pool BRIER. Plancher principielle `n_clusters_brier ≥ 2`, **constantes L16 fabriquées dissoutes** (anciens `min_n_effective=30` et `min_n_for_ci=10` retirés post red-team Olivier).
  - `tests/test_thesis_alpha_resolver.py` (18 tests) + `tests/test_aggregator_alpha_track_record.py` (18 tests dont T8/T9 critiques anti-inversion + anti-iid) + `tests/test_e2e_alpha_chain.py` (2 tests pose→resolver→aggregator + lock storage-only subprocess) + `tests/test_thesis_predictions_writer.py` + `tests/test_thesis_predictions_table.py`.
- **Cure infra #128 (12/06/2026 cf [memory feedback-red-team-verify-before-assert](.claude/projects/-Users-olivierlegendre-mes-bots-finance/memory/feedback_red_team_verify_before_assert.md))** : `bot/jobs/__init__.py` vidé de ses ré-exports eager (Option B, supprimer la machinerie > la rendre lazy). `bot/main.py` migré vers imports par sous-module (daily/intervals/periodic). Sans cette cure, importer `bot.jobs.thesis_alpha_resolver` tirait pandas/yfinance/google/data_sources au package-level → tests pièce 4 + E2E non-runnables sur venv minimal. Post-#128 : module resolver run-vérifié storage-only sur 2 machines (Mac + venv minimal 3.14.5).
- **Backfill SK + CCJ POSÉS** (session 11/06 soir) :
  - SK Hynix ID 1 : `asof=2026-06-11`, `asof_price=2,101,000 KRW` (yfinance), `pt=2,500,000 KRW` (agrégateur updated post-rally, choisi consciemment vs blend mécanique 2,3M), `your_target=3,600,000`, `your_delta=+52.36%` (bull magnitude), `confidence=0.8` (c4), `source="rv_micron_peg_2026-06"`, resolve due 2027-06-11.
  - Cameco (CCJ) ID 2 : `asof=2026-06-10` (NYSE pas clos au moment de la pose 11/06 — fail-loud assert `actual==ASOF` a forcé décalage propre vers dernière close réelle), `asof_price=95.03 USD`, `pt=139.0` (médiane robuste vs moyenne 140.25 traînée par range), `your_target=130.0`, `your_delta=-9.47%` (bear modéré, fade analystes à la marge), `confidence=0.8` (c4 décoté depuis c5 par Olivier), `source="fade_analyst_targets_2026-06"`, resolve due 2027-06-10.
- **Timing attendu du premier verdict** : `resolve_due_date` de CCJ = 2027-06-10 (première résolution due) + `resolve_due_date` SK = 2027-06-11. Verdict statistique aggregator ne deviendra significatif qu'avec ~30+ paris accumulés sur plusieurs clusters distincts (pas avant fin 2027 / début 2028). C'est L13 — patience instrumentée, pas gratification.
- **Cure P0 audit (2) APPLIQUÉE (commit a9f4f07, migration 0054)** : `ε_delta_pct_at_pose` + `ε_neutral_pct_at_pose` ajoutés à la table, les DEUX figés à la pose (pas at_resolve — stocker au resolve aurait documenté le drift au lieu de l'empêcher, red-team Olivier 11/06 soir). Writer stocke à l'INSERT, resolver LIT les ε figés du pred (fallback loggé `thesis_resolve_legacy_epsilon_fallback` si NULL, défensif pour cas pathologique). Trigger 1 étend la liste UPDATE OF aux 2 ε pour les figer immuables ensuite. Backfill in-migration : SK ID 1 + CCJ ID 2 → ε=1.0 (doctrine juin 2026 connue). Sémantique cohérente avec SPEC §0 décision B « Freeze à la pose » étendue aux ε (cible figée pour mesure).
- **Doctrine post-livraison — formules scoring figées** (note P1 audit (2)) : `compute_alpha_realized_pct` et `_compute_magnitude_score` (= la formule Brier-type `prob_you = 0.5 + conf×0.5×sign(δ)`, outcome = `sign(α)`) sont **figées post-1re-pose**. Toute modification doctrinale exige : (i) migration explicite stockant `scoring_doctrine_version: int` dans la pose, OU (ii) re-pose de tous les paris ouverts sous la nouvelle doctrine. Pas de modification silencieuse dans `shared/thesis_alpha.py` ou `bot/jobs/thesis_alpha_resolver.py` — le verdict 12 mois plus tard doit être reproductible bit-perfect contre les formules du jour de la pose. Versioning implicite via `git log` aujourd'hui ; si on en a besoin un jour, la colonne `scoring_doctrine_version` est l'option propre.
- **KNOWN-GAP `grace_days` consciemment non-figé** (note P1 audit (2)) : `grace_days = 5` reste hardcodé dans `bot/jobs/thesis_alpha_resolver.py` (resolve-side, pas pose-side). Analyse de proba de drift : `grace_days` ne mord QUE pour un titre **sans prix pendant 5 jours MAIS avec un prix à due+6..10** — un delisting = pas de prix sur toute la fenêtre quoi qu'il en soit (abandon quel que soit grace=5 ou 20). Le seul cas où grace change l'issue = un halt d'~1 semaine puis reprise, quasi-nul sur titres liquides (SK, CCJ). Geler `grace_days_at_resolve` serait cohérent en principe (même classe que ε) mais c'est de l'over-engineering pour une proba ~0. Si jamais on change `grace_days` un jour, à ce moment-là on ajoute la migration de fixation. Décision consciente, pas négligence.

## 8. Le fil

> Le Brier signal mesure des intuitions court-terme dans le régime de l'instant. Le P&L EUR mesure l'argent total mélangé. L'**alpha thèse** isole une chose et une seule : ton skill de stock-picking contre la foule, dans la devise de l'action, sur l'horizon où la foule a parié elle aussi (12m). Pas plus. Si tu bats régulièrement le consensus en native sur 12m, tu as un skill — indépendamment du régime de marché, indépendamment du fx, indépendamment de combien tu as taillé tes positions. C'est le mètre qui ne ment pas parce qu'il ne prétend mesurer qu'une seule chose. **Trois couches, trois mètres, jamais mélangées.** Le payoff est dans 12-18 mois ; l'instrument se monte aujourd'hui.
